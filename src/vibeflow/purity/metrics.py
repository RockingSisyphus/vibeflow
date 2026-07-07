from __future__ import annotations

import ast
from typing import Any

from vibeflow.purity.ast_rules import boolop_branch_count, call_name
from vibeflow.purity.helpers import _fingerprint_function
from vibeflow.purity.types import _CallChainAnalysis


class _ComplexityCounter(ast.NodeVisitor):
    def __init__(self) -> None:
        self.function_count = 0
        self.branch_count = 0
        self.max_nesting_depth = 0
        self.function_names: list[str] = []
        self.run_pure_fingerprint = ""
        self.run_pure_shape = ""
        self._nesting = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_count += 1
        self.function_names.append(node.name)
        if node.name == "run_pure":
            self.run_pure_fingerprint = _fingerprint_function(node)
            self.run_pure_shape = _classify_run_pure_shape(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_If(self, node: ast.If) -> None:
        self._visit_branch(node)

    def visit_For(self, node: ast.For) -> None:
        self._visit_branch(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_branch(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_branch(node)

    def visit_Try(self, node: ast.Try) -> None:
        self.branch_count += max(1, len(node.handlers))
        self._with_nesting(lambda: self.generic_visit(node))

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self.visit_Try(node)  # type: ignore[arg-type]

    def visit_Match(self, node: ast.Match) -> None:
        self.branch_count += max(1, len(node.cases))
        self._with_nesting(lambda: self.generic_visit(node))

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self.branch_count += boolop_branch_count(node)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._visit_branch(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self.branch_count += 1 + len(node.ifs)
        self.generic_visit(node)

    def _visit_branch(self, node: ast.AST) -> None:
        self.branch_count += 1
        self._with_nesting(lambda: self.generic_visit(node))

    def _with_nesting(self, callback: Any) -> None:
        self._nesting += 1
        self.max_nesting_depth = max(self.max_nesting_depth, self._nesting)
        callback()
        self._nesting -= 1


def _analyze_internal_call_chain(tree: ast.Module) -> _CallChainAnalysis:
    class_defs = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    if not class_defs:
        return _CallChainAnalysis()
    class_def = class_defs[0]
    methods = {node.name: node for node in class_def.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "run_pure" not in methods:
        return _CallChainAnalysis()
    method_names = set(methods)
    graph: dict[str, set[str]] = {name: set() for name in method_names}
    for name, method in methods.items():
        collector = _InternalMethodCallCollector(method_names)
        collector.visit(method)
        graph[name] = collector.calls

    recursive_paths: list[tuple[str, ...]] = []
    best_path: tuple[str, ...] = ("run_pure",)

    def dfs(name: str, path: tuple[str, ...]) -> None:
        nonlocal best_path
        if len(path) > len(best_path):
            best_path = path
        for target in sorted(graph.get(name, ())):
            if target in path:
                cycle = (*path[path.index(target):], target)
                if cycle not in recursive_paths:
                    recursive_paths.append(cycle)
                continue
            dfs(target, (*path, target))

    dfs("run_pure", ("run_pure",))
    return _CallChainAnalysis(length=len(best_path), path=best_path, recursive_paths=tuple(recursive_paths))


class _InternalMethodCallCollector(ast.NodeVisitor):
    def __init__(self, method_names: set[str]) -> None:
        self.method_names = method_names
        self.calls: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        target = ""
        if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "self":
            target = node.func.attr
        elif isinstance(node.func, ast.Name):
            target = node.func.id
        if target in self.method_names:
            self.calls.add(target)
        self.generic_visit(node)


def _classify_run_pure_shape(node: ast.FunctionDef) -> str:
    if _has_control_flow(node):
        return "logic"
    core_calls = [name for name in _call_names(node) if not _is_wrapper_scaffolding_call(name)]
    if len(core_calls) == 1 and _has_static_output_return(node):
        return "wrapper"
    if not core_calls and _has_static_output_return(node):
        return "literal"
    return "logic"


def _has_control_flow(node: ast.FunctionDef) -> bool:
    control_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.Match, ast.IfExp, ast.comprehension)
    return any(isinstance(child, control_nodes) for child in ast.walk(node))


def _call_names(node: ast.FunctionDef) -> tuple[str, ...]:
    names: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            names.append(call_name(child.func))
    return tuple(names)


def _is_wrapper_scaffolding_call(name: str) -> bool:
    return name in {"dict", "list", "tuple", "set", "str", "int", "float", "bool", "inputs.get", "params.get"}


def _has_static_output_return(node: ast.FunctionDef) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Return):
            continue
        if isinstance(child.value, ast.Dict):
            return all(isinstance(key, ast.Constant) and isinstance(key.value, str) for key in child.value.keys)
        if isinstance(child.value, ast.Name):
            return True
    return False

