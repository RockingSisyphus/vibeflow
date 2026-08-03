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
    reflected = reflected_reference_name(node, aliases)
    if reflected:
        return reflected
    if isinstance(node, ast.Name):
        return _normalize_builtin_root(aliases.get(node.id, node.id))
    if isinstance(node, ast.Attribute):
        left = qualified_call_name(node.value, aliases)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return qualified_call_name(node.func, aliases)
    return ""


def qualified_reference_name(node: ast.AST, aliases: Mapping[str, str]) -> str:
    """Resolve a statically named value, including common reflection bypasses."""

    reflected = reflected_reference_name(node, aliases)
    if reflected:
        return reflected
    if isinstance(node, ast.Name):
        return _normalize_builtin_root(aliases.get(node.id, node.id))
    if isinstance(node, ast.Attribute):
        left = qualified_reference_name(node.value, aliases)
        return f"{left}.{node.attr}" if left else ""
    return ""


def reflected_reference_name(node: ast.AST, aliases: Mapping[str, str]) -> str:
    """Resolve literal ``getattr``/``vars``/``__dict__`` lookup chains."""

    if isinstance(node, ast.Subscript):
        key = _literal_string(node.slice)
        if not key:
            return ""
        base = qualified_reference_name(node.value, aliases)
        if base.endswith(".__dict__"):
            base = base[: -len(".__dict__")]
        return f"{base}.{key}" if base else ""
    if not isinstance(node, ast.Call):
        return ""
    if isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
        base = qualified_reference_name(node.func.value, aliases)
        key = _literal_string(node.args[0])
        if base.endswith(".__dict__") and key:
            return f"{base[: -len('.__dict__')]}.{key}"
    function = qualified_call_name(node.func, aliases)
    if function in {"getattr", "builtins.getattr"} and len(node.args) >= 2:
        base = qualified_reference_name(node.args[0], aliases)
        attribute = _literal_string(node.args[1])
        return f"{base}.{attribute}" if base and attribute else ""
    if function in {"vars", "builtins.vars"} and len(node.args) == 1:
        base = qualified_reference_name(node.args[0], aliases)
        return f"{base}.__dict__" if base else ""
    return ""


def record_assignment_aliases(
    node: ast.Assign | ast.AnnAssign | ast.NamedExpr,
    aliases: dict[str, str],
) -> None:
    """Track simple callable/module aliases and invalidate overwritten names."""

    value = node.value
    resolved = qualified_reference_name(value, aliases)
    if isinstance(node, ast.Assign):
        targets = node.targets
    else:
        targets = (node.target,)
    for target in targets:
        if not isinstance(target, ast.Name):
            continue
        if resolved and resolved != target.id:
            aliases[target.id] = resolved
        else:
            aliases.pop(target.id, None)


def import_aliases_from_node(node: ast.Import | ast.ImportFrom) -> dict[str, str]:
    if isinstance(node, ast.Import):
        return {alias.asname or alias.name.split(".", 1)[0]: alias.name for alias in node.names}
    if not node.module:
        return {}
    return {alias.asname or alias.name: f"{node.module}.{alias.name}" for alias in node.names}


def imported_module_roots(node: ast.Import | ast.ImportFrom) -> set[str]:
    """Return resolved top-level module roots introduced by one import."""

    return {
        value.split(".", 1)[0]
        for value in import_aliases_from_node(node).values()
        if value
    }


def import_aliases(tree: ast.AST, *, defaults: Mapping[str, str] | None = None) -> dict[str, str]:
    aliases = dict(defaults or {})
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            aliases.update(import_aliases_from_node(node))
    return aliases


def import_roots(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    return tuple(module.split(".", 1)[0] for module in import_modules(node))


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


def module_matches(module: str, patterns: tuple[str, ...]) -> bool:
    return any(module == pattern or module.startswith(f"{pattern}.") for pattern in patterns)


def is_banned_import(module: str, *, allowed_roots: tuple[str, ...], banned_roots: tuple[str, ...], allowed_modules: tuple[str, ...], banned_modules: tuple[str, ...]) -> bool:
    root = module.split(".", 1)[0]
    if module_matches(module, banned_modules):
        return True
    if module_matches(module, allowed_modules):
        return False
    return root in set(banned_roots) and root not in set(allowed_roots)


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


def _literal_string(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return ""


def _normalize_builtin_root(value: str) -> str:
    if value == "__builtins__" or value.startswith("__builtins__."):
        return f"builtins{value[len('__builtins__'):]}"
    return value


def _is_docstring_expr(stmt: ast.stmt) -> bool:
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)
