from __future__ import annotations

import ast

from vibeflow.purity.ast_rules import name_targets
from vibeflow.purity.helpers import _dict_literal_keys, _literal_subscript_key
from vibeflow.purity.types import MUTATING_METHODS


def _reachable_module_helpers(node: ast.Module, node_class_name: str) -> set[str]:
    helpers = {
        stmt.name: stmt
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target = next(
        (
            stmt
            for stmt in node.body
            if isinstance(stmt, ast.ClassDef) and stmt.name == node_class_name
        ),
        None,
    )
    if target is None or not helpers:
        return set()
    reachable: set[str] = set()
    pending = list(_called_module_helpers(target, helpers))
    while pending:
        name = pending.pop()
        if name in reachable:
            continue
        reachable.add(name)
        pending.extend(_called_module_helpers(helpers[name], helpers) - reachable)
    return reachable


def _trace_helper_input_parameters(
    node: ast.Module,
    node_class_name: str,
) -> dict[str, set[str]]:
    helpers = {
        stmt.name: stmt
        for stmt in node.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target = next(
        (
            stmt
            for stmt in node.body
            if isinstance(stmt, ast.ClassDef) and stmt.name == node_class_name
        ),
        None,
    )
    tainted: dict[str, set[str]] = {name: set() for name in helpers}
    if target is None:
        return tainted
    sources: list[tuple[ast.AST, set[str]]] = [
        (stmt, {"inputs"})
        for stmt in target.body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef))
        and any(
            arg.arg == "inputs"
            for arg in (*stmt.args.posonlyargs, *stmt.args.args, *stmt.args.kwonlyargs)
        )
    ]
    while sources:
        source, seeds = sources.pop()
        aliases = _input_reference_aliases(source, seeds)
        for call in (child for child in ast.walk(source) if isinstance(child, ast.Call)):
            if not isinstance(call.func, ast.Name) or call.func.id not in helpers:
                continue
            next_names = _tainted_helper_parameters(call, helpers[call.func.id], aliases)
            unseen = next_names - tainted[call.func.id]
            if unseen:
                tainted[call.func.id].update(unseen)
                sources.append((helpers[call.func.id], set(tainted[call.func.id])))
    return tainted


def _called_module_helpers(node: ast.AST, helpers: dict[str, ast.AST]) -> set[str]:
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id in helpers
    }


def _input_reference_aliases(node: ast.AST, seeds: set[str]) -> set[str]:
    aliases = set(seeds)
    changed = True
    while changed:
        changed = False
        for child in ast.walk(node):
            if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                continue
            value = child.value
            if value is None or not _is_input_reference(value, aliases):
                continue
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in aliases:
                    aliases.add(target.id)
                    changed = True
    return aliases


def _tainted_helper_parameters(
    call: ast.Call,
    helper: ast.FunctionDef | ast.AsyncFunctionDef,
    aliases: set[str],
) -> set[str]:
    positional = (*helper.args.posonlyargs, *helper.args.args)
    tainted: set[str] = set()
    for index, value in enumerate(call.args):
        if index < len(positional) and _is_input_reference(value, aliases):
            tainted.add(positional[index].arg)
    parameters = {arg.arg for arg in (*positional, *helper.args.kwonlyargs)}
    for keyword in call.keywords:
        if keyword.arg in parameters and _is_input_reference(keyword.value, aliases):
            tainted.add(str(keyword.arg))
    return tainted


def _is_input_reference(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, (ast.Attribute, ast.Subscript)):
        return _is_input_reference(node.value, aliases)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "get" and _is_input_reference(node.func.value, aliases)
    return False


class _NodeDataTrackingMixin:
    def _track_input_alias(self, node: ast.Assign) -> None:
        aliases_input = self._is_node_input_reference(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if aliases_input:
                    self._input_aliases.add(target.id)
                else:
                    self._input_aliases.discard(target.id)

    def _track_output_literal(self, node: ast.Assign) -> None:
        if not isinstance(node.value, ast.Dict):
            return
        keys, dynamic = _dict_literal_keys(node.value)
        if dynamic or keys is None:
            return
        for target in name_targets(node.targets):
            self._output_dicts[target.id] = keys

    def _track_output_key_assignment(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id in self._output_dicts:
                self._record_output_key(target, node)

    def _record_output_key(self, target: ast.Subscript, node: ast.Assign) -> None:
        key = _literal_subscript_key(target)
        if key and isinstance(target.value, ast.Name):
            self._output_dicts[target.value.id].add(key)
        else:
            self._add("dynamic_output_key", "output dict assignment key must be a string literal", node, suggested_fix_type="fix_contract")

    def _check_input_mutation_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute):
            return
        if self._is_node_input_reference(node.func.value) and node.func.attr in MUTATING_METHODS:
            self._add("input_mutation", f"node must not mutate inputs via {node.func.attr}", node, suggested_fix_type="fix_node")

    def _check_params_get_call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            return
        if node.func.value.id == "params" and node.func.attr == "get" and node.args:
            self._check_params_key_node(node.args[0], node)

    def _check_params_key_node(self, key_node: ast.AST, node: ast.Call) -> None:
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            key = key_node.value
            if key != "_global" and self.contract is not None and key not in self.contract.params_schema:
                self._add("undeclared_param", f"params key is not declared in CONTRACT.params_schema: {key}", node, failure_layer="contract", suggested_fix_type="fix_contract")

    def _check_assignment_target(self, target: ast.AST, node: ast.AST) -> None:
        if self._target_mutates_node_input(target):
            self._add("input_mutation", "node must not mutate inputs", node, suggested_fix_type="fix_node")
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id != "self":
            self._add("monkey_patch", "assigning to external object attributes is forbidden", node, suggested_fix_type="fix_node")

    def _target_mutates_node_input(self, target: ast.AST) -> bool:
        return isinstance(target, (ast.Subscript, ast.Attribute)) and self._is_node_input_reference(target.value)

    def _is_node_input_reference(self, node: ast.AST) -> bool:
        return _is_input_reference(node, {"inputs", *self._input_aliases})

    def _return_keys(self, value: ast.AST | None) -> tuple[set[str] | None, bool]:
        if isinstance(value, ast.Dict):
            return _dict_literal_keys(value)
        if isinstance(value, ast.Name) and value.id in self._output_dicts:
            return set(self._output_dicts[value.id]), False
        return None, True
