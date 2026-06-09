from __future__ import annotations

import ast


def module_statement_kind(stmt: ast.stmt) -> str:
    if isinstance(stmt, (ast.Import, ast.ImportFrom)):
        return "import"
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return "definition"
    if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
        return "assignment"
    if _is_docstring_expr(stmt):
        return "docstring"
    return "other"


def import_modules(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)
    return (node.module,) if node.module else ()


def boolop_branch_count(node: ast.BoolOp) -> int:
    return max(0, len(node.values) - 1)


def name_targets(targets: list[ast.expr]) -> tuple[ast.Name, ...]:
    return tuple(target for target in targets if isinstance(target, ast.Name))


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
