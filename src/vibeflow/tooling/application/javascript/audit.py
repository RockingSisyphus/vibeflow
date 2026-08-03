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
    catalogs: DescriptorCatalogs
    implementation_facts: ImplementationFacts
    plan: WorkflowPlan
    architecture: Mapping[str, object]
    import_policy: Mapping[str, Any]
    source_files: tuple[str, ...]
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
    compiled = _validate_graph_tree(
        graph,
        catalogs=catalogs,
        facts=facts,
        path=(),
        active_nodesets=(),
        compiled_by_path=compiled_by_path,
        used_node_types=used_node_types,
    )
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
        catalogs=catalogs,
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
        catalogs=catalogs,
        implementation_facts=facts,
        plan=plan,
        architecture=architecture,
        import_policy=import_policy,
        source_files=source_files,
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


def render_mermaid(result: JavascriptAuditResult) -> str:
    lines = ["flowchart TD"]
    for node in result.graph.nodes:
        label = f"{node.id}\\n{node.type_used}".replace('"', "'")
        flow_kind = result.compiled.flow_kinds.get(node.id, node.flow_kind)
        if flow_kind == FLOW_KIND_GLOBAL_STATE:
            shape = mermaid_shape_for_flow_kind(flow_kind)
            lines.append(
                f'  {node.id}@{{ shape: {shape}, label: "{label}" }}'
            )
        else:
            lines.append(f'  {node.id}["{label}"]')
    for edge in result.compiled.effective_edges:
        condition = f"|{edge.when}|" if edge.when else ""
        lines.append(f"  {edge.source} -->{condition} {edge.target}")
    return "\n".join(lines) + "\n"


def render_ascii(result: JavascriptAuditResult) -> str:
    lines = [
        f"workflow {result.plan.workflow_id} ({result.graph.entry_mode})",
    ]
    incoming = {
        node.id: [] for node in result.graph.nodes
    }
    for edge in result.compiled.effective_edges:
        incoming.setdefault(edge.target, []).append(edge.source)
    for node in result.graph.nodes:
        parents = ", ".join(sorted(incoming.get(node.id, ()))) or "entry"
        lines.append(f"- {node.id} [{node.type_used}] <- {parents}")
    return "\n".join(lines) + "\n"


def render_review_svg(result: JavascriptAuditResult) -> str:
    nodes = tuple(result.graph.nodes)
    width = 760
    row_height = 86
    height = max(140, 50 + len(nodes) * row_height)
    positions = {
        node.id: (40, 30 + index * row_height)
        for index, node in enumerate(nodes)
    }
    fragments: list[str] = []
    for edge in result.compiled.effective_edges:
        source = positions.get(edge.source)
        target = positions.get(edge.target)
        if source is None or target is None:
            continue
        x1, y1 = source
        x2, y2 = target
        fragments.append(
            f'<line x1="{x1 + 680}" y1="{y1 + 27}" '
            f'x2="{x2 + 680}" y2="{y2 + 27}" '
            'stroke="#64748b" stroke-width="2" marker-end="url(#arrow)"/>'
        )
    for node in nodes:
        x, y = positions[node.id]
        flow_kind = result.compiled.flow_kinds.get(node.id, node.flow_kind)
        if flow_kind == FLOW_KIND_GLOBAL_STATE:
            shape = (
                f'<path class="global-state-cloud" d="{_cloud_path(x, y, 680, 54)}" '
                'fill="#f8fafc" stroke="#334155"/>'
            )
        else:
            shape = (
                f'<rect x="{x}" y="{y}" width="680" height="54" rx="8" '
                'fill="#f8fafc" stroke="#334155"/>'
            )
        fragments.extend(
            [
                f'<g class="review-inline-fragment" data-node="{escape_xml(node.id)}" data-flow-kind="{escape_xml(flow_kind)}">',
                shape,
                f'<text x="{x + 16}" y="{y + 23}" font-family="sans-serif" font-size="15" font-weight="600">{escape_xml(node.id)}</text>',
                f'<text x="{x + 16}" y="{y + 43}" font-family="monospace" font-size="12" fill="#475569">{escape_xml(node.type_used)}</text>',
                "</g>",
            ]
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        'role="img" aria-roledescription="flowchart-review-columns">'
        '<defs><marker id="arrow" markerWidth="8" markerHeight="8" '
        'refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" '
        'fill="#64748b"/></marker></defs>'
        + "".join(fragments)
        + "</svg>\n"
    )


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
) -> CompiledGraph:
    compiled = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            target_features=TargetFeatureSet(target="javascript"),
            known_nodesets=frozenset(graph.nodesets),
            owner="pipeline" if not path else "nodeset:" + ".".join(path),
        )
    ).compiled_graph
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
            if not is_loop:
                _check_contract(
                    node,
                    nodeset.requires,
                    nodeset.provides,
                    owner=f"nodeset '{nodeset_key}'",
                    path=call_path,
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
            compiled_by_path[call_path] = child
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
        _check_contract(
            node,
            descriptor.contract.requires,
            descriptor.contract.provides,
            owner=f"node descriptor '{descriptor.type_key}'",
            path=call_path,
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
    return compiled


def _check_contract(
    node: object,
    requires: tuple[object, ...],
    provides: tuple[object, ...],
    *,
    owner: str,
    path: tuple[str, ...],
) -> None:
    mismatches: list[str] = []
    if tuple(getattr(node, "requires", ())) != tuple(requires):
        mismatches.append("requires")
    if tuple(getattr(node, "provides", ())) != tuple(provides):
        mismatches.append("provides")
    if mismatches:
        raise ProjectBuildError(
            "VF_AOT_CONTRACT_INVALID",
            f"graph call does not match {owner}: {', '.join(mismatches)}",
            path,
        )


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
    catalogs: DescriptorCatalogs,
    plugin_records: tuple[Mapping[str, object], ...],
    host_records: tuple[Mapping[str, object], ...],
    root_id: str,
    source_path: str,
) -> dict[str, object]:
    report = build_architecture_report(graph, compiled=compiled)
    return {
        "project_target": "javascript",
        "workflow": {
            "source": {"root_id": root_id, "path": source_path},
            "entry_mode": graph.entry_mode,
            **report,
        },
        "nodesets": {
            key: {
                "type_key": value.type_key,
                "status": value.status,
                "flow_kind": value.flow_kind,
                "requires": requirements_to_dicts(value.requires),
                "provides": providers_to_dicts(value.provides),
            }
            for key, value in sorted(graph.nodesets.items())
        },
        "node_types": {
            descriptor.type_key: {
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
            "base_lib": catalogs.base_libs.to_dict(),
            "capabilities": catalogs.capabilities.to_dict(),
            "host_extensions": list(host_records),
            "plugins": list(plugin_records),
        },
    }


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
