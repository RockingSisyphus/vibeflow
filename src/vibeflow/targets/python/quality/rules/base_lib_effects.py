"""BaseLib module structure and diagnostics over the shared effect traversal."""

from vibeflow.core.findings import HealthFinding
from vibeflow.targets.python.quality.source_analysis.ast_rules import module_assignment_is_allowed, module_statement_kind
from vibeflow.targets.python.quality.source_analysis.visitors import _EffectVisitor


class _BaseLibEffectVisitor(_EffectVisitor):
    def __init__(self, *, path, module, policy, effect_scope="none", resolved_calls=frozenset()):
        self.path, self.module = path, module
        self.findings = []
        self._init_effect_state(policy=policy, effect_scope=effect_scope, resolved_calls=resolved_calls)

    def visit_Module(self, node):
        self._prepare_effect_module(node)
        self._visit_module_body(node, self._visit_module_statement)

    def _visit_module_statement(self, statement):
        kind = module_statement_kind(statement)
        if kind in {"import", "definition"}:
            self.visit(statement)
        elif kind == "assignment":
            if self.effect_scope != "global_state" and not module_assignment_is_allowed(statement) and statement.value not in self._sdk_calls:
                self._add("global_state", "base_lib must not hold mutable module-level state", statement)
            # Includes initializers and module aliases; the structure policy
            # never grants permission to their actual effects.
            self.visit(statement)
        elif kind != "docstring":
            self._add("BASE_LIB.TOP_LEVEL_SIDE_EFFECT",
                "base_lib top level may only contain imports, definitions, immutable constants, and docstrings", statement)

    def _add(self, code, message, node, *, suggested_fix_type=""):
        diagnostic = {"effect_import":"BASE_LIB.BANNED_IMPORT", "banned_import":"BASE_LIB.BANNED_IMPORT",
            "effect_call":"BASE_LIB.SIDE_EFFECT_CALL", "banned_call":"BASE_LIB.SIDE_EFFECT_CALL",
            "global_state":"BASE_LIB.GLOBAL_STATE"}.get(code, code)
        self.findings.append(HealthFinding(rule_id=diagnostic, message=message, severity="error",
            object_type="base_lib", object_id=self.module,
            source_location={"path":self.path, "line":getattr(node,"lineno",1), "column":getattr(node,"col_offset",0)+1},
            suggested_fix_type=suggested_fix_type))
