from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .node import NodeContract, NodeInfo, PureNode


BANNED_IMPORT_ROOTS = {
    "httpx",
    "nodriver",
    "playwright",
    "requests",
    "selenium",
    "shutil",
    "socket",
    "sqlite3",
    "subprocess",
}
BANNED_CALL_NAMES = {"eval", "exec", "open", "__import__"}
BANNED_ATTR_CALLS = {
    "os.system",
    "Path.write_text",
    "Path.write_bytes",
    "Path.unlink",
    "Path.rename",
}


@dataclass(frozen=True)
class PurityPolicy:
    max_source_lines: int = 500
    max_source_bytes: int = 60000
    allowed_import_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class PurityViolation:
    code: str
    message: str


def validate_node_class(node_cls: type[PureNode], *, policy: PurityPolicy | None = None) -> list[PurityViolation]:
    policy = policy or PurityPolicy()
    violations: list[PurityViolation] = []
    info = getattr(node_cls, "NODE_INFO", None)
    contract = getattr(node_cls, "CONTRACT", None)
    if not isinstance(info, NodeInfo):
        violations.append(PurityViolation("missing_node_info", "node must define NODE_INFO: NodeInfo"))
    elif info.purity != "pure":
        violations.append(PurityViolation("non_pure_node", "NODE_INFO.purity must be 'pure'"))
    if not isinstance(contract, NodeContract):
        violations.append(PurityViolation("missing_contract", "node must define CONTRACT: NodeContract"))
    if hasattr(node_cls, "run"):
        violations.append(PurityViolation("context_run_forbidden", "pure node must not define run(context, ...)"))
    if not hasattr(node_cls, "run_pure"):
        violations.append(PurityViolation("missing_run_pure", "node must define run_pure(inputs, params)"))

    source = _source_text(node_cls)
    if source is None:
        violations.append(PurityViolation("source_unavailable", "node source is unavailable for static purity check"))
        return violations
    line_count = len(source.splitlines())
    if line_count > policy.max_source_lines:
        violations.append(PurityViolation("source_too_large", f"node source has {line_count} lines > {policy.max_source_lines}"))
    byte_count = len(source.encode("utf-8"))
    if byte_count > policy.max_source_bytes:
        violations.append(PurityViolation("source_bytes_too_large", f"node source has {byte_count} bytes > {policy.max_source_bytes}"))
    violations.extend(_validate_ast(source, policy=policy))
    return violations


def _source_text(node_cls: type[Any]) -> str | None:
    try:
        return inspect.getsource(node_cls)
    except (OSError, TypeError):
        source_file = inspect.getsourcefile(node_cls)
        if not source_file:
            return None
        path = Path(source_file)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")


def _validate_ast(source: str, *, policy: PurityPolicy) -> list[PurityViolation]:
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [PurityViolation("syntax_error", str(exc))]
    allowed = set(policy.allowed_import_roots)
    violations: list[PurityViolation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in BANNED_IMPORT_ROOTS and root not in allowed:
                    violations.append(PurityViolation("banned_import", f"banned import: {alias.name}"))
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in BANNED_IMPORT_ROOTS and root not in allowed:
                violations.append(PurityViolation("banned_import", f"banned import: {node.module}"))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            violations.append(PurityViolation("global_state", "global/nonlocal mutation is forbidden"))
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in BANNED_CALL_NAMES or name in BANNED_ATTR_CALLS:
                violations.append(PurityViolation("banned_call", f"banned call: {name}"))
    return violations


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""
