from __future__ import annotations

from pathlib import Path

from .cli_reports import config_load_error_report, dedupe_findings, fail_report, graph_config_error_report
from .compiler import GraphCompiler, GraphCompileError
from .config_loader import ConfigLoadError, load_config_document
from .config_schema import collect_config_schema_findings
from .graph_config import GraphConfigError, parse_graph_config
from .health_types import HealthReport
from .policy import default_effective_policy, resolve_effective_policy
from .plugin import load_plugins_from_config


def validate_config_path(path: Path, *, policy_path: Path | None = None) -> HealthReport:
    try:
        document = load_config_document(path)
    except ConfigLoadError as exc:
        return config_load_error_report(exc, object_type="config", object_id=str(path))

    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=path.parent)
    if plugin_findings:
        return HealthReport(status="ERROR", errors=tuple(plugin_findings), effective_policy=default_effective_policy().to_dict())
    policy_result = resolve_effective_policy(document.data, config_path=path, explicit_policy_path=policy_path, plugin_registry=plugin_registry)
    effective_policy = policy_result.effective_policy.to_dict()
    schema_findings = dedupe_findings((*collect_config_schema_findings(document.data), *policy_result.findings))
    if schema_findings:
        status = "ERROR" if any(finding.failure_layer in {"source", "syntax", "plugin"} for finding in schema_findings) else "FAIL"
        return HealthReport(
            status=status,
            errors=tuple(finding for finding in schema_findings if finding.severity == "error"),
            warnings=tuple(finding for finding in schema_findings if finding.severity == "warning"),
            effective_policy=effective_policy,
        )

    try:
        graph = parse_graph_config(document.data)
    except GraphConfigError as exc:
        return graph_config_error_report(exc, path=path, effective_policy=effective_policy)
    try:
        compiled = GraphCompiler().compile(graph)
    except GraphCompileError as exc:
        return fail_report(exc.rule_id, str(exc), "pipeline", "pipeline", "topology", effective_policy=effective_policy)
    return HealthReport(
        status="PASS",
        info={
            "nodes": len(graph.nodes),
            "nodesets": sorted(graph.nodesets),
            "nodeset_imports": [dict(item) for item in document.nodeset_imports],
            "explicit_edges": [edge.pair for edge in compiled.explicit_edges],
            "data_edges": [edge.pair for edge in compiled.data_edges],
            "effective_edges": [edge.pair for edge in compiled.effective_edges],
        },
        effective_policy=effective_policy,
    )


def inspect_config_payload(path: Path, *, policy_path: Path | None = None) -> tuple[dict[str, object], int]:
    report = validate_config_path(path, policy_path=policy_path)
    payload: dict[str, object] = {"health": report.to_dict()}
    if report.status not in {"PASS", "CONCERNS"}:
        return payload, 1
    document = load_config_document(path)
    graph = parse_graph_config(document.data)
    compiled = GraphCompiler().compile(graph)
    payload["config"] = {
        "inputs": list(graph.inputs),
        "nodes": [
            {"name": node.name, "type": node.node_type, "requires": list(node.requires), "provides": list(node.provides)}
            for node in graph.nodes
        ],
        "nodesets": [
            {
                "name": nodeset.name,
                "display_name": nodeset.display_name,
                "category": nodeset.category,
                "description": nodeset.description,
                "version": nodeset.version,
                "purity": nodeset.purity,
                "requires": list(nodeset.requires),
                "provides": list(nodeset.provides),
                "exports": list(nodeset.exports),
                "node_count": len(nodeset.graph.nodes),
            }
            for nodeset in graph.nodesets.values()
        ],
        "nodeset_imports": [dict(item) for item in document.nodeset_imports],
        "max_steps": graph.max_steps,
        "effective_edges": [{"from": edge.source, "to": edge.target, "when": edge.when} for edge in compiled.effective_edges],
    }
    return payload, 0
