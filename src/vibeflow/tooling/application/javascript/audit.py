"""Target-neutral JavaScript workflow validation and architecture snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape as escape_xml
import json
from pathlib import Path
from typing import Any, Mapping

from vibeflow.block_compiler import WorkflowPlan, compile_graph_plan
from vibeflow.core import (
    CompiledGraph,
    CoreCompileRequest,
    ImplementationFacts,
    TargetFeatureSet,
    compile_core,
)
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.descriptors import DescriptorCatalogs, PluginSelectionError
from vibeflow.core.flow import (
    IO_NODE_TYPE,
    LOOP_NODE_TYPES,
    STATUS_PLANNED,
    GraphConfig,
)
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.inspection import build_architecture_report
from vibeflow.targets.javascript.build.project_graph import (
    require_explicit_inputs,
)
from vibeflow.targets.javascript.build.project_paths import (
    javascript_options,
    safe_project_path,
)
from vibeflow.targets.javascript.build.project_resources import (
    schemas_for_types,
    target_neutral_import_policy,
)
from vibeflow.targets.javascript.build.toolchain import (
    AotToolchainError,
    AuditToolchainInfo,
    run_audit_driver,
)
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.frontend.facts import (
    JavascriptImplementationFactsError,
    target_neutral_implementation_facts_from_catalog,
    validate_javascript_descriptor_catalogs,
)
from vibeflow.tooling.project.config_loader import (
    ConfigDocument,
    load_workspace_config_document,
)
from vibeflow.tooling.project.descriptor_loader import (
    load_project_descriptor_catalogs,
)
from vibeflow.tooling.project.document_kinds import ARCHITECTURE_DOCUMENT_HEADER
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.tooling.project.host_extensions import host_extension_resources
from vibeflow.tooling.project.plugin_review import load_plugin_review_resources
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.workspace_model import WorkspaceConfig, WorkspaceRoot
from vibeflow.tooling.application.mermaid_shapes import (
    mermaid_shape_for_flow_kind,
)


@dataclass(frozen=True)
class JavascriptAuditRequest:
    workspace: str | Path | WorkspaceConfig
    config: str | Path
    node_command: str = "node"
    audit_sources: bool = True
    audit_registered_resources: bool = False


@dataclass(frozen=True)
class JavascriptAuditResult:
    workspace: WorkspaceConfig
    root: WorkspaceRoot
    document: ConfigDocument
    graph: GraphConfig
    compiled: CompiledGraph
    compiled_by_path: Mapping[tuple[str, ...], CompiledGraph]
    compiled_nodesets: Mapping[str, CompiledGraph]
    catalogs: DescriptorCatalogs
    implementation_facts: ImplementationFacts
    plan: WorkflowPlan
    architecture: Mapping[str, object]
    import_policy: Mapping[str, Any]
    source_files: tuple[str, ...]
    plugin_records: tuple[Mapping[str, object], ...] = ()
    host_records: tuple[Mapping[str, object], ...] = ()
    toolchain: AuditToolchainInfo | None = None

    @property
    def config_path(self) -> Path:
        return self.document.path


def audit_javascript_project(
    request: JavascriptAuditRequest,
) -> JavascriptAuditResult:
    """Validate one JS root without choosing browser or Node semantics."""

    config_path = Path(request.config).expanduser().resolve()
    workspace = (
        request.workspace
        if isinstance(request.workspace, WorkspaceConfig)
        else load_workspace_config(
            Path(request.workspace).expanduser().resolve()
        )
    )
    root = workspace.root_for_path(config_path)
    if root is None:
        raise ProjectBuildError(
            "VF_AOT_CONFIG_ROOT",
            f"config is not under a workspace root: {config_path}",
        )
    if root.project_target != "javascript":
        raise ProjectBuildError(
            "CLI.PROJECT_TARGET.MISMATCH",
            (
                f"JavaScript audit requires project_target='javascript', "
                f"found {root.project_target!r}"
            ),
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
        facts = target_neutral_implementation_facts_from_catalog(
            catalogs.nodes
        )
    except JavascriptImplementationFactsError as exc:
        raise ProjectBuildError(exc.code, exc.message) from exc
    document = load_workspace_config_document(config_path, workspace=workspace)
    graph = parse_graph_config(
        document.data,
        project_root=root.path,
        root_id=root.id,
        root_path=root.path,
        source_path=config_path,
    )
    require_explicit_inputs(graph, path=())
    compiled_by_path: dict[tuple[str, ...], CompiledGraph] = {}
    used_node_types: set[str] = set()
    compilation = _validate_graph_tree(
        graph,
        catalogs=catalogs,
        facts=facts,
        path=(),
        active_nodesets=(),
        compiled_by_path=compiled_by_path,
        used_node_types=used_node_types,
    )
    graph = compilation.workflow.graph
    compiled = compilation.compiled_graph
    compiled_nodesets = {
        type_key: compile_core(
            CoreCompileRequest(
                graph=nodeset.graph,
                implementation_facts=facts,
                target_features=TargetFeatureSet(target="javascript"),
                known_nodesets=frozenset(nodeset.graph.nodesets),
                owner=f"nodeset:{type_key}",
            )
        ).compiled_graph
        for type_key, nodeset in sorted(graph.nodesets.items())
    }
    plan = compile_graph_plan(
        graph,
        compiled,
        workflow_id=None,
        compiled_by_path=compiled_by_path,
        implementation_facts=facts,
        target_features=TargetFeatureSet(target="javascript"),
    )
    plugin_records, plugin_ids = _plugin_records(
        document.data,
        catalogs=catalogs,
    )
    host_records, host_extension_ids = _host_extension_records(
        document.data,
        root=root,
        catalogs=catalogs,
    )
    javascript = javascript_options(root)
    package_root = safe_project_path(
        root.path,
        javascript["package_root"],
        subject="javascript.package_root",
        require_directory=True,
    )
    external = set(javascript["external_packages"])
    planned_plugin_ids = frozenset(
        str(item.get("id", ""))
        for item in plugin_records
        if item.get("status") == "planned"
    )
    planned_host_extension_ids = frozenset(
        str(item.get("id", ""))
        for item in host_records
        if item.get("status") == "planned"
    )
    if request.audit_registered_resources:
        # Project quality owns the whole registered implementation catalog,
        # not only the workflow's active runtime closure.  Planned selections
        # remain declarations and therefore never cause their source to load.
        plugin_ids = tuple(
            descriptor.id
            for descriptor in catalogs.plugins
            if descriptor.id not in planned_plugin_ids
        )
        host_extension_ids = tuple(
            descriptor.id
            for descriptor in catalogs.host_extensions
            if descriptor.id not in planned_host_extension_ids
        )
    import_policy, source_files = target_neutral_import_policy(
        catalogs=catalogs,
        project_root=root.path,
        allowed_external=external,
        node_ids=(
            None
            if request.audit_registered_resources
            else frozenset(used_node_types)
        ),
        host_extension_ids=frozenset(host_extension_ids),
        plugin_ids=frozenset(plugin_ids),
    )
    toolchain: AuditToolchainInfo | None = None
    if request.audit_sources and source_files:
        try:
            audited = run_audit_driver(
                {
                    "typecheckFiles": list(source_files),
                    "importPolicy": _driver_import_policy(import_policy),
                },
                package_root=package_root,
                node_command=request.node_command,
            )
            toolchain = audited.toolchain
        except AotToolchainError as exc:
            raise ProjectBuildError(
                exc.code,
                str(exc),
                diagnostics=exc.diagnostics,
            ) from exc
    architecture = _architecture_payload(
        graph,
        compiled=compiled,
        compiled_nodesets=compiled_nodesets,
        catalogs=catalogs,
        used_node_types=frozenset(used_node_types),
        active_base_lib_ids=frozenset(
            str(owner.get("id", ""))
            for owner in import_policy.get("owners", ())
            if owner.get("kind") == "base_lib"
        ),
        plugin_records=plugin_records,
        host_records=host_records,
        root_id=root.id,
        source_path=config_path.relative_to(root.path).as_posix(),
    )
    return JavascriptAuditResult(
        workspace=workspace,
        root=root,
        document=document,
        graph=graph,
        compiled=compiled,
        compiled_by_path=dict(compiled_by_path),
        compiled_nodesets=compiled_nodesets,
        catalogs=catalogs,
        implementation_facts=facts,
        plan=plan,
        architecture=architecture,
        import_policy=import_policy,
        source_files=source_files,
        plugin_records=plugin_records,
        host_records=host_records,
        toolchain=toolchain,
    )


def render_architecture(result: JavascriptAuditResult) -> str:
    return (
        ARCHITECTURE_DOCUMENT_HEADER
        + json.dumps(
            result.architecture,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )


def inspect_payload(result: JavascriptAuditResult) -> dict[str, object]:
    graph = result.graph
    compiled = result.compiled
    return {
        "status": "PASS",
        "project_target": "javascript",
        "config": str(result.config_path),
        "workflow": {
            "entry_mode": graph.entry_mode,
            "inputs": providers_to_dicts(graph.inputs),
            "outputs": requirements_to_dicts(graph.outputs),
            "nodes": [
                {
                    "id": node.id,
                    "type_used": node.type_used,
                    "status": node.status,
                    "flow_kind": compiled.flow_kinds.get(
                        node.id,
                        node.flow_kind,
                    ),
                    "effect_scope": _effect_scope_label(
                        compiled,
                        node.id,
                        compiled.flow_kinds.get(node.id, node.flow_kind),
                    ),
                    "runtime_dispatch": _runtime_dispatch_label(
                        compiled,
                        node.id,
                    ),
                    "effective_execution_lock": (
                        _effective_lock_text(graph, node) or None
                    ),
                    "requires": requirements_to_dicts(node.requires),
                    "provides": providers_to_dicts(node.provides),
                }
                for node in graph.nodes
            ],
            "edges": [
                {
                    "from": edge.source,
                    "to": edge.target,
                    "when": edge.when,
                    "schedule": edge.pair
                    in {item.pair for item in compiled.schedule_edges},
                    "transfer": edge.pair
                    in {item.pair for item in compiled.transfer_edges},
                }
                for edge in compiled.effective_edges
            ],
        },
        "architecture": dict(result.architecture),
    }


def render_mermaid(
    result: JavascriptAuditResult,
    *,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
    mermaid_layout: str = "default",
) -> str:
    from vibeflow.tooling.application.javascript.review import render_mermaid as render

    return render(
        result,
        expand_nodesets=expand_nodesets,
        show_contract=show_contract,
        show_semantics=show_semantics,
        mermaid_layout=mermaid_layout,
    )


def render_ascii(
    result: JavascriptAuditResult,
    *,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
) -> str:
    from vibeflow.tooling.application.javascript.review import render_ascii as render

    return render(
        result,
        expand_nodesets=expand_nodesets,
        show_contract=show_contract,
        show_semantics=show_semantics,
    )


def render_review_svg(result: JavascriptAuditResult) -> str:
    from vibeflow.tooling.application.javascript.review import render_review_svg as render

    return render(result)


def _runtime_dispatch_label(compiled: CompiledGraph, node_id: str) -> str:
    value = getattr(compiled, "runtime_dispatches", {}).get(node_id)
    if value is True:
        return "detected"
    if value is False:
        return "none"
    return "unknown"


def _effect_scope_label(
    compiled: CompiledGraph,
    node_id: str,
    flow_kind: str,
) -> str:
    return compiled.effect_scopes.get(
        node_id,
        "global_state" if flow_kind == FLOW_KIND_GLOBAL_STATE else "none",
    )


def _effective_lock_text(graph: GraphConfig, node: object) -> str:
    node_lock = getattr(node, "execution_lock", None)
    if node_lock is not None:
        node_type = str(getattr(node, "type_used", ""))
        scope = (
            "block"
            if node_type in LOOP_NODE_TYPES or node_type in graph.nodesets
            else "node"
        )
        return f"{node_lock.key} ({scope})"
    if graph.execution_lock is not None:
        return f"{graph.execution_lock.key} (root, inherited)"
    return ""


def _cloud_path(x: float, y: float, width: float, height: float) -> str:
    """Return a scalable cloud outline contained by the requested box."""

    def point(px: float, py: float) -> str:
        return f"{x + width * px:.2f},{y + height * py:.2f}"

    return " ".join(
        (
            f"M {point(0.12, 0.96)}",
            f"C {point(0.04, 0.96)} {point(0.01, 0.78)} {point(0.06, 0.61)}",
            f"C {point(0.01, 0.42)} {point(0.08, 0.22)} {point(0.18, 0.31)}",
            f"C {point(0.22, 0.02)} {point(0.39, 0.00)} {point(0.44, 0.27)}",
            f"C {point(0.52, 0.08)} {point(0.66, 0.15)} {point(0.67, 0.39)}",
            f"C {point(0.76, 0.18)} {point(0.90, 0.30)} {point(0.87, 0.55)}",
            f"C {point(0.98, 0.54)} {point(1.00, 0.82)} {point(0.91, 0.94)}",
            f"C {point(0.78, 1.01)} {point(0.31, 1.00)} {point(0.12, 0.96)} Z",
        )
    )


def _validate_graph_tree(
    graph: GraphConfig,
    *,
    catalogs: DescriptorCatalogs,
    facts: ImplementationFacts,
    path: tuple[str, ...],
    active_nodesets: tuple[str, ...],
    compiled_by_path: dict[tuple[str, ...], CompiledGraph],
    used_node_types: set[str],
):
    compilation = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            target_features=TargetFeatureSet(target="javascript"),
            known_nodesets=frozenset(graph.nodesets),
            owner="pipeline" if not path else "nodeset:" + ".".join(path),
        )
    )
    graph = compilation.workflow.graph
    compiled = compilation.compiled_graph
    for node in graph.nodes:
        call_path = (*path, node.id)
        if node.status == STATUS_PLANNED:
            continue
        if node.type_used == IO_NODE_TYPE:
            continue
        is_loop = node.type_used in LOOP_NODE_TYPES
        is_nodeset = node.type_used in graph.nodesets and not is_loop
        if is_loop or is_nodeset:
            nodeset_key = node.loop.body if is_loop else node.type_used
            nodeset = graph.nodesets.get(nodeset_key)
            if nodeset is None:
                raise ProjectBuildError(
                    "VF_AOT_NODESET",
                    f"unknown nodeset '{nodeset_key}'",
                    call_path,
                )
            if nodeset_key in active_nodesets:
                chain = " -> ".join((*active_nodesets, nodeset_key))
                raise ProjectBuildError(
                    "VF_AOT_NODESET_RECURSION",
                    f"recursive nodeset calls cannot target AOT: {chain}",
                    call_path,
                )
            child = _validate_graph_tree(
                nodeset.graph,
                catalogs=catalogs,
                facts=facts,
                path=call_path,
                active_nodesets=(*active_nodesets, nodeset_key),
                compiled_by_path=compiled_by_path,
                used_node_types=used_node_types,
            )
            compiled_by_path[call_path] = child.compiled_graph
            continue
        descriptor = catalogs.nodes.get(node.type_used)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_NODE_UNKNOWN",
                f"node type '{node.type_used}' has no descriptor",
                call_path,
            )
        used_node_types.add(descriptor.type_key)
        if not any(
            implementation.language in {"javascript", "typescript"}
            for implementation in descriptor.implementations
        ):
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"node '{node.type_used}' has no JavaScript/TypeScript implementation",
                call_path,
            )
        for base_lib_id in descriptor.base_libs:
            if catalogs.base_libs.get(base_lib_id) is None:
                raise ProjectBuildError(
                    "VF_AOT_BASE_LIB_UNKNOWN",
                    f"unknown required base_lib '{base_lib_id}'",
                    call_path,
                )
        for requirement in descriptor.capabilities:
            capability = catalogs.capabilities.get(requirement.id)
            if capability is None:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_UNKNOWN",
                    f"node '{node.type_used}' requires unknown capability '{requirement.id}'",
                    call_path,
                )
            unknown = sorted(
                set(requirement.operations) - set(capability.operations)
            )
            if unknown:
                raise ProjectBuildError(
                    "VF_AOT_CAPABILITY_OPERATION",
                    (
                        f"node '{node.type_used}' requires unknown operations "
                        f"on capability '{requirement.id}': {unknown}"
                    ),
                    call_path,
                )
    used_types = {item.type for item in graph.inputs}
    used_types.update(item.type for item in graph.outputs)
    for node in graph.nodes:
        used_types.update(item.type for item in node.requires)
        used_types.update(item.type for item in node.provides)
    schemas_for_types(used_types, catalogs=catalogs)
    return compilation


def _plugin_records(
    config: Mapping[str, Any],
    *,
    catalogs: DescriptorCatalogs,
) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
    try:
        records = load_plugin_review_resources(
            config,
            catalog=catalogs.plugins,
        )
    except PluginSelectionError as exc:
        raise ProjectBuildError("VF_AOT_CONTRACT_INVALID", str(exc)) from exc
    planned_ids = {
        resource.record.id
        for resource in records
        if resource.status == "planned"
    }
    active: list[str] = []
    visiting: list[str] = []

    def visit(plugin_id: str) -> None:
        if plugin_id in active:
            return
        if plugin_id in planned_ids:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"implemented plugin depends on planned plugin '{plugin_id}'",
            )
        if plugin_id in visiting:
            start = visiting.index(plugin_id)
            cycle = " -> ".join((*visiting[start:], plugin_id))
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"plugin dependency cycle: {cycle}",
            )
        descriptor = catalogs.plugins.get(plugin_id)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"unknown implemented plugin '{plugin_id}'",
            )
        visiting.append(plugin_id)
        for dependency in descriptor.dependencies:
            visit(dependency)
        visiting.pop()
        active.append(plugin_id)

    for resource in records:
        if resource.status != "implemented":
            continue
        visit(resource.record.id)
    for plugin_id in active:
        descriptor = catalogs.plugins.get(plugin_id)
        assert descriptor is not None
        implementations = tuple(
            item
            for item in descriptor.implementations
            if item.language in {"javascript", "typescript"}
        )
        if not implementations:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"plugin '{descriptor.id}' has no JavaScript/TypeScript implementation",
            )
        if len({item.completion for item in implementations}) != 1:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"plugin '{descriptor.id}' has platform-dependent completion",
            )
    return (
        tuple(resource.to_dict() for resource in records),
        tuple(active),
    )


def _host_extension_records(
    config: Mapping[str, Any],
    *,
    root: WorkspaceRoot,
    catalogs: DescriptorCatalogs,
) -> tuple[tuple[Mapping[str, object], ...], tuple[str, ...]]:
    legacy = javascript_options(root)["host_extensions"]
    actual = config
    if "host_extensions" not in actual and legacy:
        actual = {**actual, "host_extensions": list(legacy)}
    findings: list[object] = []
    resources = host_extension_resources(actual, findings=findings)
    errors = [
        item
        for item in findings
        if str(getattr(item, "severity", "error")) == "error"
    ]
    if errors:
        first = errors[0]
        raise ProjectBuildError(
            "VF_AOT_CONTRACT_INVALID",
            str(getattr(first, "message", first)),
        )
    records: list[Mapping[str, object]] = []
    planned_ids = {
        resource.id for resource in resources if resource.status == "planned"
    }
    active: list[str] = []
    visiting: list[str] = []

    def visit(extension_id: str) -> None:
        if extension_id in active:
            return
        if extension_id in planned_ids:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                (
                    "implemented host_extension depends on planned "
                    f"host_extension '{extension_id}'"
                ),
            )
        if extension_id in visiting:
            start = visiting.index(extension_id)
            cycle = " -> ".join((*visiting[start:], extension_id))
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"host_extension dependency cycle: {cycle}",
            )
        descriptor = catalogs.host_extensions.get(extension_id)
        if descriptor is None:
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"unknown implemented host_extension '{extension_id}'",
            )
        visiting.append(extension_id)
        for dependency in descriptor.dependencies:
            visit(dependency)
        visiting.pop()
        active.append(extension_id)

    for resource in resources:
        descriptor = catalogs.host_extensions.get(resource.id)
        if descriptor is None and resource.status == "implemented":
            raise ProjectBuildError(
                "VF_AOT_CONTRACT_INVALID",
                f"unknown implemented host_extension '{resource.id}'",
            )
        if descriptor is not None:
            implementations = tuple(
                item
                for item in descriptor.implementations
                if item.language in {"javascript", "typescript"}
            )
            if resource.status == "implemented":
                if not implementations:
                    raise ProjectBuildError(
                        "VF_AOT_CONTRACT_INVALID",
                        (
                            f"host_extension '{resource.id}' has no "
                            "JavaScript/TypeScript implementation"
                        ),
                    )
                if any(
                    item.completion != "immediate"
                    for item in implementations
                ):
                    raise ProjectBuildError(
                        "VF_AOT_CONTRACT_INVALID",
                        (
                            f"host_extension '{resource.id}' factory must "
                            "be immediate"
                        ),
                    )
        records.append(resource.to_dict())
        if resource.status == "implemented":
            visit(resource.id)
    return tuple(records), tuple(active)

def _architecture_payload(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph,
    compiled_nodesets: Mapping[str, CompiledGraph],
    catalogs: DescriptorCatalogs,
    used_node_types: frozenset[str],
    active_base_lib_ids: frozenset[str],
    plugin_records: tuple[Mapping[str, object], ...],
    host_records: tuple[Mapping[str, object], ...],
    root_id: str,
    source_path: str,
) -> dict[str, object]:
    return {
        "project_target": "javascript",
        "workflow": _javascript_graph_document(
            graph,
            compiled,
            source={"root_id": root_id, "path": source_path},
            graph_lock_scope="root",
        ),
        "nodesets": {
            key: {
                "type_key": value.type_key,
                "source": _javascript_source_reference(value),
                "display_name": value.display_name,
                "description": value.description,
                "status": value.status,
                "flow_kind": value.flow_kind,
                "effect_scope": "none",
                "reachable_from_workflow": key in _reachable_javascript_nodesets(graph),
                "requires": requirements_to_dicts(value.requires),
                "provides": providers_to_dicts(value.provides),
                "global_config": dict(value.global_config),
                "body": (
                    _javascript_graph_document(
                        value.graph,
                        compiled_nodesets[key],
                        source=_javascript_source_reference(value),
                        graph_lock_scope="block",
                    )
                    if value.graph.nodes
                    else None
                ),
            }
            for key, value in sorted(graph.nodesets.items())
        },
        "node_types": {
            descriptor.type_key: {
                "display_name": descriptor.display_name,
                "description": descriptor.description,
                "category": descriptor.category,
                "version": descriptor.version,
                "flow_kind": descriptor.flow_kind,
                "contract": descriptor.contract.to_dict(),
                "implementations": [
                    item.to_dict() for item in descriptor.implementations
                    if item.language in {"javascript", "typescript"}
                ],
            }
            for descriptor in catalogs.nodes
        },
        "resources": {
            "data_schemas": catalogs.schemas.to_dict(),
            "base_lib": {
                key: value
                for key, value in catalogs.base_libs.to_dict().items()
                if key in active_base_lib_ids
            },
            "capabilities": {
                key: value
                for key, value in catalogs.capabilities.to_dict().items()
                if key in _active_capability_ids(
                    catalogs,
                    used_node_types=used_node_types,
                    host_records=host_records,
                )
            },
            "host_extensions": list(host_records),
            "plugins": list(plugin_records),
        },
    }


def _active_capability_ids(
    catalogs: DescriptorCatalogs,
    *,
    used_node_types: frozenset[str],
    host_records: tuple[Mapping[str, object], ...],
) -> frozenset[str]:
    active = {
        requirement.id
        for type_key in used_node_types
        for descriptor in (catalogs.nodes.get(type_key),)
        if descriptor is not None
        for requirement in descriptor.capabilities
    }
    for record in host_records:
        for provided in record.get("provides", ()):
            if isinstance(provided, Mapping):
                capability_id = str(provided.get("id", ""))
            else:
                capability_id = str(provided)
            if capability_id:
                active.add(capability_id)
    return frozenset(active)


def _javascript_graph_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    *,
    source: Mapping[str, str],
    graph_lock_scope: str,
) -> dict[str, object]:
    report = build_architecture_report(graph, compiled=compiled)
    return {
        "source": dict(source),
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "max_steps": graph.max_steps,
        "entry_mode": graph.entry_mode,
        "execution_lock": (
            {"key": graph.execution_lock.key, "scope": graph_lock_scope}
            if graph.execution_lock is not None
            else None
        ),
        "contains_global_state": bool(
            getattr(compiled, "contains_global_state", False)
        ),
        "summary": report.get("summary", {}),
        "entry_nodes": report.get("entry_nodes", []),
        "terminal_nodes": report.get("terminal_nodes", []),
        "god_nodes": report.get("god_nodes", []),
        "nodes": [
            _javascript_node_document(
                graph,
                compiled,
                node,
                source=source,
                graph_lock_scope=graph_lock_scope,
            )
            for node in graph.nodes
        ],
        "edges": [
            _javascript_edge_document(graph, compiled, edge)
            for edge in compiled.effective_edges
        ],
    }


def _javascript_node_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    node: object,
    *,
    source: Mapping[str, str],
    graph_lock_scope: str,
) -> dict[str, object]:
    node_id = str(getattr(node, "id", ""))
    type_used = str(getattr(node, "type_used", ""))
    is_loop = type_used in LOOP_NODE_TYPES
    target = getattr(getattr(node, "loop", None), "body", "") if is_loop else type_used
    nodeset = graph.nodesets.get(target)
    invokes = None
    if nodeset is not None:
        invokes = {
            "kind": "loop_body" if is_loop else "nodeset",
            "target": target,
            "target_status": nodeset.status,
        }
    flow_kind = compiled.flow_kinds.get(node_id, str(getattr(node, "flow_kind", "")))
    lock = getattr(node, "execution_lock", None)
    effective_lock = None
    if lock is not None:
        effective_lock = {
            "key": lock.key,
            "scope": "block" if invokes else "node",
            "inherited": False,
        }
    elif graph.execution_lock is not None:
        effective_lock = {
            "key": graph.execution_lock.key,
            "scope": graph_lock_scope,
            "inherited": True,
        }
    async_mode = str(getattr(node, "async_mode", ""))
    status = str(getattr(node, "status", "implemented"))
    contract_source = (
        "planned_config"
        if status == STATUS_PLANNED
        else "system_config"
        if type_used == IO_NODE_TYPE or is_loop
        else "nodeset"
        if nodeset is not None
        else "node_type"
    )
    return {
        "id": node_id,
        "type_used": type_used,
        "source": dict(source),
        "role": getattr(node, "metadata").to_dict(),
        "contract_source": contract_source,
        "flow_kind": flow_kind,
        "effect_scope": _effect_scope_label(compiled, node_id, flow_kind),
        "runtime_dispatch": _runtime_dispatch_label(compiled, node_id),
        "execution_lock": (
            {"key": lock.key, "scope": "block" if invokes else "node"}
            if lock is not None
            else None
        ),
        "effective_execution_lock": effective_lock,
        "contains_global_state": flow_kind == FLOW_KIND_GLOBAL_STATE,
        "status": status,
        "planned_behavior": (
            getattr(node, "planned_behavior").to_dict()
            if str(getattr(node, "status", "")) == STATUS_PLANNED
            else None
        ),
        "requires": requirements_to_dicts(getattr(node, "requires")),
        "provides": providers_to_dicts(getattr(node, "provides")),
        "join_policy": str(getattr(node, "join_policy", "")),
        "async": (
            {"mode": async_mode, "result_key": str(getattr(node, "result_key", "")) or None}
            if async_mode
            else None
        ),
        "loop": getattr(node, "loop").to_dict() or None,
        "io": getattr(node, "io").to_dict() or None,
        "invokes": invokes,
        "config": {
            "call": dict(getattr(node, "params")),
            "node_configs": dict(getattr(node, "node_config_overrides")),
            "allow_config_override": bool(getattr(node, "allow_config_override")),
        },
    }


def _javascript_edge_document(
    graph: GraphConfig,
    compiled: CompiledGraph,
    edge: object,
) -> dict[str, object]:
    pair = (str(getattr(edge, "source", "")), str(getattr(edge, "target", "")))
    roles = [
        name
        for name, values in (
            ("mainline", compiled.mainline_edges),
            ("data_bypass", compiled.data_bypass_edges),
            ("async", compiled.async_edges),
            ("schedule", compiled.schedule_edges),
            ("transfer", compiled.transfer_edges),
        )
        if pair in {item.pair for item in values}
    ]
    return {
        "from": pair[0],
        "to": pair[1],
        "when": str(getattr(edge, "when", "")),
        "roles": roles,
    }


def _javascript_source_reference(value: object) -> dict[str, str]:
    root_id = str(getattr(value, "root_id", ""))
    root_path = Path(str(getattr(value, "root_path", "") or ".")).resolve()
    source_path = Path(str(getattr(value, "source_path", "") or ".")).resolve()
    try:
        path = source_path.relative_to(root_path).as_posix()
    except ValueError:
        path = source_path.name
    return {"root_id": root_id, "path": path}


def _reachable_javascript_nodesets(graph: GraphConfig) -> frozenset[str]:
    reachable: set[str] = set()

    def visit(body: GraphConfig) -> None:
        for node in body.nodes:
            target = (
                node.loop.body
                if node.type_used in LOOP_NODE_TYPES
                else node.type_used
            )
            nodeset = body.nodesets.get(target)
            if nodeset is None or target in reachable:
                continue
            reachable.add(target)
            visit(nodeset.graph)

    visit(graph)
    return frozenset(reachable)


def _driver_import_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "owners": [dict(item) for item in policy.get("owners", ())],
        "nodeBaseLibs": dict(policy.get("node_base_libs", {})),
        "baseLibDependencies": dict(
            policy.get("base_lib_dependencies", {})
        ),
        "hostExtensionDependencies": dict(
            policy.get("host_extension_dependencies", {})
        ),
        "pluginDependencies": dict(policy.get("plugin_dependencies", {})),
        "allowedExternalPackages": list(
            policy.get("allowed_external_packages", ())
        ),
    }


__all__ = [
    "JavascriptAuditRequest",
    "JavascriptAuditResult",
    "audit_javascript_project",
    "inspect_payload",
    "render_ascii",
    "render_architecture",
    "render_mermaid",
    "render_review_svg",
]
