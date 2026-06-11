from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

from ..ast_rules import import_aliases_from_node, path_effect_call_name
from .code_quality_types import SIDE_EFFECT_ATTR_CALLS, SIDE_EFFECT_CALLS, SIDE_EFFECT_IMPORT_ROOTS, QualityFinding


def side_effect_findings(module: str, rel_path: str, path: Path, tree: ast.AST) -> list[QualityFinding]:
    findings = []
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            findings.extend(_side_effect_import_findings(module, path, node))
            continue
        if isinstance(node, ast.Call):
            findings.extend(_side_effect_call_findings(rel_path, path, node, aliases))
    return findings


def _side_effect_import_findings(module: str, path: Path, node: ast.Import | ast.ImportFrom) -> list[QualityFinding]:
    findings = []
    for root in _side_effect_import_roots(node):
        if root in SIDE_EFFECT_IMPORT_ROOTS:
            findings.append(_finding("QUALITY.SIDE_EFFECT.IMPORT", "warning", "module", module, path, getattr(node, "lineno", 1), f"imports side-effect capable module {root}", "isolate_side_effect"))
    return findings


def _side_effect_call_findings(rel_path: str, path: Path, node: ast.Call, aliases: Mapping[str, str]) -> list[QualityFinding]:
    call_name = _call_name(node.func, aliases)
    if call_name in SIDE_EFFECT_CALLS or any(call_name == banned or call_name.startswith(f"{banned}.") for banned in SIDE_EFFECT_ATTR_CALLS):
        return [_finding("QUALITY.SIDE_EFFECT.CALL", "warning", "file", rel_path, path, getattr(node, "lineno", 1), f"calls side-effect capable API {call_name}", "isolate_side_effect")]
    path_effect = path_effect_call_name(node, aliases)
    if path_effect:
        return [_finding("QUALITY.SIDE_EFFECT.CALL", "warning", "file", rel_path, path, getattr(node, "lineno", 1), f"calls side-effect capable API {path_effect}", "isolate_side_effect")]
    return []


def _side_effect_import_roots(node: ast.Import | ast.ImportFrom) -> tuple[str, ...]:
    roots = [alias.name.split(".", 1)[0] for alias in getattr(node, "names", ())]
    if isinstance(node, ast.ImportFrom) and node.module:
        roots.append(node.module.split(".", 1)[0])
    return tuple(roots)


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases = {"Path": "pathlib.Path"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            aliases.update(import_aliases_from_node(node))
    return aliases


def _call_name(func: ast.AST, aliases: Mapping[str, str]) -> str:
    if isinstance(func, ast.Name):
        return aliases.get(func.id, func.id)
    if isinstance(func, ast.Attribute):
        return f"{_call_name(func.value, aliases)}.{func.attr}"
    return "<dynamic>"


def _finding(
    rule_id: str,
    severity: str,
    object_type: str,
    object_id: str,
    path: Path,
    line: int,
    message: str,
    suggested_fix_type: str = "refactor",
    details: Mapping[str, object] | None = None,
) -> QualityFinding:
    return QualityFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=object_type,
        object_id=object_id,
        source_location={"path": str(path), "line": line},
        message=message,
        suggested_fix_type=suggested_fix_type,
        details=details or {},
    )
