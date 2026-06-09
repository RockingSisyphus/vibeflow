from __future__ import annotations

import ast
from copy import deepcopy
from typing import Mapping

from .node import NodeInfo
from .purity_types import IMMUTABLE_CONSTANT_TYPES, RESOURCE_FIELD_NAMES, PurityViolation, _SourceInfo, _default_rule_id


def _validate_key_tuple(value: object, field_name: str, *, source: _SourceInfo, violations: list[PurityViolation]) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not _non_empty_string(item) for item in value):
        violations.append(_violation("contract_key_list", f"{field_name} must be a tuple/list of non-empty strings", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
        return ()
    if len(set(value)) != len(value):
        violations.append(_violation("contract_duplicate_key", f"{field_name} must not contain duplicate keys", source=source, failure_layer="contract", suggested_fix_type="fix_contract"))
    return value


def _validate_semantics(value: object, keys: tuple[str, ...], field_name: str, *, required: bool, source: _SourceInfo) -> list[PurityViolation]:
    if not isinstance(value, Mapping):
        return [_violation("contract_semantics", f"{field_name} must be a mapping", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    missing = set(keys) - set(value)
    if required and missing:
        return [_violation("contract_semantics_missing", f"{field_name} must cover keys: {sorted(missing)}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for key, item in value.items():
        if key not in keys:
            return [_violation("contract_semantics_extra", f"{field_name} contains undeclared key: {key}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not isinstance(item, tuple) or any(not _non_empty_string(part) for part in item):
            return [_violation("contract_semantics", f"{field_name}[{key!r}] must be a tuple of non-empty strings", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _validate_schema_mapping(value: object, keys: tuple[str, ...], field_name: str, *, source: _SourceInfo, require_all: bool) -> list[PurityViolation]:
    if not isinstance(value, Mapping):
        return [_violation("contract_schema", f"{field_name} must be a mapping", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    missing = set(keys) - set(value)
    if require_all and missing:
        return [_violation("contract_schema_missing", f"{field_name} must cover keys: {sorted(missing)}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    for key, schema in value.items():
        if keys and key not in keys:
            return [_violation("contract_schema_extra", f"{field_name} contains undeclared key: {key}", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
        if not isinstance(schema, Mapping) or ("type" not in schema and schema.get("snapshot") != "opaque"):
            return [_violation("contract_schema_shape", f"{field_name}[{key!r}] must be an object with 'type' or snapshot='opaque'", source=source, failure_layer="contract", suggested_fix_type="fix_contract")]
    return []


def _dict_literal_keys(node: ast.Dict) -> tuple[set[str] | None, bool]:
    keys: set[str] = set()
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str) or not key.value:
            return None, True
        keys.add(key.value)
    return keys, False


def _literal_subscript_key(node: ast.Subscript) -> str:
    if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
        return node.slice.value
    return ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return ""


def _root_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _root_name(node.value)
    if isinstance(node, ast.Call):
        return _root_name(node.func)
    return ""


def _matches_prefix(name: str, patterns: set[str]) -> bool:
    return any(name.startswith(f"{pattern}.") for pattern in patterns)


def _is_inputs_subscript(node: ast.AST) -> bool:
    return isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "inputs"


def _assigns_resource_field(node: ast.AST) -> bool:
    targets: list[ast.AST] = []
    if isinstance(node, ast.Assign):
        targets = list(node.targets)
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    for target in targets:
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
            if target.attr.lower() in RESOURCE_FIELD_NAMES:
                return True
    return False


def _module_assignment_is_allowed(node: ast.Assign | ast.AnnAssign) -> bool:
    value = node.value
    if value is None:
        return True
    return _is_immutable_constant(value)


def _is_immutable_constant(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, IMMUTABLE_CONSTANT_TYPES)
    if isinstance(node, ast.Tuple):
        return all(_is_immutable_constant(item) for item in node.elts)
    return False


def _class_looks_like_node(node: ast.ClassDef) -> bool:
    names = set()
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return {"NODE_INFO", "CONTRACT"} <= names


def _is_node_module(module: str) -> bool:
    return _module_has_part(module, "nodes")


def _is_boundary_import(module: str) -> bool:
    parts = tuple(part for part in module.split(".") if part)
    return "boundary" in parts or "boundaries" in parts


def _is_base_lib_module(module: str) -> bool:
    return _module_has_part(module, "base_lib")


def _module_has_part(module: str, expected: str) -> bool:
    return expected in tuple(part for part in module.split(".") if part)


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



def _dedupe_violations(violations: list[PurityViolation]) -> list[PurityViolation]:
    seen: set[tuple[str, str, tuple[tuple[str, object], ...]]] = set()
    out: list[PurityViolation] = []
    for violation in violations:
        key = (violation.rule_id, violation.message, tuple(sorted(violation.source_location.items())))
        if key in seen:
            continue
        seen.add(key)
        out.append(violation)
    return out
