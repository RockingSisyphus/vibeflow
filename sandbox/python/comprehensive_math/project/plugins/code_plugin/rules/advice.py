"""Consume an engine-bound typed record without rescanning Node source."""

from vibeflow.targets.python.sdk import rule
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleResult


@rule(id="math.t_advice", scope="source", inputs={"count": "math.t_count.v1"})
def check(context, inputs, params):
    record = inputs["count"]
    evidence = record.value
    if evidence["actual"] >= evidence["minimum"]:
        return RuleResult()
    return RuleResult(findings=(HealthFinding(
        rule_id="MATH.T_ADVICE", severity="warning", object_type="node",
        object_id=context.subject["descriptor"].id,
        rule_source="rule:math.t_advice",
        source_location={key: evidence[key] for key in ("path", "line", "column")},
        message="The source measurement reached this dependent rule; review the Node convention.",
        details={"actual": evidence["actual"], "minimum": evidence["minimum"],
                 "record_type": record.type_id, "suggestion": "Review the declared implementation."},
    ),))
