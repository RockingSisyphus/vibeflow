"""A plugin-defined source rule, deliberately advisory in this sandbox."""

import ast

from vibeflow.targets.python.sdk import rule
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleRecord, RuleResult


@rule(
    id="math.min_t",
    description="Count lowercase t in the declared Node class source.",
    scope="source",
    outputs={"count": "math.t_count.v1"},
    params_schema={"minimum": {"type": "integer", "minimum": 0}},
    params_defaults={"minimum": 10},
)
def check(context, inputs, params):
    sources = context.require("source_context")
    descriptor = context.subject["descriptor"]
    current = next(n for n in sources.nodes if n.definition_id == descriptor.id)
    symbol = sources.symbol(current.path, current.symbol)
    if symbol is None:
        raise ValueError("Node implementation symbol is unavailable")
    text = ast.get_source_segment(sources.file(current.path).text, symbol.node)
    if text is None:
        raise ValueError("Node implementation source is unavailable")
    evidence = {"actual": text.count("t"), "minimum": params["minimum"],
                "path": current.path, "line": symbol.line, "column": 1}
    findings = ()
    if evidence["actual"] < evidence["minimum"]:
        findings = (HealthFinding(
            rule_id="MATH.MIN_T", severity="warning", object_type="node",
            object_id=descriptor.id, rule_source="rule:math.min_t",
            message=f"Node source has {evidence['actual']} lowercase t characters; expected at least {evidence['minimum']}.",
            source_location={key: evidence[key] for key in ("path", "line", "column")},
            details={**evidence, "counting_scope": "declared implementation"},
        ),)
    return RuleResult({"count": RuleRecord("math.t_count.v1", evidence)}, findings)
