from __future__ import annotations

import ast
from typing import Mapping


IMMUTABLE_AST_CONSTANT_TYPES = (str, int, float, bool, type(None))
PATH_EFFECT_METHODS = frozenset(
    {
        "mkdir",
        "open",
        "read_bytes",
        "read_text",
        "rename",
        "replace",
        "rmdir",
        "touch",
        "unlink",
        "write_bytes",
        "write_text",
    }
)


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


def call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return call_name(node.func)
    return ""


def qualified_call_name(node: ast.AST, aliases: Mapping[str, str]) -> str:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        return f"{qualified_call_name(node.value, aliases)}.{node.attr}"
    if isinstance(node, ast.Call):
        return qualified_call_name(node.func, aliases)
    return ""


def import_aliases_from_node(node: ast.Import | ast.ImportFrom) -> dict[str, str]:
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0]: alias.name for alias in node.names}
    if not node.module:
        return {}
    return {alias.asname or alias.name: f"{node.module}.{alias.name}" for alias in node.names}


def path_effect_call_name(node: ast.Call, aliases: Mapping[str, str]) -> str:
    if not isinstance(node.func, ast.Attribute) or node.func.attr not in PATH_EFFECT_METHODS:
        return ""
    if _is_pathlike_expression(node.func.value, aliases):
        return f"pathlib.Path.{node.func.attr}"
    return ""


def module_assignment_is_allowed(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return True
    return is_immutable_constant(value)


def is_immutable_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, IMMUTABLE_AST_CONSTANT_TYPES)
    if isinstance(node, ast.Tuple):
        return all(is_immutable_constant(item) for item in node.elts)
    return False


def name_targets(targets: list[ast.expr]) -> tuple[ast.Name, ...]:
    return tuple(target for target in targets if isinstance(target, ast.Name))


def _is_pathlike_expression(node: ast.AST, aliases: Mapping[str, str]) -> bool:
    if isinstance(node, ast.Name):
        return aliases.get(node.id, "") == "pathlib.Path" or _looks_pathlike_name(node.id)
    if isinstance(node, ast.Call):
        return qualified_call_name(node.func, aliases) == "pathlib.Path" or _is_pathlike_expression(node.func, aliases)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _is_pathlike_expression(node.left, aliases) or _is_pathlike_expression(node.right, aliases)
    if isinstance(node, ast.Attribute):
        return _is_pathlike_expression(node.value, aliases)
    return False


def _looks_pathlike_name(value: str) -> bool:
    lowered = value.lower()
    return lowered in {"path", "root", "output", "destination", "run_dir"} or lowered.endswith(
        ("_path", "_dir", "_file", "_root")
    )


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
