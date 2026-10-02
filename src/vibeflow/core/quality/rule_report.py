"""Consume typed review records without assuming Ruleset-local call names."""

from dataclasses import fields, replace
import json
from collections.abc import Mapping

from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.models import DirectoryQuality, PrefixClusterQuality, QualityReport, QualityThresholds
from vibeflow.core.rules.models import plain


_RECORD_FIELDS = {
    "vibeflow.module_graph.v1": "dependency_graph",
    "vibeflow.module_chain.v1": "longest_dependency_chain",
    "vibeflow.directories.v1": "directory_graph",
    "vibeflow.clusters.v1": "prefix_clusters",
    "vibeflow.structure_summary.v1": "structure_summary",
}


def project_quality_report(facts, policy, executions, checked_rulesets):
    from vibeflow.core.quality.evaluator import _dedupe_findings
    findings = list(facts.findings)
    records = {name: [] for name in _RECORD_FIELDS.values()}
    promised = set()
    threshold_values = {}
    for execution in executions:
        findings.extend(execution.findings)
        for invocation in execution.plan.invocations:
            promised.update(_RECORD_FIELDS[kind] for kind in invocation.rule.outputs.values() if kind in _RECORD_FIELDS)
            if invocation.rule.id.startswith("vibeflow.quality."):
                for name in {item.name for item in fields(QualityThresholds)}.intersection(invocation.params):
                    value = invocation.params[name]
                    if isinstance(value, int) and not isinstance(value, bool):
                        threshold_values.setdefault(name, set()).add(value)
            result = execution.results[invocation.id]
            if result.state != "completed":
                if not any(item.severity == "error" for item in result.findings):
                    findings.append(HealthFinding(rule_id="RULE.EXECUTION.UNAVAILABLE", severity="error",
                        object_type="rule", object_id=invocation.id, definition_id=invocation.rule.id,
                        failure_layer="rule", message=f"selected rule did not complete ({result.state})",
                        details={"state": result.state, "ruleset": execution.plan.ruleset_id}))
                continue
            for record in result.records.values():
                name = _RECORD_FIELDS.get(record.type_id)
                if name is not None:
                    records[name].append((execution.plan.ruleset_id + "/" + invocation.id, record.value))
    availability = {name: "available" if values else "unavailable" if name in promised else "not_selected"
                    for name, values in records.items()}
    graph, chains, directories, clusters, summaries = {}, [], [], [], []
    for name, values in records.items():
        for origin, value in values:
            try:
                if name == "dependency_graph":
                    if not isinstance(value, Mapping) or any(not isinstance(edges, (tuple, list)) or any(not isinstance(edge, str) for edge in edges) for edges in value.values()):
                        raise ValueError("module graph must map module names to module lists")
                    for module, edges in value.items():
                        graph.setdefault(module, set()).update(edges)
                elif name == "longest_dependency_chain":
                    if not isinstance(value, (tuple, list)) or any(not isinstance(item, str) for item in value):
                        raise ValueError("module chain must contain module names")
                    chains.append(tuple(value))
                elif name == "directory_graph":
                    directories.extend(_objects(value, DirectoryQuality))
                elif name == "prefix_clusters":
                    clusters.extend(_objects(value, PrefixClusterQuality))
                elif name == "structure_summary":
                    if not isinstance(value, Mapping):
                        raise ValueError("structure summary must be an object")
                    summaries.append((origin, plain(value)))
            except (TypeError, ValueError) as exc:
                availability[name] = "unavailable"
                findings.append(HealthFinding(rule_id="RULE.REPORT.RECORD_INVALID", severity="error",
                    object_type="rule", object_id=origin, failure_layer="rule", message=str(exc), details={"record": name}))
    findings = _dedupe_findings(findings)
    incomplete = any(execution.status == "ERROR" for execution in executions) or any(state == "unavailable" for state in availability.values())
    syntax_error = any(item.severity == "error" and item.code.startswith("QUALITY.SYNTAX.") for item in facts.findings)
    status = "FAIL" if syntax_error else "ERROR" if incomplete else "FAIL" if any(item.severity == "error" for item in findings) else "CONCERNS" if any(item.severity == "warning" for item in findings) else "PASS"
    thresholds = replace(policy.thresholds, **{key: next(iter(values)) for key, values in threshold_values.items() if len(values) == 1})
    return QualityReport(status=status, root=facts.root, thresholds=thresholds, files=facts.files,
        dependency_graph={key: tuple(sorted(value)) for key, value in sorted(graph.items())},
        longest_dependency_chain=max(chains, key=lambda item: (len(item), item), default=()),
        findings=tuple(findings), directory_graph=_unique(directories), prefix_clusters=_unique(clusters),
        structure_summary=_summaries(summaries), checked_rulesets=checked_rulesets,
        rule_executions=tuple(execution.to_dict() for execution in executions), record_availability=availability)


def _objects(value, kind):
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{kind.__name__} record must be a list")
    for item in value:
        if isinstance(item, kind):
            yield item
        elif isinstance(item, Mapping):
            yield kind(**plain(item))
        else:
            raise ValueError(f"{kind.__name__} record item must be an object")


def _unique(values):
    seen = {}
    for item in values:
        seen.setdefault(json.dumps(item.to_dict(), sort_keys=True), item)
    return tuple(seen.values())


def _summaries(values):
    unique = {}
    for origin, value in values:
        unique.setdefault(json.dumps(value, sort_keys=True), (origin, value))
    if not unique:
        return {}
    snapshots = tuple(unique.values())
    if len(snapshots) == 1:
        return snapshots[0][1]
    first = snapshots[0][1]
    common = {key: value for key, value in first.items() if all(snapshot.get(key) == value for _, snapshot in snapshots[1:])}
    return {**common, "rule_summaries": [{"origin": origin, "value": value} for origin, value in snapshots]}


__all__ = ["project_quality_report"]
