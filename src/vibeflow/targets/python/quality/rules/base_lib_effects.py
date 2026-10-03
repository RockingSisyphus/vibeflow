"""Side-effect judgments for an explicitly selected Python library source."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Mapping

from vibeflow.core.quality.implementation import (
    ImplementationLimits,
    ImplementationMetrics,
    evaluate_base_lib_implementation,
)
from vibeflow.targets.python.project.base_lib_types import (
    BaseLibDependencySummary,
    BaseLibFinding,
    BaseLibModuleReport,
    BaseLibScanReport,
)
from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    boolop_branch_count,
    import_aliases_from_node,
    imported_module_roots,
    import_modules,
    module_assignment_is_allowed,
    module_matches,
    module_statement_kind,
    record_assignment_aliases,
)
from vibeflow.targets.python.quality.source_analysis.effects import (
    call_violation,
    dynamic_namespace_reference,
    import_violation_code,
    process_argv_import_is_forbidden,
    process_argv_reference,
    system_exit_is_forbidden,
    system_exit_reference,
)
from vibeflow.targets.python.quality.source_analysis.types import PurityPolicy


FORBIDDEN_PROJECT_IMPORT_PARTS = {
    "boundary", "boundaries", "nodes", "plugin", "plugins", "runtime",
}


class _BaseLibAstScanner(ast.NodeVisitor):
    def __init__(self, *, path: str, module: str, policy: PurityPolicy, effect_scope: str = "none") -> None:
        self.effect_scope = effect_scope
        self.path = path
        self.module = module
        self.policy = policy
        self.imports: set[str] = set()
        self.findings: list[BaseLibFinding] = []
        self.import_aliases: dict[str, str] = {"Path": "pathlib.Path"}
        self.imported_module_roots: set[str] = set()

    def visit_Module(self, node: ast.Module) -> None:
        from vibeflow.targets.python.quality.source_analysis.sdk_declarations import declaration_calls
        self._sdk_calls = declaration_calls(node)
        for stmt in node.body:
            kind = module_statement_kind(stmt)
            if kind in {"import", "definition"}:
                self.visit(stmt)
            elif kind == "assignment":
                self._visit_module_assignment(stmt)
            elif kind != "docstring":
                self._add(
                    "BASE_LIB.TOP_LEVEL_SIDE_EFFECT",
                    "base_lib top level may only contain imports, definitions, immutable constants, and docstrings",
                    stmt,
                )

    def visit_Import(self, node: ast.Import) -> None:
        self._check_import_node(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        if process_argv_import_is_forbidden(
            module,
            {alias.name for alias in node.names},
        ):
            self._add(
                "BASE_LIB.BANNED_IMPORT",
                "base_lib must not import process sys.argv",
                node,
            )
        self._check_import_node(node)

    def visit_Call(self, node: ast.Call) -> None:
        violation_code, forbidden = call_violation(
            node,
            aliases=self.import_aliases,
            effect_scope=self.effect_scope,
            imported_roots=self.imported_module_roots,
        )
        if violation_code:
            self._add(
                "BASE_LIB.SIDE_EFFECT_CALL",
                f"base_lib banned side-effect call: {forbidden}",
                node,
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        record_assignment_aliases(node, self.import_aliases)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        record_assignment_aliases(node, self.import_aliases)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        record_assignment_aliases(node, self.import_aliases)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        reference = process_argv_reference(node, self.import_aliases)
        if reference:
            self._add(
                "BASE_LIB.SIDE_EFFECT_CALL",
                f"base_lib banned process argument access: {reference}",
                node,
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        reference = dynamic_namespace_reference(
            node,
            aliases=self.import_aliases,
            imported_roots=self.imported_module_roots,
        )
        if reference:
            self._add(
                "BASE_LIB.SIDE_EFFECT_CALL",
                f"base_lib banned dynamic module namespace lookup: {reference}",
                node,
            )
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise) -> None:
        if not isinstance(node.exc, ast.Call):
            reference = system_exit_reference(node.exc, self.import_aliases)
            if reference and system_exit_is_forbidden(self.effect_scope):
                self._add(
                    "BASE_LIB.SIDE_EFFECT_CALL",
                    f"base_lib banned process exit: {reference}",
                    node,
                )
        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        if self.effect_scope == "global_state":
            return
        self._add(
            "BASE_LIB.GLOBAL_STATE",
            "base_lib must not use global mutation",
            node,
        )

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        if self.effect_scope == "global_state":
            return
        self._add(
            "BASE_LIB.GLOBAL_STATE",
            "base_lib must not use nonlocal mutation",
            node,
        )

    def _visit_module_assignment(self, node: ast.Assign | ast.AnnAssign) -> None:
        if self.effect_scope != "global_state" and not module_assignment_is_allowed(node) and node.value not in getattr(self, "_sdk_calls", ()):
            self._add(
                "BASE_LIB.GLOBAL_STATE",
                "base_lib must not hold mutable module-level state",
                node,
            )
        self.visit(node)

    def _check_import_node(self, node: ast.Import | ast.ImportFrom) -> None:
        self.import_aliases.update(import_aliases_from_node(node))
        self.imported_module_roots.update(imported_module_roots(node))
        for module in import_modules(node):
            self._check_import(module, node)

    def _check_import(self, module: str, node: ast.AST) -> None:
        self.imports.add(module)
        if any(
            part in FORBIDDEN_PROJECT_IMPORT_PARTS for part in module.split(".")
        ):
            self._add(
                "BASE_LIB.FORBIDDEN_PROJECT_IMPORT",
                "base_lib must not import node, plugin, boundary, runtime, or "
                f"side-effect layer: {module}",
                node,
            )
            return
        if module_matches(module, self.policy.banned_base_lib_modules):
            self._add(
                "BASE_LIB.BANNED_MODULE",
                f"base_lib module is banned by policy: {module}",
                node,
            )
            return
        if import_violation_code(
            module,
            effect_scope=self.effect_scope,
            policy=self.policy,
        ):
            self._add(
                "BASE_LIB.BANNED_IMPORT",
                f"base_lib banned import: {module}",
                node,
            )

    def _add(self, rule_id: str, message: str, node: ast.AST) -> None:
        self.findings.append(
            _finding(
                rule_id,
                message,
                path=self.path,
                module=self.module,
                line=getattr(node, "lineno", None),
                column=(getattr(node, "col_offset", 0) + 1)
                if hasattr(node, "col_offset")
                else None,
            )
        )


def _finding(
    rule_id: str,
    message: str,
    *,
    path: str,
    module: str,
    line: int | None = None,
    column: int | None = None,
    details: Mapping[str, object] | None = None,
) -> BaseLibFinding:
    location: dict[str, object] = {"path": path}
    if line is not None:
        location["line"] = line
    if column is not None:
        location["column"] = column
    return BaseLibFinding(
        rule_id=rule_id,
        message=message,
        object_id=module,
        source_location=location,
        details=details or {},
    )
