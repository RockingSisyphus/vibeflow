from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Mapping

from vibeflow.core.findings import HealthFinding, HealthReport

if TYPE_CHECKING:
    from vibeflow.core.compiler import CompiledGraph
    from vibeflow.core.flow import GraphConfig
    from vibeflow.targets.python.project.plugins import PluginRegistry
    from vibeflow.targets.python.quality.workflow.validation import _HealthValidationState

def _build_health_report(
    graph: GraphConfig,
    compiled: CompiledGraph | None,
    plugin_registry: PluginRegistry | None,
    state: _HealthValidationState,
    rule_phase: str | None = None,
) -> HealthReport:
    from vibeflow.targets.python.runtime.helpers import has_planned, planned_items

    errors: tuple[HealthFinding, ...] = tuple(state.errors)
    warnings: tuple[HealthFinding, ...] = tuple(state.warnings)
    skipped: tuple[HealthFinding, ...] = ()
    errors = _aggregate_findings(errors)
    warnings = _aggregate_findings(warnings)
    skipped = _aggregate_findings(skipped)
    return HealthReport(
        status=_health_status(list(errors), list(warnings)),
        errors=errors,
        warnings=warnings,
        skipped=skipped,
        info={
            **({"explicit_edges": [edge.pair for edge in compiled.explicit_edges],
                "data_edges": [edge.pair for edge in compiled.data_edges],
                "effective_edges": [edge.pair for edge in compiled.effective_edges]} if compiled is not None else {}),
            **({"rule_phase": rule_phase} if rule_phase is not None else {}),
            "mainline": state.mainline,
            "node_metrics": state.node_metrics,
            "node_effect_scopes": state.node_effect_scopes,
            "call_effect_policies": state.call_effect_policies,
            "nodeset_findings": state.nodeset_findings,
            "plugins": plugin_registry.to_dict() if plugin_registry is not None else {"plugins": []},
            "planned": [dict(item) for item in planned_items(graph)],
            "production_ready": not has_planned(graph),
            "rule_executions": [item.to_dict() for item in state.rule_executions],
            "workflow_rulesets": list(graph.rulesets),
        },
    )

def _aggregate_findings(findings: tuple[HealthFinding, ...]) -> tuple[HealthFinding, ...]:
    grouped: dict[tuple[object, ...], list[HealthFinding]] = {}
    order: list[tuple[object, ...]] = []
    for finding in findings:
        key = _finding_aggregation_key(finding)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(finding)
    return tuple(_aggregated_finding(grouped[key]) for key in order)

def _finding_aggregation_key(finding: HealthFinding) -> tuple[object, ...]:
    details = dict(finding.details)
    details.pop("rule_contexts", None)
    if finding.rule_id == "GRAPH.DATA.MISSING_DIRECT_PROVIDER":
        return (
            finding.rule_id,
            finding.definition_id,
            finding.severity,
            details.get("owner", ""),
            details.get("node", ""),
            details.get("required_type", finding.object_id),
            _canonical_value(details.get("direct_sources", ())),
        )
    stable_detail_fields = (
        "owner",
        "source",
        "target",
        "node",
        "path",
        "field",
        "required_type",
        "provider_key",
        "direct_sources",
        "downstream_sources",
        "downstream_nodes",
        "matched_sources",
        "unconditional_sources",
        "conditional_sources",
        "nodeset",
    )
    stable_details = tuple((field, _canonical_value(details.get(field))) for field in stable_detail_fields if field in details)
    return (
        finding.rule_id,
        finding.definition_id,
        finding.severity,
        finding.object_type,
        finding.object_id,
        finding.failure_layer,
        finding.message,
        _canonical_value(finding.source_location),
        stable_details,
        _canonical_value(details),
    )

def _aggregated_finding(group: list[HealthFinding]) -> HealthFinding:
    first = group[0]
    if len(group) == 1:
        return first
    details = dict(first.details)
    contexts = []
    for finding in group:
        for context in finding.details.get("rule_contexts", ()):
            if context not in contexts:
                contexts.append(context)
    if contexts:
        details["rule_contexts"] = contexts
    details.update(
        {
            "aggregated": True,
            "occurrences": len(group),
            "suppressed_duplicates": len(group) - 1,
        }
    )
    return HealthFinding(
        rule_id=first.rule_id,
        severity=first.severity,
        object_type=first.object_type,
        object_id=first.object_id,
        source_location=first.source_location,
        rule_source=first.rule_source,
        failure_layer=first.failure_layer,
        message=first.message,
        suggested_fix_type=first.suggested_fix_type,
        details=details,
        definition_id=first.definition_id, root_id=first.root_id, root_path=first.root_path, source_path=first.source_path,
    )

def _canonical_value(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)

def _health_status(errors: list[HealthFinding], warnings: list[HealthFinding]) -> str:
    if any(finding.failure_layer == "plugin" for finding in errors):
        return "ERROR"
    if errors:
        return "FAIL"
    return "CONCERNS" if warnings else "PASS"


__all__: list[str] = []
