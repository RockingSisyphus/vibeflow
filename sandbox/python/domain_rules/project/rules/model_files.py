"""File layout is checked at graph scope; Node Rules retain local views."""
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleResult


def check(context, inputs, params):
    sources = context.require("source_context")
    background = context.facts.get("global_source_context", sources)
    findings = []
    for symbol in sources.symbols:
        if symbol.name != "model_forward" or background.owners(symbol.id):
            continue
        findings.append(HealthFinding(rule_id="EXAMPLE.MODEL.LOCATION", severity="error",
            object_type="file", object_id=symbol.path, failure_layer="implementation",
            message="An unowned module model_forward does not belong to a model_block Node.",
            source_location={"path":symbol.path, "line":symbol.line, "column":1},
            details={"symbol":symbol.name, "ownership":[]}))
    return RuleResult(findings=tuple(findings))
