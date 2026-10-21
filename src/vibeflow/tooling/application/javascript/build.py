from __future__ import annotations

from vibeflow.targets.javascript.build.driver_session import check_scope

from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping

from vibeflow.targets.javascript.build.builder import BuildRequest, BuildResult, build_aot
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy
from vibeflow.targets.javascript.build.project_graph import (
    PreparationState as _PreparationState,
    prepare_graph as _prepare_graph,
)
from vibeflow.targets.javascript.quality.rules import JavascriptRuleReport, source_node_calls, run_javascript_rules, run_javascript_workflow_rules
from vibeflow.targets.javascript.build.project_paths import (
    javascript_options as _javascript_options,
    safe_project_path as _safe_project_path,
)
from vibeflow.targets.javascript.build.project_resources import base_lib_closure as _base_lib_closure, target_neutral_import_policy, required_capabilities as _required_capabilities, schemas_for_types as _schemas_for_types, used_schema_types as _used_schema_types
from vibeflow.core import (
    CompiledGraph,
    CoreCompileRequest,
    ImplementationFacts,
    TargetFeatureSet,
    compile_core,
)
from vibeflow.tooling.project.config_loader import load_workspace_config_document


from vibeflow.core.descriptors import DescriptorCatalogs
from vibeflow.targets.javascript.frontend.facts import (
    JavascriptImplementationFactsError,
    implementation_facts_from_catalog,
    apply_call_effect_scopes,
    validate_javascript_descriptor_catalogs,
)
from vibeflow.tooling.project.resources import prepare_workflow_catalogs
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
    preview_root: str | Path | None = None


@dataclass(frozen=True)
class PreparedProjectBuild:
    workspace: WorkspaceConfig
    root: WorkspaceRoot
    config_path: Path
    package_root: Path
    rule_report: JavascriptRuleReport
    graph: GraphConfig
    compiled: CompiledGraph
    catalogs: DescriptorCatalogs
    plan: WorkflowPlan
    javascript_bindings: JavascriptBindingPlan
    import_policy: Mapping[str, Any]
    external_packages: tuple[str, ...]
    used_node_ids: tuple[str, ...]
    used_base_libs: tuple[str, ...]
    used_capabilities: tuple[str, ...]




    declared_plugins: tuple[Mapping[str, Any], ...] = ()
    planned_plugins: tuple[str, ...] = ()
    plugin_bindings: tuple[Mapping[str, Any], ...] = ()
    plugin_annotations: tuple[Mapping[str, Any], ...] = ()
    plugin_audit_sources: tuple[str, ...] = ()
    warnings: tuple[Mapping[str, object], ...] = ()
    presentation_inputs: object | None = None


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


@check_scope
def prepare_project_build(
    request: ProjectBuildRequest,
    *,
    before_compile_hooks: tuple[BeforeCompileHook, ...] = (),
) -> PreparedProjectBuild:
    """Load one workflow and execute its selected static and import rules."""

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

    from vibeflow.tooling.project.preparation import ProjectPreparation
    preparation = ProjectPreparation(workspace, root=root, workflow=config_path, node_command=request.node_command)
    from vibeflow.tooling.project.config_schema import ConfigSchemaError
    try:
        prepared_resources = preparation.workflow_resources(config_path)
    except ConfigSchemaError as exc:
        raise ProjectBuildError(exc.code, str(exc), diagnostics=exc.diagnostics) from exc
    catalogs = prepared_resources.catalogs
    governance = preparation.review()
    governance_errors = tuple(item for item in governance.findings if item.severity == "error")
    if governance_errors:
        raise ProjectBuildError(governance_errors[0].rule_id, governance_errors[0].message,
                                diagnostics=tuple(item.to_dict() for item in governance.findings))

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

    document = prepared_resources.document
    graph = prepared_resources.graph
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


    rule_import_policy, _ = target_neutral_import_policy(resource_inventory=prepared_resources.resource_inventory, catalogs=catalogs, project_root=root.path, allowed_external=set(javascript["external_packages"]), node_ids=frozenset(source_node_calls(graph)),  plugin_ids=frozenset(item.id for item in _active_plugin_bindings(plugin_plan)))
    rule_report = run_javascript_rules(graph, catalogs, project_root=root.path, package_root=package_root, phase="static", target=request.target, import_policy=rule_import_policy, node_command=request.node_command,
                                     quality_policy=javascript_quality_policy())
    rule_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if rule_errors:
        first = rule_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
    rule_report = run_javascript_workflow_rules(graph, catalogs, compiled_by_path={}, node_report=rule_report, project_root=root.path, package_root=package_root, phase="import", target=request.target, node_command=request.node_command,
        quality_policy=javascript_quality_policy())
    rule_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if rule_errors:
        first = rule_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
    implementation_facts = implementation_facts_from_catalog(node_catalog, target=request.target, effect_policies=rule_report.policies)
    plugin_report = JavascriptBuildPluginReport()
    build_plugins = plugin_plan.compiler_plugins
    if build_plugins:
        try:
            with JavascriptBuildPluginRunner(
                plugin_plan,
                package_root=package_root,
                target=request.target,
                workflow_id=request.workflow_id or config_path.stem,
                node_command=request.node_command,
                catalogs=catalogs,
            ) as plugin_runner:
                plugin_runner.before_compile(graph)
                compilation = _compile_core_compilation(
                    graph,
                    implementation_facts=implementation_facts,
                    target_features=target_features,
                    known_nodeset_types=set(graph.nodeset_types),
                    owner="pipeline",
                )
                graph = compilation.workflow.graph
                compiled = apply_call_effect_scopes(compilation.compiled_graph, graph, rule_report.call_effect_scopes)
                plugin_runner.after_compile(graph, compiled)
                plugin_report = plugin_runner.report()
        except JavascriptPluginError as exc:
            raise ProjectBuildError(exc.code, str(exc), details=exc.details) from exc
    else:
        compilation = _compile_core_compilation(
            graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodeset_types=set(graph.nodeset_types),
            owner="pipeline",
        )
        graph = compilation.workflow.graph
        compiled = apply_call_effect_scopes(compilation.compiled_graph, graph, rule_report.call_effect_scopes)
    compilation = replace(compilation, compiled_graph=compiled)
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
        compile_graph=lambda child_graph, known_nodeset_types, owner: _compile_core_graph(
            child_graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodeset_types=known_nodeset_types,
            owner=owner,
        ),
        compiled_by_path={},
        params_by_path={},
        source_by_definition={},
        implementations={},
        used_nodes={},
        used_types=set(),
        call_effect_scopes=rule_report.call_effect_scopes,
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

    from vibeflow.core.rules.planning import graph_rule_subjects
    declarations = {subject.definition.type_key: subject.graph
        for subject in graph_rule_subjects(graph) if subject.declaration_only}
    compiled_declarations = {key: state.compile_graph(child, set(child.nodeset_types), "nodeset:" + key)
        for key, child in declarations.items()}
    rule_report = run_javascript_workflow_rules(graph, catalogs, compiled_by_path={(): compiled, **state.compiled_by_path}, node_report=rule_report, project_root=root.path, package_root=package_root, target=request.target, node_command=request.node_command,
        compiled_nodeset_types=compiled_declarations, quality_policy=javascript_quality_policy())
    workflow_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if workflow_errors:
        first = workflow_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
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
    )
    schema_types = set(state.used_types)
    schema_types.update(_used_schema_types(graph, state.used_nodes, capabilities))
    schemas = _schemas_for_types(schema_types, catalogs=catalogs)
    plan = compile_graph_plan(
        graph,
        compiled,
        workflow_id=request.workflow_id or None,
        source_by_definition=state.source_by_definition,
        compiled_by_path=state.compiled_by_path,
        params_by_path=state.params_by_path,
        implementation_facts=implementation_facts,
        target_features=target_features,
    )

    from vibeflow.targets.shared.rule_support.capability_policy import policies_from_executions
    from vibeflow.block_compiler.policies import apply_call_policies
    paths = [(*block.path, call.id) for block in plan.blocks for call in block.nodes]
    plan = apply_call_policies(plan, policies_from_executions(
        (execution for values in rule_report.results.values() for execution in values), paths))



    project_external = tuple(javascript["external_packages"])
    allowed_external = set(project_external)
    for descriptor in base_lib_order:
        allowed_external.update(descriptor.external_packages)

    for binding in _active_plugin_bindings(plugin_plan):
        allowed_external.update(binding.external_packages)
    import_policy, _ = target_neutral_import_policy(resource_inventory=prepared_resources.resource_inventory, catalogs=catalogs, project_root=root.path,
        allowed_external=allowed_external, node_ids=frozenset(state.used_nodes),

        plugin_ids=frozenset(item.id for item in _active_plugin_bindings(plugin_plan)))
    javascript_bindings = build_javascript_binding_plan(
        plan,
        implementations=state.implementations,
        base_libs_by_definition={
            key: tuple(descriptor.base_libs)
            for key, descriptor in state.used_nodes.items()
        },
        capabilities_by_definition={
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

        runtime_plugins=plugin_plan.runtime_plugins,
        import_policy=import_policy,
    )
    warnings = [*(item.to_dict() for item in rule_report.findings if item.severity == "warning")]
    return PreparedProjectBuild(
        workspace=workspace,
        root=root,
        config_path=config_path,
        package_root=package_root,
        rule_report=rule_report,
        graph=graph,
        compiled=compiled,
        catalogs=catalogs,
        plan=plan,
        import_policy=import_policy,
        external_packages=project_external,
        used_node_ids=tuple(sorted(state.used_nodes)),
        used_base_libs=tuple(item.id for item in base_lib_order),
        used_capabilities=tuple(item.id for item in capabilities),




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
        plugin_audit_sources=tuple(
            item.module for item in _active_plugin_bindings(plugin_plan)
        ),
        warnings=tuple(warnings),
        javascript_bindings=javascript_bindings,
        presentation_inputs={"compiled_by_path": dict(state.compiled_by_path),
                        "declarations": compiled_declarations, "selections": document.data},
    )


def _compile_core_graph(
    graph: GraphConfig,
    *,
    implementation_facts: ImplementationFacts,
    target_features: TargetFeatureSet,
    known_nodeset_types: set[str],
    owner: str,
) -> CompiledGraph:
    """Call the public Core compile boundary and return its graph view."""

    return _compile_core_compilation(
        graph,
        implementation_facts=implementation_facts,
        target_features=target_features,
        known_nodeset_types=known_nodeset_types,
        owner=owner,
    ).compiled_graph


def _compile_core_compilation(
    graph: GraphConfig,
    *,
    implementation_facts: ImplementationFacts,
    target_features: TargetFeatureSet,
    known_nodeset_types: set[str],
    owner: str,
):
    return compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=implementation_facts,
            target_features=target_features,
            known_nodeset_types=frozenset(known_nodeset_types),
            owner=owner,
        )
    )


@check_scope
def build_project_aot(request: ProjectBuildRequest) -> ProjectBuildResult:
    prepared = prepare_project_build(request)
    from vibeflow.tooling.presentation.preview.diagnostics import incidental_preview, preview_operation
    from vibeflow.tooling.application.javascript.presentation.preview import publish_build_preview
    record = incidental_preview(publish_build_preview, prepared=prepared, preview_root=request.preview_root)
    with preview_operation(record):
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
    raw = list(catalogs.lifecycle_selections)
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
    from os.path import relpath
    payload["module"] = Path(relpath(source, root)).as_posix()
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
        compiler_plugins=tuple(hashed(item) for item in plan.compiler_plugins),
        runtime_plugins=tuple(hashed(item) for item in plan.runtime_plugins),
        planned_plugins=plan.planned_plugins,
    )


__all__ = [
    "BeforeCompileHook",
    "PreparedProjectBuild",
    "ProjectBuildError",
    "ProjectBuildRequest",
    "ProjectBuildResult",
    "build_project_aot",
    "prepare_project_build",
]
