"""Architecture facts of a checked JavaScript graph; shared by audit and build."""
from pathlib import Path
from typing import Mapping
from vibeflow.core import CompiledGraph
from vibeflow.core.flow import GraphConfig, LOOP_DEFINITION_IDS, STATUS_PLANNED
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.descriptors import DescriptorCatalogs
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts
from vibeflow.core.inspection import build_architecture_report
from vibeflow.core.rules.selection import selection_data
from vibeflow.core.planned import effective_planned_behavior
from vibeflow.tooling.presentation.node_presentation import resolve_presentation

def build_architecture_facts(
    graph: GraphConfig,
    *,
    compiled: CompiledGraph,
    compiled_nodeset_types: Mapping[str, CompiledGraph],
    catalogs: DescriptorCatalogs,
    used_node_ids: frozenset[str],
    active_base_lib_ids: frozenset[str],
    plugin_records: tuple[Mapping[str, object], ...],
    root_id: str,
    source_path: str,
    findings: tuple = (),
    project_root=None,
    resource_use=None,
    roots=None,
    rule_report=None,
    global_config=None,
    effective_params=None,
) -> dict[str, object]:
    roots = {**({"@project": catalogs.source_roots[-1]} if len(catalogs.source_roots) > 1 else {}), **(roots or {})}
    from .status import node_health_classes
    if rule_report is not None:
        findings = rule_report.findings
    from vibeflow.tooling.architecture.entries import policy_facts
    from vibeflow.targets.shared.rule_support.capability_policy import policies_from_executions
    from vibeflow.core.graph_calls import graph_call_subjects
    paths = [(*subject.call_path, node.id) for subject in graph_call_subjects(graph) for node in subject.graph.nodes]
    policies = policies_from_executions((item for values in rule_report.results.values() for item in values), paths) if rule_report else {}
    health_classes = node_health_classes(graph, findings)
    adapted = {
        "node_definitions": {
            descriptor.id: {**descriptor.to_dict(),
                "declaration": getattr(descriptor, "declaration", descriptor).to_dict(),
                "effective_presentation": resolve_presentation(descriptor).to_dict(),
            }
            for descriptor in catalogs.nodes
        },
        "node_types": catalogs.node_types.to_dict(),
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
                    used_node_ids=used_node_ids,

                )
            },

            "plugins": list(plugin_records),
        },
    }

    from vibeflow.tooling.architecture.workflow import ArchitectureInputs, build_workflow_architecture
    def compile_graph(body):
        key = next(key for key, value in graph.nodeset_types.items() if value.graph is body)
        return body, compiled_nodeset_types[key]
    payload = build_workflow_architecture(ArchitectureInputs(graph=graph, compiled=compiled,
        target="javascript", descriptor=catalogs.nodes.get, compile_graph=compile_graph,
        node_definitions=adapted["node_definitions"], node_types=adapted["node_types"],
        resources=adapted["resources"], policies=policies, health_classes=health_classes,
        global_config=global_config or {},
        effective_params=effective_params or {},
        extras={"resource_use": resource_use.to_dict() if resource_use else None}))
    from vibeflow.core.rules.planning import selection_report
    payload["rule_selections"] = selection_report(graph, catalogs)
    if rule_report is not None:
        payload["rule_checks"] = rule_report.to_dict()
    if project_root is not None:
        from vibeflow.tooling.architecture.resources import resource_architecture
        from vibeflow.tooling.presentation.portable_paths import portable_paths
        sources = tuple(item for scope in rule_report.source_scopes.values() for item in scope["sources"]) if rule_report else ()
        payload["implementation_graph"] = resource_architecture(catalogs, project_root=project_root,
            resource_use=resource_use, selected_nodes=used_node_ids, source_facts=sources,
            findings=findings, roots=roots)
        from vibeflow.targets.javascript.build.driver_session import current_scope
        scope = current_scope()
        kernel_roots = {"@vibeflow/javascript": driver.resources for driver in scope.drivers.values()} if scope else {}
        payload = portable_paths(payload, roots={**(roots or {}), **kernel_roots}, primary_root=project_root)
    return payload


def _active_capability_ids(
    catalogs: DescriptorCatalogs,
    *,
    used_node_ids: frozenset[str],
) -> frozenset[str]:
    active = {
        requirement.id
        for type_key in used_node_ids
        for descriptor in (catalogs.nodes.get(type_key),)
        if descriptor is not None
        for requirement in descriptor.capabilities
    }

    return frozenset(active)


def build_prepared_architecture(prepared):
    """Adapt checked build inputs without compiling or interpreting source again."""
    inputs = prepared.presentation_inputs
    compiled_nodeset_types = dict(inputs["declarations"])

    def remember(graph, path=()):
        for node in graph.nodes:
            target = node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id
            definition = graph.nodeset_types.get(target)
            call = path + (node.id,)
            if definition is not None and call in inputs["compiled_by_path"]:
                compiled_nodeset_types.setdefault(target, inputs["compiled_by_path"][call])
                remember(definition.graph, call)

    remember(prepared.graph)
    return build_architecture_facts(prepared.graph, compiled=prepared.compiled,
        compiled_nodeset_types=compiled_nodeset_types, catalogs=prepared.catalogs,
        used_node_ids=frozenset(prepared.used_node_ids), active_base_lib_ids=frozenset(prepared.used_base_libs),
        plugin_records=prepared.declared_plugins,
        root_id=prepared.root.id, source_path=prepared.config_path.relative_to(prepared.root.path).as_posix(),
        project_root=prepared.root.path, resource_use=prepared.resource_use,
        roots={root.id:root.path for root in prepared.workspace.roots}, rule_report=prepared.rule_report,
        global_config=inputs.get("global_config", {}), effective_params=inputs.get("effective_params", {}))


def render_architecture(result):
    from vibeflow.tooling.architecture.documents import render_architecture_payload
    return render_architecture_payload(result.architecture)
