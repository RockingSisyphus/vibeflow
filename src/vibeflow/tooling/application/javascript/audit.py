"""Target-neutral JavaScript workflow validation and architecture snapshots."""

from __future__ import annotations

from vibeflow.core.rules.selection import selection_data

from vibeflow.targets.javascript.build.driver_session import check_scope

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
from vibeflow.targets.shared.quality_support import QualityPolicy
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy
from vibeflow.tooling.application.javascript.rule_defaults import workflow_rule_defaults
from vibeflow.targets.javascript.build.project_paths import (
    javascript_options,
    safe_project_path,
)
from vibeflow.targets.javascript.build.project_resources import (
    driver_import_policy,
    schemas_for_types,
    target_neutral_import_policy,
)
from vibeflow.targets.javascript.build.toolchain import (
    AotToolchainError,
    AuditToolchainInfo,
    DriverQualityResult,
    run_audit_driver,
)
from vibeflow.targets.javascript.quality.rules import JavascriptRuleReport, source_node_calls, run_javascript_rules, run_javascript_workflow_rules
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.frontend.facts import (
    JavascriptImplementationFactsError,
    target_neutral_implementation_facts_from_catalog,
    apply_call_effect_scopes,
    validate_javascript_descriptor_catalogs,
)
from vibeflow.tooling.project.config_loader import (
    ConfigDocument,
    load_workspace_config_document,
)
from vibeflow.tooling.project.descriptor_loader import (
    load_workflow_catalogs,
)
from vibeflow.tooling.project.document_kinds import ARCHITECTURE_DOCUMENT_HEADER
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.tooling.project.plugin_review import load_plugin_review_resources
from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.workspace_model import WorkspaceConfig, WorkspaceRoot
from vibeflow.tooling.presentation.node_presentation import resolve_presentation
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
    quality_facts_by_root: Mapping[str, DriverQualityResult] | None = None
    quality_policy: QualityPolicy | None = None
    catalogs: DescriptorCatalogs | None = None


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
    warnings: tuple[Mapping[str, object], ...] = ()
    plugin_records: tuple[Mapping[str, object], ...] = ()
    host_records: tuple[Mapping[str, object], ...] = ()
    toolchain: AuditToolchainInfo | None = None
    rule_report: JavascriptRuleReport | None = None
    rule_facts: Mapping[str, Any] | None = None

    @property
    def config_path(self) -> Path:
        return self.document.path


@check_scope
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

    catalogs = request.catalogs or load_workflow_catalogs(
        root.path,
        project_config=root.config_path, workflow_config=config_path, workspace=workspace, node_command=request.node_command,
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
    javascript = javascript_options(root)
    package_root = safe_project_path(root.path, javascript["package_root"], subject="javascript.package_root", require_directory=True)
    rule_plugin_records, rule_plugin_ids = _plugin_records(document.data, catalogs=catalogs)
    host_records, host_extension_ids = _host_extension_records(document.data, root=root, catalogs=catalogs)
    rule_host_records, rule_host_ids = host_records, host_extension_ids
    if request.audit_registered_resources:
        planned_plugins = {item["id"] for item in rule_plugin_records if item.get("status") == "planned"}
        planned_hosts = {item["id"] for item in rule_host_records if item.get("status") == "planned"}
        rule_plugin_ids = tuple(item.id for item in catalogs.plugins if item.id not in planned_plugins)
        rule_host_ids = tuple(item.id for item in catalogs.host_extensions if item.id not in planned_hosts)
    rule_import_policy, _ = target_neutral_import_policy(
        catalogs=catalogs, project_root=root.path, allowed_external=set(javascript["external_packages"]),
        node_ids=None if request.audit_registered_resources else frozenset(source_node_calls(graph)), host_extension_ids=frozenset(rule_host_ids), plugin_ids=frozenset(rule_plugin_ids),
    )
    rule_report = run_javascript_rules(graph, catalogs, project_root=root.path, package_root=package_root,
                                     phase="static", import_policy=rule_import_policy, node_command=request.node_command, evaluate_sources=request.audit_sources, include_registered=request.audit_registered_resources, prefetched_quality=(request.quality_facts_by_root or {}).get(str(root.path)),
                                     quality_policy=request.quality_policy or javascript_quality_policy(structure_limits=getattr(root, "quality_structure", None)))
    rule_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if rule_errors:
        first = rule_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
    rule_report = run_javascript_workflow_rules(graph, catalogs, compiled_by_path={}, node_report=rule_report, project_root=root.path, package_root=package_root, phase="import", node_command=request.node_command, evaluate_sources=request.audit_sources,
        rule_defaults=workflow_rule_defaults(catalogs, javascript["nodeset_max_depth"]),
        quality_policy=request.quality_policy or javascript_quality_policy(structure_limits=getattr(root, "quality_structure", None)))
    rule_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if rule_errors:
        first = rule_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
    facts = target_neutral_implementation_facts_from_catalog(catalogs.nodes, effect_policies=rule_report.policies)
    width_warnings = ()
    javascript = javascript_options(root)
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
        call_effect_scopes=rule_report.call_effect_scopes,
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
    implementation_warnings = ()
    if request.audit_sources and source_files:
        try:
            audited = run_audit_driver(
                {
                    "typecheckFiles": list(source_files),
                    "importPolicy": driver_import_policy(import_policy),
                },
                package_root=package_root,
                node_command=request.node_command,
            )
            toolchain = audited.toolchain
        except AotToolchainError as exc:
            raise ProjectBuildError(
                exc.code,
                str(exc),
                diagnostics=(*exc.diagnostics, *width_warnings),
            ) from exc
    rule_report = run_javascript_workflow_rules(graph, catalogs, compiled_by_path={(): compiled, **compiled_by_path}, compiled_nodesets=compiled_nodesets, node_report=rule_report, project_root=root.path, package_root=package_root, rule_defaults=workflow_rule_defaults(catalogs, javascript["nodeset_max_depth"]), node_command=request.node_command, evaluate_sources=request.audit_sources,
                                                 quality_policy=request.quality_policy or javascript_quality_policy(structure_limits=getattr(root, "quality_structure", None)))
    workflow_errors = tuple(item for item in rule_report.findings if item.severity == "error")
    if workflow_errors:
        first = workflow_errors[0]
        raise ProjectBuildError(first.rule_id, first.message, diagnostics=tuple(item.to_dict() for item in rule_report.findings))
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
        findings=rule_report.findings,
    )
    from vibeflow.core.rules.planning import selection_report
    architecture["rule_selections"] = selection_report(graph, catalogs)
    architecture["rule_checks"] = rule_report.to_dict()
    from vibeflow.tooling.presentation.resource_architecture import resource_architecture
    architecture["implementation_graph"] = resource_architecture(catalogs, project_root=root.path,
        source_facts=tuple(item for scope in rule_report.source_scopes.values() for item in scope["sources"]),
        selections=document.data, selected_nodes=used_node_types, findings=rule_report.findings,
        roots={item.id:item.path for item in workspace.roots})
    from vibeflow.tooling.presentation.portable_paths import portable_paths
    architecture = portable_paths(architecture, roots={item.id:item.path for item in workspace.roots}, primary_root=root.path)
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
        warnings=(*width_warnings, *implementation_warnings, *(item.to_dict() for item in rule_report.findings if item.severity == "warning")),
        plugin_records=plugin_records,
        host_records=host_records,
        toolchain=toolchain,
        rule_report=rule_report, rule_facts=rule_report.facts,
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




def _effect_scope_label(
    compiled: CompiledGraph,
    node_id: str,
    flow_kind: str,
) -> str:
    return compiled.effect_scopes.get(
        node_id,
        "unconstrained",
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




def _validate_graph_tree(
    graph: GraphConfig,
    *,
    catalogs: DescriptorCatalogs,
    facts: ImplementationFacts,
    path: tuple[str, ...],
    active_nodesets: tuple[str, ...],
    compiled_by_path: dict[tuple[str, ...], CompiledGraph],
    used_node_types: set[str],
    call_effect_scopes: Mapping,
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
    from dataclasses import replace
    compiled = apply_call_effect_scopes(compilation.compiled_graph, graph, call_effect_scopes, path)
    compilation = replace(compilation, compiled_graph=compiled)
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
                call_effect_scopes=call_effect_scopes,
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
            {**config, "plugins": list(catalogs.lifecycle_selections)},
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


def _host_extension_records(config, *, root, catalogs):
    from vibeflow.tooling.application.javascript.host_selection import declared_hosts, active_host_ids
    resources = declared_hosts(config, catalog=catalogs.host_extensions)
    active = active_host_ids(tuple(item.id for item in resources if item.status == "implemented"),
        catalog=catalogs.host_extensions, planned=frozenset(item.id for item in resources if item.status == "planned"))
    for identifier in active:
        descriptor = catalogs.host_extensions.require(identifier)
        implementations = tuple(item for item in descriptor.implementations
                                if item.language in {"javascript", "typescript"})
        if not implementations:
            raise ProjectBuildError("VF_AOT_CONTRACT_INVALID",
                f"host_extension '{identifier}' has no JavaScript/TypeScript implementation")
        if any(item.completion != "immediate" for item in implementations):
            raise ProjectBuildError("VF_AOT_CONTRACT_INVALID",
                f"host_extension '{identifier}' factory must be immediate")
    return tuple(item.to_dict() for item in resources), active


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
    findings: tuple = (),
) -> dict[str, object]:
    from vibeflow.tooling.application.javascript.presentation_status import node_health_classes
    health_classes = node_health_classes(graph, findings)
    return {
        "project_target": "javascript",
        "workflow": _javascript_graph_document(
            graph,
            compiled,
            source={"root_id": root_id, "path": source_path},
            graph_lock_scope="root",
            catalogs=catalogs,
            health_classes=health_classes,
        ),
        "nodesets": {
            key: {
                "type_key": value.type_key,
                "source": _javascript_source_reference(value),
                "display_name": value.display_name,
                "description": value.description,
                "status": value.status,
                "expand": value.expand,
                "flow_kind": value.flow_kind,
                "effect_scope": "unavailable" if value.status == STATUS_PLANNED else "unconstrained",
                "rulesets": selection_data(value.graph.rulesets),
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
                        catalogs=catalogs,
                        health_classes=health_classes,
                    )
                    if value.graph.nodes
                    else None
                ),
            }
            for key, value in sorted(graph.nodesets.items())
        },
        "node_types": {
            descriptor.type_key: {**descriptor.to_dict(),
                "effective_presentation": resolve_presentation(descriptor).to_dict(),
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
    catalogs: DescriptorCatalogs,
    health_classes: Mapping[tuple[int, str], str] | None = None,
) -> dict[str, object]:
    report = build_architecture_report(graph, compiled=compiled)
    return {
        "source": dict(source),
        "rulesets": selection_data(graph.rulesets),
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
                catalogs=catalogs,
                health_classes=health_classes,
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
    catalogs: DescriptorCatalogs,
    health_classes: Mapping[tuple[int, str], str] | None = None,
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
    descriptor = catalogs.nodes.get(type_used)
    native_class = "externalDependency" if descriptor is not None and descriptor.external and nodeset is None else "loopNode" if is_loop else "nodesetNode" if nodeset is not None else "documentNode" if flow_kind == "document" else "defaultNode"
    planned = status == STATUS_PLANNED or nodeset is not None and nodeset.status == STATUS_PLANNED
    presentation = resolve_presentation(descriptor, native_class=native_class, status_class="plannedNode" if planned else (health_classes or {}).get((id(graph), node_id), ""), call_style=getattr(node, "style", None), flow_kind=flow_kind, node=node, compiled=compiled)
    return {
        "id": node_id,
        "type_used": type_used,
        "source": dict(source),
        "role": getattr(node, "metadata").to_dict(),
        "presentation": presentation.to_dict(),
        "rulesets": selection_data(nodeset.graph.rulesets) if nodeset is not None else selection_data(node.rulesets if node.rulesets is not None else descriptor.rulesets) if descriptor else None,
        "selected_rulesets": selection_data(nodeset.graph.rulesets) if nodeset is not None else selection_data(node.rulesets if node.rulesets is not None else descriptor.rulesets) if descriptor else [],
        "tags": list(descriptor.tags) if descriptor else [],
        "metadata": dict(descriptor.metadata) if descriptor else {},
        "contract_source": contract_source,
        "flow_kind": flow_kind,
        "effect_scope": "unavailable" if planned else _effect_scope_label(compiled, node_id, flow_kind),

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
