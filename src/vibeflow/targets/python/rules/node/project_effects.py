"""Adapt shared effect judgments to optional ordinary-source warnings."""

from __future__ import annotations

import ast

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.quality.source_analysis.types import _SourceInfo
from vibeflow.targets.python.rules.node.policy import PurityPolicy
from vibeflow.targets.python.rules.node.effect_visitors import ModulePurityVisitor


class _SourceEffectVisitor(ModulePurityVisitor):
    def __init__(self, source, *, policy, effect_scope, resolved_calls):
        super().__init__(policy=policy,
            source=_SourceInfo(source.source_path, None, 1, source.text),
            node_class_name="", effect_scope=effect_scope,
            audit_all_definitions=True, resolved_calls=resolved_calls)
        self.ordinary_source = source
        self.findings = {}

    def _visit_module_statement(self, statement, *, reachable_helpers):
        # Ordinary source has no Node top-level, contract or input ABI. Review
        # calls in definitions and initializers using the same effect judgments.
        self.visit(statement)

    def _add(self, code, message, node, *, suggested_fix_type):
        if code in {"effect_import", "banned_import"}:
            rule_id = "QUALITY.SIDE_EFFECT.IMPORT"
        elif code in {"effect_call", "banned_call", "global_state"}:
            rule_id = "QUALITY.SIDE_EFFECT.CALL"
        else:
            return
        line, column = getattr(node, "lineno", 1), getattr(node, "col_offset", 0) + 1
        # Chained calls share a source position. Keep the complete operation
        # once, while preserving separately positioned operations on that line.
        self.findings.setdefault((rule_id, line, column), HealthFinding(
            rule_id=rule_id, severity="warning", object_type="file",
            object_id=self.ordinary_source.relative_path,
            source_location={"path":self.ordinary_source.source_path, "line":line, "column":column},
            message=message, suggested_fix_type="isolate_side_effect"))


def source_effect_findings(source: object, tree: ast.AST, *, policy: PurityPolicy,
                           effect_scope: str, resolved_calls=frozenset()) -> tuple[HealthFinding, ...]:
    visitor = _SourceEffectVisitor(source, policy=policy, effect_scope=effect_scope,
                                  resolved_calls=resolved_calls)
    visitor.visit(tree)
    return tuple(visitor.findings.values())
