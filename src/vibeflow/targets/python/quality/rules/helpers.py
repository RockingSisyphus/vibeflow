"""Shared fact access and diagnostic construction; these are not rules."""

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.quality.source_analysis.types import _SourceInfo
from vibeflow.targets.python.quality.policy_parameters import source_policy


def rule_effect_scope(params):
    scope = params.get("effect_scope", "none")
    if not isinstance(scope, str) or scope not in {"none", "terminal", "python_io", "global_state", "trusted"}:
        raise ValueError(f"unsupported rule effect_scope: {scope!r}")
    return scope


def source_subject(context):
    sources = context.require("source_context")
    type_key = context.subject["type_key"]
    node = next(item for item in sources.nodes if item.type_key == type_key)
    symbol = sources.symbol(node.path, node.symbol)
    return sources, node, symbol


def source_info(file, symbol=None):
    text = file.text if symbol is None else "\n".join(file.text.splitlines()[symbol.line - 1:symbol.end_line])
    return _SourceInfo(path=file.path, class_text=text, class_start_line=1, module_text=file.text)


def finding(context, rule_id, message, *, path="", line=1, column=1, severity="error", details=None, suggested_fix_type=""):

    return HealthFinding(rule_id=rule_id, severity=severity, object_type=str(context.subject.get("kind", "node")), object_id=str(context.subject.get("type_key", context.subject.get("id", ""))),
                         source_location={"path": path, "line": line, "column": column}, message=message,
                         failure_layer="implementation", rule_source="ruleset.selection", details=details or {}, suggested_fix_type=suggested_fix_type)


def violation_finding(context, violation):
    return finding(context, violation.rule_id, violation.message,
                   path=str(violation.source_location.get("path", "")), line=int(violation.source_location.get("line", 1)),
                   column=int(violation.source_location.get("column", 1)), severity=violation.severity,
                   details=dict(violation.details), suggested_fix_type=violation.suggested_fix_type)
