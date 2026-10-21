"""Convert Target analysis diagnostics into rule findings."""
from typing import Any, Mapping
from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules import RuleContext
from vibeflow.core.rules.models import plain


def rule_finding(raw: Mapping[str, Any], rule_id: str, context: RuleContext) -> Finding:
    location = raw.get("source_location")
    if not isinstance(location, Mapping):
        location = {name: raw[name] for name in ("path", "line", "column") if name in raw}
        if raw.get("file"):
            location = {**location, "path": raw["file"]}
    details = dict(raw.get("details", {}))
    if isinstance(raw.get("owner"), Mapping):
        details["source_owner"] = plain(raw["owner"])
    rule = context.facts.get("catalogs").rules.get(rule_id) if context.facts.get("catalogs") is not None else None
    call_paths = context.subject.get("source_call_paths", ()) if rule is not None and rule.scope == "source" else context.subject.get("call_paths", ())
    details["rule_id"] = rule_id
    if "definition_id" in context.subject:
        details["definition_id"] = context.subject["definition_id"]
    if context.subject.get("kind") != "nodeset_definition":
        details.setdefault("call_paths", plain(call_paths))
    default_subject = "node" if "definition_id" in context.subject else context.subject.get("kind", "workflow")
    subject_id = context.subject.get("definition_id", context.subject.get("id", context.subject.get("workflow", "")))
    return HealthFinding(
        code=str(raw.get("code", raw.get("rule_id", rule_id))),
        severity=raw.get("severity", "error"),
        subject_type=str(raw.get("subject_type", raw.get("object_type", default_subject))),
        subject_id=str(raw.get("subject_id", raw.get("object_id", subject_id))),
        message=str(raw.get("message", "Rule rejected implementation")),
        source_location=location, details=details, rule_source="rule:" + rule_id, failure_layer="implementation",
    )
