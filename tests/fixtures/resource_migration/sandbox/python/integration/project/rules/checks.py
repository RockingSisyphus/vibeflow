"""Explicit Rule resources replace the former policy review hooks."""

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleResult


def finding(context, inputs, params):
    graph = context.require("graph")
    findings = [HealthFinding(rule_id="SANDBOX.PLUGIN.GRAPH_WARNING", severity="warning",
        object_type="pipeline", object_id="pipeline", failure_layer="rule",
        message="sandbox graph Rule warning", suggested_fix_type="fix_config")]
    findings.extend(HealthFinding(rule_id="SANDBOX.PLUGIN.NODE_WARNING", severity="warning",
        object_type="node", object_id=node.id, failure_layer="rule",
        message="sandbox Node Rule warning", suggested_fix_type="fix_node")
        for node in graph.nodes if node.id == "add")
    return RuleResult(findings=tuple(findings))


def fail(context, inputs, params):
    raise RuntimeError("rule boom")


def missing_record(context, inputs, params):
    return RuleResult()


def bad_shape(context, inputs, params):
    return ["not", "a", "RuleResult"]
