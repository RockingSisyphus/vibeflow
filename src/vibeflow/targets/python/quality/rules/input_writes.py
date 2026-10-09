"""Explicitly selected finite input write policy for Python Node entries."""
import ast
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import source_subject, finding
from vibeflow.targets.python.quality.source_analysis.input_tracking import direct_input_writes
from vibeflow.targets.python.quality.source_analysis.types import MUTATING_METHODS


def input_writes(context, inputs, params):
    if context.subject.get("kind") != "node":
        return RuleResult()
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol._node, ast.ClassDef):
        return RuleResult(state="unavailable")
    member = sources.class_members(symbol).get("run_pure")
    if member is None:
        return RuleResult(state="unavailable")
    methods = params.get("mutating_methods", sorted(MUTATING_METHODS))
    findings = {}
    for statement in direct_input_writes(member._node, mutating_methods=methods):
        key = (statement.lineno, statement.col_offset)
        findings[key] = finding(context, "NODE.PURITY.INPUT_MUTATION",
            "selected input-write policy forbids a direct write to entry inputs or a simple local alias",
            path=member.path, line=statement.lineno, column=statement.col_offset+1,
            suggested_fix_type="fix_node")
    return RuleResult(findings=tuple(findings.values()))
