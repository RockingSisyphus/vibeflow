from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.aot.builder import BuildRequest, BuildResult, build_aot
from vibeflow.aot.errors import ProjectBuildError
from vibeflow.aot.project_graph import (
    PreparationState as _PreparationState,
    prepare_graph as _prepare_graph,
    require_explicit_inputs as _require_explicit_inputs,
)
from vibeflow.aot.project_paths import (
    javascript_options as _javascript_options,
    safe_project_path as _safe_project_path,
)
from vibeflow.aot.project_resources import (
    base_lib_closure as _base_lib_closure,
    enriched_payload as _enriched_payload,
    host_extension_closure as _host_extension_closure,
    import_policy as _import_policy,
    required_capabilities as _required_capabilities,
    schemas_for_types as _schemas_for_types,
    used_schema_types as _used_schema_types,
)
from vibeflow.compiler import CompiledGraph, GraphCompiler
from vibeflow.config.loader import load_workspace_config_document
from vibeflow.config.resources import host_extension_resources
from vibeflow.descriptors import (
    BaseLibCatalog,
    DescriptorCatalogs,
    NodeCatalog,
    adapt_base_lib_registry,
    adapt_node_registry,
    load_project_descriptor_catalogs,
)
from vibeflow.graph_config import GraphConfig, parse_graph_config
from vibeflow.plugin import PluginRegistry, load_plugins_from_config
from vibeflow.portable import WorkflowPlan, build_workflow_plan
from vibeflow.runtime.config import (
    ConfigScope,
    normalize_config_scope,
    normalize_node_config_overrides,
)
from vibeflow.workspace import (
    build_workspace_node_registry,
    load_workspace_config,
    load_workspace_resources,
)
from vibeflow.workspace.types import (
    WorkspaceConfig,
    WorkspaceRoot,
    WorkspaceResourceRegistries,
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
    warnings: tuple[Mapping[str, str], ...] = ()


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


def prepare_project_build(request: ProjectBuildRequest) -> PreparedProjectBuild:
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
    if not config_path.is_file():
        raise ProjectBuildError(
            "VF_AOT_CONFIG",
            f"workflow config does not exist: {config_path}",
        )

    static_catalogs = load_project_descriptor_catalogs(
        root.path,
        project_config=root.config_path,
    )
    node_catalog = _merged_node_catalog(workspace, static_catalogs.nodes)
    resource_registries = _workspace_resource_registries(workspace)
    base_lib_catalog = _merged_base_lib_catalog(
        static_catalogs.base_libs,
        resource_registries.get(root.id),
    )
    catalogs = DescriptorCatalogs(
        nodes=node_catalog,
        base_libs=base_lib_catalog,
        schemas=static_catalogs.schemas,
        capabilities=static_catalogs.capabilities,
        host_extensions=static_catalogs.host_extensions,
        source_files=static_catalogs.source_files,
    )
    plugin_registry = _project_plugins(root, resource_registries.get(root.id))
    if plugin_registry.runtime_plugins():
        names = [
            str(getattr(plugin, "name", plugin.__class__.__name__))
            for plugin in plugin_registry.runtime_plugins()
        ]
        raise ProjectBuildError(
            "VF_AOT_RUNTIME_PLUGIN",
            f"Python runtime plugins cannot be included in JS AOT: {sorted(names)}",
        )

    document = load_workspace_config_document(config_path, workspace=workspace)
    graph = parse_graph_config(
        document.data,
        project_root=root.path,
        root_id=root.id,
        root_path=root.path,
        source_path=config_path,
    )
    _require_explicit_inputs(graph, path=())
    compiled = GraphCompiler().compile(
        graph,
        catalog=node_catalog,
        known_nodesets=set(graph.nodesets),
        plugin_registry=plugin_registry,
        owner="pipeline",
    )
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
        plugin_registry=plugin_registry,
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

    base_lib_order, _base_lib_implementations = _base_lib_closure(
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
    plan = build_workflow_plan(
        graph,
        compiled,
        workflow_id=request.workflow_id or None,
        source_by_type=state.source_by_type,
        compiled_by_path=state.compiled_by_path,
        params_by_path=state.params_by_path,
    )
    payload = _enriched_payload(
        plan,
        schemas=schemas,
        capabilities=capabilities,
        nodes=state.used_nodes,
        implementations=state.implementations,
    )
    javascript = _javascript_options(root)
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
    package_root = _safe_project_path(
        root.path,
        javascript["package_root"],
        subject="javascript.package_root",
        require_directory=True,
    )
    project_external = tuple(javascript["external_packages"])
    allowed_external = set(project_external)
    for descriptor in base_lib_order:
        allowed_external.update(descriptor.external_packages)
    for extension in host_extensions:
        allowed_external.update(extension["external_packages"])
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
    )


def build_project_aot(request: ProjectBuildRequest) -> ProjectBuildResult:
    prepared = prepare_project_build(request)
    result = build_aot(
        BuildRequest(
            plan=prepared.payload,
            project_root=prepared.root.path,
            package_root=prepared.package_root,
            out_dir=request.out_dir,
            target=request.target,
            profile=request.profile,
            implementation_by_type=prepared.implementation_by_type,
            external_packages=prepared.external_packages,
            import_policy=prepared.import_policy,
            host_extensions=prepared.host_extensions,
            entry_name=request.entry_name,
            sourcemap=request.sourcemap,
            replace=request.replace,
            html_template=request.html_template,
            app_entry=request.app_entry,
            node_command=request.node_command,
        )
    )
    return ProjectBuildResult(prepared=prepared, build=result)


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


def _merged_node_catalog(
    workspace: WorkspaceConfig,
    static_catalog: NodeCatalog,
) -> NodeCatalog:
    if not any(root.registry_ref for root in workspace.roots):
        return static_catalog
    registry = build_workspace_node_registry(workspace)
    if not registry.available():
        return static_catalog
    return adapt_node_registry(
        registry,
        static_catalog=static_catalog,
    ).catalog


def _workspace_resource_registries(
    workspace: WorkspaceConfig,
) -> Mapping[str, WorkspaceResourceRegistries]:
    if not any(root.registry_ref for root in workspace.roots):
        return {}
    registries, _resources, findings = load_workspace_resources(workspace)
    errors = [
        finding
        for finding in findings
        if str(getattr(finding, "severity", "")).lower() == "error"
    ]
    if errors:
        first = errors[0]
        raise ProjectBuildError(
            "VF_AOT_RESOURCE_REGISTRY",
            str(getattr(first, "message", first)),
        )
    return registries


def _merged_base_lib_catalog(
    static_catalog: BaseLibCatalog,
    registries: WorkspaceResourceRegistries | None,
) -> BaseLibCatalog:
    if (
        registries is None
        or not registries.has_base_lib_registry
        or not registries.base_libs.available()
    ):
        return static_catalog
    return adapt_base_lib_registry(
        registries.base_libs,
        static_catalog=static_catalog,
    ).catalog


def _project_plugins(
    root: WorkspaceRoot,
    registries: WorkspaceResourceRegistries | None,
) -> PluginRegistry:
    plugin_registry, findings = load_plugins_from_config(
        root.project_config,
        base_path=root.path,
        root_id=root.id,
        root_path=str(root.path),
        source_path=str(root.config_path),
        plugin_resource_registry=(
            registries.plugins if registries is not None else None
        ),
    )
    errors = [
        finding
        for finding in findings
        if str(getattr(finding, "severity", "error")).lower() == "error"
    ]
    if errors:
        first = errors[0]
        raise ProjectBuildError(
            "VF_AOT_PLUGIN",
            str(getattr(first, "message", first)),
        )
    return plugin_registry


__all__ = [
    "PreparedProjectBuild",
    "ProjectBuildError",
    "ProjectBuildRequest",
    "ProjectBuildResult",
    "build_project_aot",
    "prepare_project_build",
]
