from __future__ import annotations

import ast
from copy import deepcopy
from typing import Mapping

from vibeflow.targets.python.quality.source_analysis.types import PurityViolation, _SourceInfo, _default_rule_id






def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""






def _module_matches(module: str, patterns: tuple[str, ...]) -> bool:
    return any(module == pattern or module.startswith(f"{pattern}.") for pattern in patterns)


def _fingerprint_function(node: ast.FunctionDef) -> str:
    node = _FingerprintNormalizer().visit(deepcopy(node))  # type: ignore[assignment]
    ast.fix_missing_locations(node)
    normalized = ast.dump(node, annotate_fields=False, include_attributes=False)
    for name in ("run_pure", "inputs", "params", "self"):
        normalized = normalized.replace(name, "_")
    return normalized


class _FingerprintNormalizer(ast.NodeTransformer):
    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, str):
            return ast.copy_location(ast.Constant(value="<str>"), node)
        if isinstance(node.value, (int, float, bool)):
            return ast.copy_location(ast.Constant(value=0), node)
        return node


def _tokens(text: str) -> set[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in text)
    stop = {"a", "an", "and", "in", "node", "out", "output", "input", "the", "to", "value"}
    return {part for part in normalized.split() if len(part) >= 3 and part not in stop}


def _looks_temporary_key(key: str) -> bool:
    parts = _tokens(key)
    return bool(parts & {"debug", "scratch", "temp", "temporary", "tmp", "intermediate"})


def _looks_structured_key(key: str) -> bool:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789._")
    return bool(key) and key == key.lower() and all(char in allowed for char in key) and ".." not in key


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _violation(
    code: str,
    message: str,
    *,
    source: _SourceInfo,
    line: int | None = None,
    column: int | None = None,
    severity: str = "error",
    failure_layer: str = "implementation",
    suggested_fix_type: str = "fix_node",
    details: Mapping[str, object] | None = None,
) -> PurityViolation:
    return PurityViolation(
        code=code,
        rule_id=_default_rule_id(code),
        severity=severity,
        source_location=source.location(line=line, column=column),
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type=suggested_fix_type,
        details=details or {},
    )
