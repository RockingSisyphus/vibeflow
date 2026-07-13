from __future__ import annotations

from pathlib import Path

from vibeflow.cli.reports import config_load_error_report, dedupe_findings, fail_report, graph_config_error_report
from vibeflow.compiler import GraphCompiler, GraphCompileError
from vibeflow.config.loader import ConfigLoadError, load_config_document
from vibeflow.config.resource_registries import discover_config_resource_registry_context
from vibeflow.config.resources import load_config_resources
from vibeflow.config.schema import collect_config_schema_findings
from vibeflow.data_contract import providers_to_dicts, requirements_to_dicts
from vibeflow.graph_config import GraphConfigError, parse_graph_config
from vibeflow.health.types import HealthReport
from vibeflow.graph_config.planned_behavior import project_root_for_config
from vibeflow.policy import default_effective_policy, resolve_effective_policy
from vibeflow.plugin import load_plugins_from_config


def validate_config_path(path: Path, *, policy_path: Path | None = None) -> HealthReport:
    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(path))

    registry_context = discover_config_resource_registry_context(document.data, config_path=path)
    plugin_registry, plugin_findings = load_plugins_from_config(
        document.data,
        base_path=registry_context.base_path,
        plugin_resource_registry=registry_context.plugin_resource_registry,
    )
    if plugin_findings:
        return HealthReport(status="ERROR", errors=tuple(plugin_findings), effective_policy=default_effective_policy().to_dict())
    resources, resource_findings = load_config_resources(
        document.data,
        base_path=registry_context.base_path,
        plugin_registry=plugin_registry,
        base_lib_registry=registry_context.base_lib_registry,
        plugin_resource_registry=registry_context.plugin_resource_registry,
        base_lib_paths=registry_context.base_lib_paths,
    )
    policy_result = resolve_effective_policy(document.data, config_path=path, explicit_policy_path=policy_path, plugin_registry=plugin_registry)
    effective_policy = policy_result.effective_policy.to_dict()
    schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *registry_context.findings, *resource_findings, *policy_result.findings))
    schema_errors = tuple(finding for finding in schema_findings if finding.severity == "error")
    schema_warnings = tuple(finding for finding in schema_findings if finding.severity == "warning")
    if schema_errors:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin", "base_lib"} for finding in schema_errors) else "FAIL"
        return HealthReport(
            status=status,
            errors=schema_errors,
            warnings=schema_warnings,
            effective_policy=effective_policy,
        )

    try:
        graph = parse_graph_config(document.data, project_root=project_root_for_config(path))
    except GraphConfigError as exc:
        return graph_config_error_report(exc, path=path, effective_policy=effective_policy)
    try:
        compiled = GraphCompiler().compile(graph)
    except GraphCompileError as exc:
        return fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology", effective_policy=effective_policy)
    return HealthReport(
        status="CONCERNS" if schema_warnings else "PASS",
        warnings=schema_warnings,
        info={
            "nodes": len(graph.nodes),
            "nodesets": sorted(graph.nodesets),
            "nodeset_imports": [dict(item) for item in document.nodeset_imports],
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
            "resources": resources.to_dict(),
            "available_resources": registry_context.available_resources.to_dict(),
        },
        effective_policy=effective_policy,
    )


def inspect_config_payload(path: Path, *, policy_path: Path | None = None) -> tuple[dict[str, object], int]:
    report = validate_config_path(path, policy_path=policy_path)
    payload: dict[str, object] = {"health": report.to_dict()}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    document = load_config_document(path)
    graph = parse_graph_config(document.data, project_root=project_root_for_config(path))
    compiled = GraphCompiler().compile(graph)
    payload["config"] = {
        "inputs": providers_to_dicts(graph.inputs),
        "outputs": requirements_to_dicts(graph.outputs),
        "nodes": [
            {
                "id": node.id,
                "type_used": node.type_used,
                "requires": requirements_to_dicts(node.requires),
                "provides": providers_to_dicts(node.provides),
                "status": node.status,
                "planned_behavior": node.planned_behavior.to_dict(),
                "similar_to": node.similar_to.to_dict(),
            }
            for node in graph.nodes
        ],
        "nodesets": [
            {
                "type_key": nodeset.type_key,
                "display_name": nodeset.display_name,
                "description": nodeset.description,
                "requires": requirements_to_dicts(nodeset.requires),
                "provides": providers_to_dicts(nodeset.provides),
                "status": nodeset.status,
                "planned_behavior": nodeset.planned_behavior.to_dict(),
                "node_count": len(nodeset.graph.nodes),
            }
            for nodeset in graph.nodesets.values()
        ],
        "nodeset_imports": [dict(item) for item in document.nodeset_imports],
        "resources": report.info.get("resources", {}),
        "max_steps": graph.max_steps,
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
    }
    return payload, 0
