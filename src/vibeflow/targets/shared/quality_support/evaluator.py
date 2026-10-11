"""Pure, target-neutral project-quality evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from .models import (
    FileQuality,
    ProjectQualityFacts,
    QualityFinding,
    QualityPolicy,
    SourceQualityReport,
)


def evaluate_project_quality(
    facts: ProjectQualityFacts,
    policy: QualityPolicy | None = None,
    *,
    rulesets=None,
    rules=None,
    ruleset_catalog=None,
    handlers=None,
    entrypoint: str = "static",
    context=None,
) -> SourceQualityReport:
    """Run an explicit Rule selection over the supplied source scope.

    ``None`` and ``()`` request facts only. The composition root supplies
    resources, implementations and any default Rule selection.
    Resources and callables can be supplied by any composition root. Neither
    this function nor the Rule handlers discover additional files or Nodes.
    """
    from dataclasses import replace
    from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RulesetDescriptor, compile_ruleset, execute_rule_plan
    from vibeflow.targets.shared.quality_support.rule_report import project_quality_report

    active = policy or QualityPolicy()
    normalized = ProjectQualityFacts(facts.root, tuple(sorted(facts.files, key=lambda item: item.path)), facts.findings)
    resources = _resources_by_id(rules)
    sets = _resources_by_id(ruleset_catalog)
    selected = () if rulesets is None else (rulesets,) if isinstance(rulesets, (str, RuleDescriptor, RulesetDescriptor)) else tuple(rulesets)
    implementations = dict(handlers or {})
    base_context = context or RuleContext(subject={"kind": "source", "id": facts.root},
        scope={"root": facts.root, "files": tuple(item.path for item in normalized.files)}, phase=entrypoint)
    active_context = replace(base_context, facts={**base_context.facts, "project_facts": normalized}, phase=entrypoint)
    executions, selected_ids = [], []
    for item in selected:
        if isinstance(item, RuleDescriptor):
            resources[item.id] = item
            item = RulesetDescriptor("rule:" + item.id, (RuleCall("check", item.id),))
        elif isinstance(item, str) and item not in sets and item in resources:
            item = RulesetDescriptor("rule:" + item, (RuleCall("check", item),))
        plan = compile_ruleset(item, rules=resources, rulesets=sets, entrypoint=entrypoint)
        selected_ids.append(plan.ruleset_id)
        executions.append(execute_rule_plan(plan, active_context, handlers=implementations))
    return project_quality_report(normalized, active, tuple(executions), tuple(selected_ids))


def _resources_by_id(resources):
    if resources is None:
        return {}
    return dict(resources) if isinstance(resources, Mapping) else {item.id: item for item in resources}


def _dedupe_findings(
    findings: Sequence[QualityFinding],
) -> list[QualityFinding]:
    unique: dict[tuple[object, ...], QualityFinding] = {}
    for finding in findings:
        key = (
            finding.rule_id,
            finding.severity,
            finding.object_type,
            finding.object_id,
            json.dumps(
                finding.source_location,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
            finding.message,
            json.dumps(
                finding.details,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ),
        )
        unique.setdefault(key, finding)
    return list(unique.values())


__all__ = ["evaluate_project_quality"]
