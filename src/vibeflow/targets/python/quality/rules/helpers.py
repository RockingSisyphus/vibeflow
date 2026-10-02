"""Shared fact access and diagnostic construction; these are not rules."""

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy, _SourceInfo


def source_subject(context):
    sources = context.require("source_context")
    type_key = context.subject["type_key"]
    node = next(item for item in sources.nodes if item.type_key == type_key)
    symbol = sources.symbol(node.path, node.symbol)
    return sources, node, symbol


def source_info(file, symbol=None):
    text = file.text if symbol is None else "\n".join(file.text.splitlines()[symbol.line - 1:symbol.end_line])
    return _SourceInfo(path=file.path, class_text=text, class_start_line=1, module_text=file.text)


def source_policy(context, params=None):
    from dataclasses import replace
    policy = context.facts.get("purity_policy") or PurityPolicy()
    override = dict((params or {}).get("policy",{}))
    fields = {
        "node_source": {"max_lines":"max_source_lines","max_bytes":"max_source_bytes",
            "warn_lines":"warn_source_lines","warn_bytes":"warn_source_bytes"},
        "complexity": {name:name for name in ("max_functions","max_branches","max_nesting_depth","max_params","max_contract_keys")},
        "imports": {"allowed_roots":"allowed_import_roots","banned_roots":"banned_import_roots",
            "allowed_modules":"allowed_import_modules","banned_modules":"banned_import_modules"},
        "base_lib": {"allowed_paths":"allowed_base_lib_paths","allowed_modules":"allowed_base_lib_modules",
            "banned_modules":"banned_base_lib_modules"},
        "maintainability": {name:name for name in ("warn_call_chain_length","max_call_chain_length",
            "warn_dependency_chain_length","max_dependency_chain_length")},
    }
    changes = {}
    for group, values in override.items():
        if group not in fields or not hasattr(values,"items"):
            raise ValueError(f"unknown or invalid rule policy section: {group}")
        for name, value in values.items():
            target = fields[group].get(name)
            if target is None:
                raise ValueError(f"unknown rule policy parameter: {group}.{name}")
            changes[target] = tuple(value) if target.startswith(("allowed_","banned_")) else value
    return replace(policy,**changes)


def finding(context, rule_id, message, *, path="", line=1, column=1, severity="error", details=None, suggested_fix_type=""):

    return HealthFinding(rule_id=rule_id, severity=severity, object_type=str(context.subject.get("kind", "node")), object_id=str(context.subject.get("type_key", context.subject.get("id", ""))),
                         source_location={"path": path, "line": line, "column": column}, message=message,
                         failure_layer="implementation", rule_source="ruleset.selection", details=details or {}, suggested_fix_type=suggested_fix_type)


def violation_finding(context, violation):
    return finding(context, violation.rule_id, violation.message,
                   path=str(violation.source_location.get("path", "")), line=int(violation.source_location.get("line", 1)),
                   column=int(violation.source_location.get("column", 1)), severity=violation.severity,
                   details=dict(violation.details), suggested_fix_type=violation.suggested_fix_type)
