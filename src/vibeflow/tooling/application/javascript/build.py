from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from vibeflow.targets.javascript.build.builder import BuildRequest, BuildResult, build_aot
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.build.project_graph import (
    PreparationState as _PreparationState,
    prepare_graph as _prepare_graph,
    require_explicit_inputs as _require_explicit_inputs,
)
from vibeflow.targets.javascript.build.project_paths import (
    javascript_options as _javascript_options,
    safe_project_path as _safe_project_path,
)
from vibeflow.targets.javascript.build.project_resources import (
    base_lib_closure as _base_lib_closure,
    enriched_payload as _enriched_payload,
    host_extension_closure as _host_extension_closure,
    import_policy as _import_policy,
    required_capabilities as _required_capabilities,
    schemas_for_types as _schemas_for_types,
    used_schema_types as _used_schema_types,
)
from vibeflow.core import (
    CompiledGraph,
    CoreCompileRequest,
    ImplementationFacts,
    TargetFeatureSet,
    compile_core,
)
from vibeflow.tooling.project.config_loader import load_workspace_config_document
from vibeflow.tooling.project.host_extensions import host_extension_resources
from vibeflow.core.descriptors import DescriptorCatalogs
from vibeflow.targets.javascript.frontend.facts import (
    JavascriptImplementationFactsError,
    implementation_facts_from_catalog,
    validate_javascript_descriptor_catalogs,
)
from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs
from vibeflow.core.flow import GraphConfig
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.block_compiler import WorkflowPlan, compile_graph_plan
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptBindingPlan,
    JavascriptPluginBinding,
    build_javascript_binding_plan,
)
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    JavascriptPluginBindingPlan,
    JavascriptPluginError,
    parse_javascript_plugin_selection,
    resolve_javascript_plugins,
)
from vibeflow.targets.javascript.build.plugin_hooks import (
    JavascriptBuildPluginReport,
    JavascriptBuildPluginRunner,
)
from vibeflow.core.config.scope import (
    ConfigScope,
    normalize_config_scope,
    normalize_node_config_overrides,
)
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.workspace_model import (
    WorkspaceConfig,
    WorkspaceRoot,
)

@dataclass(frozen=True)
class ProjectBuildRequest:
    """A workspace-aware request for a JavaScript/TypeScript AOT build."""

    workspace: str | Path
    config: str | Path
    out_dir: str | Path
    target: str
    profile: str
    workflow_id: str = ""
    node_config_overrides: Mapping[str, Mapping[str, Any]] | None = None
    global_config: Mapping[str, Any] | ConfigScope | None = None
    entry_name: str = ""
    sourcemap: str = "external"
    replace: bool = False
    html_template: str | Path | None = None
    app_entry: str | Path | None = None
    node_command: str = "node"


@dataclass(frozen=True)
class PreparedProjectBuild:
    workspace: WorkspaceConfig
    root: WorkspaceRoot
    config_path: Path
    package_root: Path
    graph: GraphConfig
    compiled: CompiledGraph
    catalogs: DescriptorCatalogs
    plan: WorkflowPlan
    payload: Mapping[str, Any]
    implementation_by_type: Mapping[str, object]
    import_policy: Mapping[str, Any]
    external_packages: tuple[str, ...]
    used_node_types: tuple[str, ...]
    used_base_libs: tuple[str, ...]
    used_capabilities: tuple[str, ...]
    used_host_extensions: tuple[str, ...]
    declared_host_extensions: tuple[Mapping[str, Any], ...]
    planned_host_extensions: tuple[str, ...]
    host_extensions: tuple[Mapping[str, Any], ...]
    declared_plugins: tuple[Mapping[str, Any], ...] = ()
    planned_plugins: tuple[str, ...] = ()
    plugin_bindings: tuple[Mapping[str, Any], ...] = ()
    plugin_annotations: tuple[Mapping[str, Any], ...] = ()
    plugin_findings: tuple[Mapping[str, Any], ...] = ()
    plugin_relaxations: tuple[Mapping[str, Any], ...] = ()
    plugin_audit_sources: tuple[str, ...] = ()
    warnings: tuple[Mapping[str, str], ...] = ()
    javascript_bindings: JavascriptBindingPlan | None = None


@dataclass(frozen=True)
class ProjectBuildResult:
    prepared: PreparedProjectBuild
    build: BuildResult

    @property
    def out_dir(self) -> Path:
        return self.build.out_dir

    @property
    def entry(self) -> Path:
        return self.build.entry

    @property
    def manifest(self) -> Path:
        return self.build.manifest

    @property
    def files(self) -> tuple[str, ...]:
        return self.build.files


BeforeCompileHook = Callable[[GraphConfig, DescriptorCatalogs], GraphConfig]


def prepare_project_build(
    request: ProjectBuildRequest,
    *,
    before_compile_hooks: tuple[BeforeCompileHook, ...] = (),
) -> PreparedProjectBuild:
    """Load and validate one workspace workflow without invoking Node.js."""

    if request.target not in {"browser", "node"}:
        raise ProjectBuildError(
            "VF_AOT_TARGET",
            "target must be 'browser' or 'node'",
        )
    workspace_path = Path(request.workspace).expanduser().resolve()
    config_path = Path(request.config).expanduser().resolve()
    workspace = load_workspace_config(workspace_path)
    root = workspace.root_for_path(config_path)
    if root is None:
        raise ProjectBuildError(
            "VF_AOT_CONFIG_ROOT",
            f"config is not under a workspace root: {config_path}",
        )
    if root.project_target != "javascript":
        raise ProjectBuildError(
            "VF_AOT_PROJECT_TARGET",
            "JavaScript AOT build requires project_target 'javascript'; "
            f"root {root.id!r} declares {root.project_target!r}",
        )
    if not config_path.is_file():
        raise ProjectBuildError(
            "VF_AOT_CONFIG",
            f"workflow config does not exist: {config_path}",
        )

    catalogs = load_project_descriptor_catalogs(
        root.path,
        project_config=root.config_path,
    )
    try:
        validate_javascript_descriptor_catalogs(catalogs)
    except JavascriptImplementationFactsError as exc:
        raise ProjectBuildError(exc.code, exc.message) from exc
    node_catalog = catalogs.nodes
    base_lib_catalog = catalogs.base_libs
    implementation_facts = implementation_facts_from_catalog(
        node_catalog,
        target=request.target,
    )
    target_features = TargetFeatureSet(target=request.target)
    javascript = _javascript_options(root)
    package_root = _safe_project_path(
        root.path,
        javascript["package_root"],
        subject="javascript.package_root",
        require_directory=True,
    )

    document = load_workspace_config_document(config_path, workspace=workspace)
    graph = parse_graph_config(
        document.data,
        project_root=root.path,
        root_id=root.id,
        root_path=root.path,
        source_path=config_path,
    )
    graph = _apply_before_compile_hooks(
        graph,
        catalogs=catalogs,
        hooks=before_compile_hooks,
    )
    plugin_plan = _javascript_plugin_plan(
        document.data,
        catalogs=catalogs,
        target=request.target,
        entry_mode=graph.entry_mode,
        project_root=root.path,
    )
    _require_explicit_inputs(graph, path=())
    plugin_report = JavascriptBuildPluginReport()
    build_plugins = (*plugin_plan.policy_plugins, *plugin_plan.compiler_plugins)
    if build_plugins:
        try:
            with JavascriptBuildPluginRunner(
                plugin_plan,
                package_root=package_root,
                target=request.target,
                workflow_id=request.workflow_id or config_path.stem,
                node_command=request.node_command,
            ) as plugin_runner:
                plugin_runner.validate_policy(graph)
                plugin_runner.before_compile(graph)
                compilation = _compile_core_compilation(
                    graph,
                    implementation_facts=implementation_facts,
                    target_features=target_features,
                    known_nodesets=set(graph.nodesets),
                    owner="pipeline",
                )
                graph = compilation.workflow.graph
                compiled = compilation.compiled_graph
                plugin_runner.after_compile(graph, compiled)
                plugin_report = plugin_runner.report()
        except JavascriptPluginError as exc:
            raise ProjectBuildError(exc.code, str(exc)) from exc
    else:
        compilation = _compile_core_compilation(
            graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodesets=set(graph.nodesets),
            owner="pipeline",
        )
        graph = compilation.workflow.graph
        compiled = compilation.compiled_graph
    try:
        top_overrides = normalize_node_config_overrides(
            request.node_config_overrides or {}
        )
    except Exception as exc:
        raise ProjectBuildError(
            "VF_AOT_PARAMS",
            str(exc),
        ) from exc
    raw_global = (
        document.data.get("global_config", {})
        if request.global_config is None
        else request.global_config
    )
    global_scope = normalize_config_scope(raw_global)
    state = _PreparationState(
        target=request.target,
        project_root=root.path,
        catalog=node_catalog,
        base_libs=base_lib_catalog,
        compile_graph=lambda child_graph, known_nodesets, owner: _compile_core_graph(
            child_graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodesets=known_nodesets,
            owner=owner,
        ),
        compiled_by_path={},
        params_by_path={},
        source_by_type={},
        implementations={},
        used_nodes={},
        used_types=set(),
        used_io_operations=set(),
    )
    _prepare_graph(
        graph,
        compiled,
        state=state,
        path=(),
        overrides=top_overrides,
        global_scope=global_scope,
        active_nodesets=(),
    )

    base_lib_order, base_lib_implementations = _base_lib_closure(
        state.used_nodes,
        catalog=base_lib_catalog,
        target=request.target,
        project_root=root.path,
    )
    capabilities = _required_capabilities(
        state.used_nodes,
        catalogs=catalogs,
        target=request.target,
        io_operations=state.used_io_operations,
    )
    schema_types = set(state.used_types)
    schema_types.update(_used_schema_types(graph, state.used_nodes, capabilities))
    schemas = _schemas_for_types(schema_types, catalogs=catalogs)
    plan = compile_graph_plan(
        graph,
        compiled,
        workflow_id=request.workflow_id or None,
        source_by_type=state.source_by_type,
        compiled_by_path=state.compiled_by_path,
        params_by_path=state.params_by_path,
        implementation_facts=implementation_facts,
        target_features=target_features,
    )
    payload = _enriched_payload(
        plan,
        schemas=schemas,
        capabilities=capabilities,
        nodes=state.used_nodes,
        implementations=state.implementations,
    )
    uses_legacy_host_extensions = (
        "host_extensions" not in document.data
        and bool(javascript["host_extensions"])
    )
    declared_host_extensions = _declared_host_extensions(
        document.data,
        legacy_ids=tuple(javascript["host_extensions"]),
        catalog=catalogs.host_extensions,
    )
    implemented_host_extensions = tuple(
        item.id
        for item in declared_host_extensions
        if item.status == "implemented"
    )
    planned_host_extensions = frozenset(
        item.id
        for item in declared_host_extensions
        if item.status == "planned"
    )
    host_extensions = _host_extension_closure(
        implemented_host_extensions,
        catalogs=catalogs,
        target=request.target,
        project_root=root.path,
        configurations={
            item.id: dict(item.config)
            for item in declared_host_extensions
            if item.status == "implemented"
        },
        planned=planned_host_extensions,
    )
    project_external = tuple(javascript["external_packages"])
    allowed_external = set(project_external)
    for descriptor in base_lib_order:
        allowed_external.update(descriptor.external_packages)
    for extension in host_extensions:
        allowed_external.update(extension["external_packages"])
    for binding in _active_plugin_bindings(plugin_plan):
        allowed_external.update(binding.external_packages)
    import_policy = _import_policy(
        nodes=state.used_nodes,
        base_libs=base_lib_order,
        node_catalog=catalogs.nodes,
        base_lib_catalog=catalogs.base_libs,
        target=request.target,
        project_root=root.path,
        allowed_external=allowed_external,
        implementations=state.implementations,
        host_extensions=host_extensions,
    )
    import_policy = _plugin_import_policy(import_policy, plugin_plan)
    javascript_bindings = build_javascript_binding_plan(
        plan,
        implementations=state.implementations,
        base_libs_by_type={
            key: tuple(descriptor.base_libs)
            for key, descriptor in state.used_nodes.items()
        },
        capabilities_by_type={
            key: tuple(
                requirement.to_dict()
                for requirement in descriptor.capabilities
            )
            for key, descriptor in state.used_nodes.items()
        },
        schemas=schemas,
        base_libs={
            descriptor.id: {
                "implementation": dict(
                    base_lib_implementations[descriptor.id]
                ),
                "dependencies": list(descriptor.dependencies),
                "external_packages": list(
                    descriptor.external_packages
                ),
            }
            for descriptor in base_lib_order
        },
        capabilities={
            capability.id: {
                "operations": {
                    name: operation.to_dict()
                    for name, operation in sorted(
                        capability.operations.items()
                    )
                }
            }
            for capability in capabilities
        },
        host_extensions=host_extensions,
        runtime_plugins=plugin_plan.runtime_plugins,
        import_policy=import_policy,
    )
    return PreparedProjectBuild(
        workspace=workspace,
        root=root,
        config_path=config_path,
        package_root=package_root,
        graph=graph,
        compiled=compiled,
        catalogs=catalogs,
        plan=plan,
        payload=payload,
        implementation_by_type=dict(state.implementations),
        import_policy=import_policy,
        external_packages=project_external,
        used_node_types=tuple(sorted(state.used_nodes)),
        used_base_libs=tuple(item.id for item in base_lib_order),
        used_capabilities=tuple(item.id for item in capabilities),
        used_host_extensions=tuple(
            str(item["id"]) for item in host_extensions
        ),
        declared_host_extensions=tuple(
            item.to_dict() for item in declared_host_extensions
        ),
        planned_host_extensions=tuple(sorted(planned_host_extensions)),
        host_extensions=host_extensions,
        declared_plugins=tuple(
            _plugin_manifest_binding(item, project_root=root.path)
            for item in (
                *_active_plugin_bindings(plugin_plan),
                *plugin_plan.planned_plugins,
            )
        ),
        planned_plugins=tuple(
            item.id for item in plugin_plan.planned_plugins
        ),
        plugin_bindings=tuple(
            _plugin_manifest_binding(item, project_root=root.path)
            for item in _active_plugin_bindings(plugin_plan)
        ),
        plugin_annotations=plugin_report.annotations,
        plugin_findings=plugin_report.findings,
        plugin_relaxations=plugin_report.relaxations,
        plugin_audit_sources=tuple(
            item.module for item in _active_plugin_bindings(plugin_plan)
        ),
        warnings=(
            (
                {
                    "code": "VF_AOT_HOST_EXTENSION_LEGACY_SELECTION",
                    "message": (
                        "javascript.host_extensions is deprecated; select "
                        "host extensions in the workflow-level "
                        "host_extensions list"
                    ),
                },
            )
            if uses_legacy_host_extensions
            else ()
        ),
        javascript_bindings=javascript_bindings,
    )


def _compile_core_graph(
    graph: GraphConfig,
    *,
    implementation_facts: ImplementationFacts,
    target_features: TargetFeatureSet,
    known_nodesets: set[str],
    owner: str,
) -> CompiledGraph:
    """Call the public Core compile boundary and return its graph view."""

    return _compile_core_compilation(
        graph,
        implementation_facts=implementation_facts,
        target_features=target_features,
        known_nodesets=known_nodesets,
        owner=owner,
    ).compiled_graph


def _compile_core_compilation(
    graph: GraphConfig,
    *,
    implementation_facts: ImplementationFacts,
    target_features: TargetFeatureSet,
    known_nodesets: set[str],
    owner: str,
):
    return compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodesets=frozenset(known_nodesets),
            owner=owner,
        )
    )


def build_project_aot(request: ProjectBuildRequest) -> ProjectBuildResult:
    prepared = prepare_project_build(request)
    result = build_aot(
        BuildRequest(
            plan=prepared.plan,
            project_root=prepared.root.path,
            package_root=prepared.package_root,
            out_dir=request.out_dir,
            target=request.target,
            profile=request.profile,
            external_packages=prepared.external_packages,
            entry_name=request.entry_name,
            sourcemap=request.sourcemap,
            replace=request.replace,
            html_template=request.html_template,
            app_entry=request.app_entry,
            node_command=request.node_command,
            javascript_bindings=prepared.javascript_bindings,
            plugin_manifest={
                "declared": list(prepared.declared_plugins),
                "planned": list(prepared.planned_plugins),
                "active": list(prepared.plugin_bindings),
                "annotations": [
                    dict(item) for item in prepared.plugin_annotations
                ],
                "relaxations": [
                    dict(item) for item in prepared.plugin_relaxations
                ],
            },
            audit_sources=prepared.plugin_audit_sources,
        )
    )
    return ProjectBuildResult(prepared=prepared, build=result)


def _apply_before_compile_hooks(
    graph: GraphConfig,
    *,
    catalogs: DescriptorCatalogs,
    hooks: tuple[BeforeCompileHook, ...],
) -> GraphConfig:
    """Apply optional target-owned, in-memory compile transforms in order."""

    current = graph
    for index, hook in enumerate(hooks):
        try:
            transformed = hook(current, catalogs)
        except Exception as exc:
            raise ProjectBuildError(
                "VF_AOT_BEFORE_COMPILE_HOOK",
                f"before-compile hook {index} failed: {exc}",
            ) from exc
        if not isinstance(transformed, GraphConfig):
            raise ProjectBuildError(
                "VF_AOT_BEFORE_COMPILE_HOOK",
                f"before-compile hook {index} must return GraphConfig",
            )
        current = transformed
    return current


def _javascript_plugin_plan(
    config: Mapping[str, Any],
    *,
    catalogs: DescriptorCatalogs,
    target: str,
    entry_mode: str,
    project_root: Path,
) -> JavascriptPluginBindingPlan:
    raw = config.get("plugins", ())
    if raw in (None, ()):
        raw = []
    if not isinstance(raw, list):
        raise ProjectBuildError(
            "VF_AOT_PLUGIN_CONFIG",
            "workflow plugins must be a list of static plugin ids",
        )
    try:
        selections = tuple(
            parse_javascript_plugin_selection(item) for item in raw
        )
        plan = resolve_javascript_plugins(
            selections,
            catalog=catalogs.plugins,
            target=target,
            entry_mode=entry_mode,
            project_root=project_root,
        )
        return _with_plugin_source_hashes(plan)
    except JavascriptPluginError as exc:
        raise ProjectBuildError(exc.code, str(exc)) from exc


def _active_plugin_bindings(
    plan: JavascriptPluginBindingPlan,
) -> tuple[JavascriptPluginBinding, ...]:
    return (
        *plan.policy_plugins,
        *plan.compiler_plugins,
        *plan.runtime_plugins,
    )


def _plugin_manifest_binding(
    binding: JavascriptPluginBinding,
    *,
    project_root: Path,
) -> Mapping[str, Any]:
    """Return a relocatable manifest view without changing emitter bindings."""

    payload = binding.to_dict()
    if not binding.module:
        return payload
    root = project_root.resolve()
    source = Path(binding.module).resolve()
    try:
        relative = source.relative_to(root).as_posix()
    except ValueError as exc:
        raise ProjectBuildError(
            "VF_AOT_PLUGIN_SOURCE",
            f"plugin '{binding.id}' source escapes project root: {source}",
        ) from exc
    payload["module"] = relative
    return payload


def _with_plugin_source_hashes(
    plan: JavascriptPluginBindingPlan,
) -> JavascriptPluginBindingPlan:
    def hashed(binding: JavascriptPluginBinding) -> JavascriptPluginBinding:
        if not binding.module:
            return binding
        source = Path(binding.module)
        if not source.is_file():
            raise JavascriptPluginError(
                "VF_AOT_PLUGIN_SOURCE",
                f"plugin '{binding.id}' source is not a file: {source}",
                binding.id,
            )
        return replace(
            binding,
            source_hash=hashlib.sha256(source.read_bytes()).hexdigest(),
        )

    return JavascriptPluginBindingPlan(
        policy_plugins=tuple(hashed(item) for item in plan.policy_plugins),
        compiler_plugins=tuple(hashed(item) for item in plan.compiler_plugins),
        runtime_plugins=tuple(hashed(item) for item in plan.runtime_plugins),
        planned_plugins=plan.planned_plugins,
    )


def _plugin_import_policy(
    supplied: Mapping[str, Any],
    plan: JavascriptPluginBindingPlan,
) -> Mapping[str, Any]:
    policy = dict(supplied)
    owners = [
        dict(item)
        for item in policy.get("owners", ())
        if isinstance(item, Mapping)
    ]
    for binding in _active_plugin_bindings(plan):
        owners.append(
            {
                "path": binding.module,
                "kind": "plugin",
                "id": binding.id,
                "export": binding.export,
                "completion": binding.completion,
            }
        )
    policy["owners"] = owners
    policy["plugin_dependencies"] = {
        item.id: list(item.dependencies)
        for item in _active_plugin_bindings(plan)
    }
    return policy


def _declared_host_extensions(
    config: Mapping[str, Any],
    *,
    legacy_ids: tuple[str, ...],
    catalog: object,
):
    if "host_extensions" not in config:
        config = {
            **config,
            "host_extensions": list(legacy_ids),
        }
    findings: list[object] = []
    resources = host_extension_resources(config, findings=findings)
    errors = [
        finding
        for finding in findings
        if str(getattr(finding, "severity", "error")) == "error"
    ]
    if errors:
        first = errors[0]
        raise ProjectBuildError(
            "VF_AOT_HOST_EXTENSION_CONFIG",
            (
                f"{getattr(first, 'rule_id', 'HOST_EXTENSION.CONFIG')}: "
                f"{getattr(first, 'message', str(first))}"
            ),
        )
    resolved = []
    for resource in resources:
        descriptor = catalog.get(resource.id)
        if descriptor is None:
            resolved.append(resource)
            continue
        contract = {
            "targets": tuple(descriptor.targets),
            "provides": tuple(descriptor.provides),
            "dependencies": tuple(descriptor.dependencies),
        }
        for field, expected in contract.items():
            declared = tuple(getattr(resource, field))
            if (
                field in resource.declared_contract_fields
                and declared != expected
            ):
                raise ProjectBuildError(
                    "VF_AOT_HOST_EXTENSION_CONFIG",
                    (
                        f"host_extension '{resource.id}' {field} "
                        "must match its registered descriptor"
                    ),
                )
        resolved.append(
            replace(
                resource,
                display_name=(
                    resource.display_name or descriptor.display_name
                ),
                description=(
                    resource.description or descriptor.description
                ),
                version=resource.version or descriptor.version,
                targets=contract["targets"],
                provides=contract["provides"],
                dependencies=contract["dependencies"],
            )
        )
    return tuple(resolved)


__all__ = [
    "BeforeCompileHook",
    "PreparedProjectBuild",
    "ProjectBuildError",
    "ProjectBuildRequest",
    "ProjectBuildResult",
    "build_project_aot",
    "prepare_project_build",
]
