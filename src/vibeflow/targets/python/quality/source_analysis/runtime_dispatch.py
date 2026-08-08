"""Static, advisory detection of source-visible runtime dispatch.

This module deliberately does not try to prove what third-party or native
functions do internally.  It follows values that visibly originate in a node
input envelope or mutable module state and reports only explicit calls through
those values.  The existing effect gate remains authoritative for IO, dynamic
code, process creation, and FFI.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from functools import lru_cache
import inspect
import os
import sys
import textwrap
from types import ModuleType
from typing import Any, Mapping

from vibeflow.targets.python.quality.source_analysis.source import _source_info


_STATIC = "static"
_OWNED = "owned"
_INPUTS = "inputs"
_ENVELOPE = "envelope"
_RUNTIME = "runtime"
_UNKNOWN = "unknown"
_CALLABLE = "callable"

_READ_ONLY_MAPPING_METHODS = frozenset({"get", "items", "keys", "values"})
_INPUT_VALUE_FIELDS = frozenset({"value", "values"})
_METADATA_NAMES = frozenset({"BASE_LIB_INFO", "CONTRACT", "NODE_INFO", "PLUGIN_INFO"})
_STATIC_BUILTINS = frozenset(dir(builtins))
_VALUE_PRESERVING_BUILTINS = frozenset({"anext", "next"})
_ITERATOR_BUILTINS = frozenset({"aiter", "iter"})


@dataclass(frozen=True)
class RuntimeDispatchSite:
    """One explicit call whose implementation comes from runtime data."""

    path: str
    line: int
    column: int
    dispatch_kind: str
    expression: str
    origin: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "dispatch_kind": self.dispatch_kind,
            "expression": self.expression,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class RuntimeDispatchAnalysis:
    """Tri-state-friendly result returned for an available Python source."""

    sites: tuple[RuntimeDispatchSite, ...] = ()

    @property
    def detected(self) -> bool:
        return bool(self.sites)


@dataclass(frozen=True)
class _Value:
    kind: str = _UNKNOWN
    origin: str = ""
    reference: object | None = None
    callable_id: str = ""


@dataclass(frozen=True)
class _FunctionUnit:
    key: str
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
    path: str
    line_offset: int
    module: ModuleType | None
    owner_class: str = ""


@dataclass(frozen=True)
class _Closure:
    unit: _FunctionUnit
    environment: Mapping[str, _Value]


@dataclass
class _Frame:
    unit: _FunctionUnit
    environment: dict[str, _Value]
    closures: dict[str, _Closure]


@lru_cache(maxsize=512)
def analyze_runtime_dispatch(node_cls: type[Any]) -> RuntimeDispatchAnalysis | None:
    """Return explicit runtime-dispatch sites, or ``None`` if source is absent.

    The function is intentionally read-only.  It uses already-loaded module
    objects only to resolve statically imported local helpers; it never imports
    or executes a helper while analysing it.
    """

    source = _source_info(node_cls)
    if not source.module_text or not source.path:
        return None
    try:
        tree = ast.parse(source.module_text, filename=source.path)
    except SyntaxError:
        return None
    class_node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.ClassDef) and item.name == node_cls.__name__
        ),
        None,
    )
    if class_node is None:
        return None
    run_node = next(
        (
            item
            for item in class_node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and item.name == "run_pure"
        ),
        None,
    )
    if run_node is None:
        return RuntimeDispatchAnalysis()
    module = inspect.getmodule(node_cls)
    analyzer = _RuntimeDispatchAnalyzer(
        root_path=source.path,
        root_tree=tree,
        root_module=module,
        owner_class=node_cls.__name__,
    )
    unit = _FunctionUnit(
        key=f"{source.path}:{node_cls.__qualname__}.run_pure",
        node=run_node,
        path=source.path,
        line_offset=0,
        module=module,
        owner_class=node_cls.__name__,
    )
    parameters = _bind_initial_parameters(run_node)
    analyzer.analyze(unit, parameters)
    return RuntimeDispatchAnalysis(tuple(analyzer.sites))


class _RuntimeDispatchAnalyzer:
    def __init__(
        self,
        *,
        root_path: str,
        root_tree: ast.Module,
        root_module: ModuleType | None,
        owner_class: str,
    ) -> None:
        self.root_path = _absolute_path(root_path)
        self.project_root = _project_root(self.root_path)
        self.root_tree = root_tree
        self.root_module = root_module
        self.owner_class = owner_class
        self.sites: list[RuntimeDispatchSite] = []
        self._site_keys: set[tuple[str, int, int, str]] = set()
        self._active: set[tuple[str, tuple[str, ...]]] = set()
        self._cache: dict[tuple[str, tuple[str, ...]], _Value] = {}
        self._closures: dict[str, _Closure] = {}
        self._module_trees: dict[str, ast.Module] = {self.root_path: root_tree}
        self._module_state: dict[str, set[str]] = {
            self.root_path: _mutable_module_state_names(root_tree)
        }
        self._module_functions: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {
            self.root_path: _top_level_functions(root_tree)
        }
        self._class_functions: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {
            self.root_path: _class_functions(root_tree, owner_class)
        }

    def analyze(
        self,
        unit: _FunctionUnit,
        arguments: Mapping[str, _Value],
        *,
        closure_environment: Mapping[str, _Value] | None = None,
    ) -> _Value:
        signature = tuple(
            f"{name}:{value.kind}"
            for name, value in sorted(arguments.items())
        )
        key = (unit.key, signature)
        if key in self._cache:
            return self._cache[key]
        if key in self._active:
            return _Value(_UNKNOWN)
        self._active.add(key)
        environment = dict(closure_environment or {})
        environment.update(arguments)
        frame = _Frame(unit=unit, environment=environment, closures={})
        if isinstance(unit.node, ast.Lambda):
            result = self._eval(unit.node.body, frame)
        else:
            returns = self._statements(unit.node.body, frame)
            result = _merge_values(*returns) if returns else _Value(_STATIC)
        self._active.remove(key)
        self._cache[key] = result
        return result

    def _statements(self, statements: list[ast.stmt], frame: _Frame) -> list[_Value]:
        returns: list[_Value] = []
        for statement in statements:
            if isinstance(statement, ast.Assign):
                value = self._eval(statement.value, frame)
                for target in statement.targets:
                    self._assign(target, value, frame)
            elif isinstance(statement, ast.AnnAssign):
                value = self._eval(statement.value, frame) if statement.value is not None else _Value(_UNKNOWN)
                self._assign(statement.target, value, frame)
            elif isinstance(statement, ast.NamedExpr):
                value = self._eval(statement.value, frame)
                self._assign(statement.target, value, frame)
            elif isinstance(statement, ast.AugAssign):
                self._eval(statement.value, frame)
                self._assign(statement.target, _Value(_STATIC), frame)
            elif isinstance(statement, ast.Expr):
                self._eval(statement.value, frame)
            elif isinstance(statement, ast.Return):
                returns.append(self._eval(statement.value, frame))
            elif isinstance(statement, ast.If):
                self._eval(statement.test, frame)
                before = dict(frame.environment)
                body_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                else_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                body_returns = self._statements(statement.body, body_frame)
                else_returns = self._statements(statement.orelse, else_frame)
                frame.environment = _merge_environments(
                    before,
                    body_frame.environment,
                    else_frame.environment,
                )
                frame.closures.update(body_frame.closures)
                frame.closures.update(else_frame.closures)
                returns.extend(body_returns)
                returns.extend(else_returns)
            elif isinstance(statement, (ast.For, ast.AsyncFor)):
                iterable = self._eval(statement.iter, frame)
                before = dict(frame.environment)
                body_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                item = _runtime_child(iterable, "iterated runtime value")
                self._assign(statement.target, item, body_frame)
                returns.extend(self._statements(statement.body, body_frame))
                returns.extend(self._statements(statement.orelse, body_frame))
                frame.environment = _merge_environments(before, body_frame.environment)
                frame.closures.update(body_frame.closures)
            elif isinstance(statement, ast.While):
                self._eval(statement.test, frame)
                before = dict(frame.environment)
                body_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                returns.extend(self._statements(statement.body, body_frame))
                returns.extend(self._statements(statement.orelse, body_frame))
                frame.environment = _merge_environments(before, body_frame.environment)
                frame.closures.update(body_frame.closures)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                for item in statement.items:
                    value = self._eval(item.context_expr, frame)
                    if item.optional_vars is not None:
                        self._assign(item.optional_vars, _runtime_child(value, value.origin), frame)
                returns.extend(self._statements(statement.body, frame))
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                closure = self._nested_closure(statement, frame)
                frame.closures[statement.name] = closure
                self._closures[closure.unit.key] = closure
                frame.environment[statement.name] = _Value(
                    _CALLABLE,
                    origin="locally defined callable",
                    callable_id=closure.unit.key,
                )
            elif isinstance(statement, ast.Try):
                before = dict(frame.environment)
                branches: list[dict[str, _Value]] = []
                try_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                returns.extend(self._statements(statement.body, try_frame))
                returns.extend(self._statements(statement.orelse, try_frame))
                branches.append(try_frame.environment)
                for handler in statement.handlers:
                    handler_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                    if handler.name:
                        handler_frame.environment[handler.name] = _Value(_OWNED)
                    returns.extend(self._statements(handler.body, handler_frame))
                    branches.append(handler_frame.environment)
                frame.environment = _merge_environments(before, *branches)
                returns.extend(self._statements(statement.finalbody, frame))
            elif isinstance(statement, ast.Match):
                subject = self._eval(statement.subject, frame)
                before = dict(frame.environment)
                branches = []
                for case in statement.cases:
                    case_frame = _Frame(frame.unit, dict(before), dict(frame.closures))
                    for name in _pattern_names(case.pattern):
                        case_frame.environment[name] = _runtime_child(subject, subject.origin)
                    if case.guard is not None:
                        self._eval(case.guard, case_frame)
                    returns.extend(self._statements(case.body, case_frame))
                    branches.append(case_frame.environment)
                frame.environment = _merge_environments(before, *branches)
            else:
                for child in ast.iter_child_nodes(statement):
                    if isinstance(child, ast.expr):
                        self._eval(child, frame)
        return returns

    def _eval(self, node: ast.AST | None, frame: _Frame) -> _Value:
        if node is None:
            return _Value(_STATIC)
        if isinstance(node, ast.Name):
            if node.id in frame.environment:
                return frame.environment[node.id]
            if node.id in _STATIC_BUILTINS:
                return _Value(_STATIC, reference=getattr(builtins, node.id, None))
            module_path = _unit_module_path(frame.unit)
            if node.id in self._module_state_names(module_path, frame.unit.module):
                return _Value(_RUNTIME, origin=f"module state {node.id}")
            reference = _module_reference(frame.unit.module, node.id)
            if reference is not None:
                return _Value(_STATIC, reference=reference)
            return _Value(_UNKNOWN)
        if isinstance(node, ast.Constant):
            return _Value(_STATIC)
        if isinstance(node, (ast.List, ast.Set, ast.Tuple, ast.Dict)):
            for child in ast.iter_child_nodes(node):
                self._eval(child, frame)
            return _Value(_OWNED)
        if isinstance(node, ast.Lambda):
            closure = self._nested_closure(node, frame)
            self._closures[closure.unit.key] = closure
            return _Value(_CALLABLE, origin="locally defined lambda", callable_id=closure.unit.key)
        if isinstance(node, ast.Attribute):
            base = self._eval(node.value, frame)
            if base.kind == _ENVELOPE and node.attr in _INPUT_VALUE_FIELDS:
                return _Value(_RUNTIME, origin="envelope value")
            if base.kind == _RUNTIME:
                return _Value(_RUNTIME, origin=base.origin)
            reference = _static_attribute(base.reference, node.attr)
            if reference is not None:
                return _Value(_STATIC, reference=reference)
            return base if base.kind in {_INPUTS, _ENVELOPE, _OWNED} else _Value(_UNKNOWN)
        if isinstance(node, ast.Subscript):
            base = self._eval(node.value, frame)
            self._eval(node.slice, frame)
            key = _literal_string(node.slice)
            if base.kind == _INPUTS:
                return _Value(_ENVELOPE, origin="input envelope")
            if base.kind == _ENVELOPE and key in _INPUT_VALUE_FIELDS:
                return _Value(_RUNTIME, origin="envelope value")
            if base.kind == _RUNTIME:
                return _Value(_RUNTIME, origin=base.origin)
            if base.kind == _OWNED:
                return _Value(_UNKNOWN)
            return _Value(_UNKNOWN)
        if isinstance(node, ast.Call):
            return self._call(node, frame)
        if isinstance(node, ast.IfExp):
            self._eval(node.test, frame)
            return _merge_values(self._eval(node.body, frame), self._eval(node.orelse, frame))
        if isinstance(node, ast.NamedExpr):
            value = self._eval(node.value, frame)
            self._assign(node.target, value, frame)
            return value
        if isinstance(node, (ast.Await, ast.Yield, ast.YieldFrom, ast.Starred)):
            return self._eval(node.value, frame)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            return self._comprehension(node, frame)
        if isinstance(node, ast.DictComp):
            self._comprehension(node, frame)
            return _Value(_OWNED)
        if isinstance(node, (ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self._eval(child, frame)
            return _Value(_STATIC)
        if isinstance(node, ast.JoinedStr):
            for value in node.values:
                self._eval(value, frame)
            return _Value(_STATIC)
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._eval(child, frame)
        return _Value(_UNKNOWN)

    def _call(self, node: ast.Call, frame: _Frame) -> _Value:
        function = self._eval(node.func, frame)
        arguments = [self._eval(item, frame) for item in node.args]
        keywords = {
            item.arg: self._eval(item.value, frame)
            for item in node.keywords
            if item.arg is not None
        }

        name = _call_name(node.func)
        leaf = name.rsplit(".", 1)[-1]
        if name in {"getattr", "builtins.getattr"} and arguments:
            if arguments[0].kind == _RUNTIME:
                return _Value(_RUNTIME, origin=arguments[0].origin)
            reference = arguments[0].reference
            attribute = _literal_string(node.args[1]) if len(node.args) >= 2 else ""
            resolved = _static_attribute(reference, attribute) if attribute else None
            return _Value(_STATIC, reference=resolved) if resolved is not None else _Value(_UNKNOWN)

        if isinstance(node.func, ast.Attribute):
            receiver = self._eval(node.func.value, frame)
            if receiver.kind == _INPUTS and leaf == "get":
                return _Value(_ENVELOPE, origin="input envelope")
            if receiver.kind == _ENVELOPE and leaf == "get":
                key = _literal_string(node.args[0]) if node.args else ""
                if key in _INPUT_VALUE_FIELDS:
                    return _Value(_RUNTIME, origin="envelope value")
                return _Value(_UNKNOWN)
            if receiver.kind == _RUNTIME and leaf in _READ_ONLY_MAPPING_METHODS:
                return _Value(_RUNTIME, origin=receiver.origin)

        closure = self._closure_for(function, frame)
        if closure is not None:
            bound = _bind_call_arguments(closure.unit.node, arguments, keywords)
            return self.analyze(
                closure.unit,
                bound,
                closure_environment=closure.environment,
            )

        helper = self._helper_unit(node.func, function, frame)
        if helper is not None:
            helper_arguments = arguments
            if (
                helper.owner_class
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in {"self", "cls"}
            ):
                helper_arguments = [_Value(_OWNED), *arguments]
            bound = _bind_call_arguments(helper.node, helper_arguments, keywords)
            return self.analyze(helper, bound)

        if function.kind == _RUNTIME:
            self._record_site(node, frame, function)
            return _Value(_RUNTIME, origin=function.origin)

        if leaf in _ITERATOR_BUILTINS and arguments:
            return _runtime_child(arguments[0], arguments[0].origin)
        if leaf in _VALUE_PRESERVING_BUILTINS and arguments:
            return _runtime_child(arguments[0], arguments[0].origin)
        if function.kind in {_STATIC, _OWNED} or leaf in _STATIC_BUILTINS:
            return _Value(_OWNED)
        return _Value(_UNKNOWN)

    def _closure_for(self, value: _Value, frame: _Frame) -> _Closure | None:
        if value.kind != _CALLABLE or not value.callable_id:
            return None
        return frame.closures.get(value.callable_id) or self._closures.get(value.callable_id)

    def _helper_unit(self, expression: ast.AST, function: _Value, frame: _Frame) -> _FunctionUnit | None:
        if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
            if expression.value.id in {"self", "cls"}:
                module_path = _unit_module_path(frame.unit)
                method = self._class_method(module_path, frame.unit.owner_class, expression.attr)
                if method is not None:
                    return _FunctionUnit(
                        key=f"{module_path}:{frame.unit.owner_class}.{expression.attr}",
                        node=method,
                        path=module_path,
                        line_offset=0,
                        module=frame.unit.module,
                        owner_class=frame.unit.owner_class,
                    )
        if isinstance(expression, ast.Name):
            module_path = _unit_module_path(frame.unit)
            helper = self._module_function(module_path, expression.id, frame.unit.module)
            if helper is not None:
                return _FunctionUnit(
                    key=f"{module_path}:{expression.id}",
                    node=helper,
                    path=module_path,
                    line_offset=0,
                    module=frame.unit.module,
                )
        reference = function.reference
        if not inspect.isfunction(reference) or not self._is_local_helper(reference):
            return None
        return self._unit_from_function(reference)

    def _unit_from_function(self, function: Any) -> _FunctionUnit | None:
        try:
            path = inspect.getsourcefile(function) or ""
            lines, start = inspect.getsourcelines(function)
            tree = ast.parse(textwrap.dedent("".join(lines)), filename=path)
        except (OSError, TypeError, SyntaxError):
            return None
        node = next(
            (
                item
                for item in tree.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            ),
            None,
        )
        if node is None:
            return None
        module = inspect.getmodule(function)
        return _FunctionUnit(
            key=f"{path}:{getattr(function, '__qualname__', function.__name__)}",
            node=node,
            path=path,
            line_offset=start - 1,
            module=module,
        )

    def _is_local_helper(self, function: Any) -> bool:
        path = inspect.getsourcefile(function)
        if not path or not path.endswith(".py"):
            return False
        resolved = _absolute_path(path)
        parts = set(resolved.split(os.sep))
        if {"site-packages", "dist-packages"} & parts:
            return False
        try:
            common = os.path.commonpath((self.project_root, resolved))
        except ValueError:
            return False
        return common == self.project_root

    def _nested_closure(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, frame: _Frame) -> _Closure:
        name = getattr(node, "name", "lambda")
        line = int(getattr(node, "lineno", 1)) + frame.unit.line_offset
        unit = _FunctionUnit(
            key=f"{frame.unit.key}:{name}@{line}",
            node=node,
            path=frame.unit.path,
            line_offset=frame.unit.line_offset,
            module=frame.unit.module,
            owner_class=frame.unit.owner_class,
        )
        return _Closure(unit=unit, environment=dict(frame.environment))

    def _comprehension(self, node: ast.AST, frame: _Frame) -> _Value:
        local = _Frame(frame.unit, dict(frame.environment), dict(frame.closures))
        generators = getattr(node, "generators", ())
        for generator in generators:
            iterable = self._eval(generator.iter, local)
            self._assign(generator.target, _runtime_child(iterable, iterable.origin), local)
            for condition in generator.ifs:
                self._eval(condition, local)
        if isinstance(node, ast.DictComp):
            self._eval(node.key, local)
            self._eval(node.value, local)
        else:
            self._eval(getattr(node, "elt", None), local)
        return _Value(_OWNED)

    def _assign(self, target: ast.AST, value: _Value, frame: _Frame) -> None:
        if isinstance(target, ast.Name):
            frame.environment[target.id] = value
            if value.kind == _CALLABLE and value.callable_id in self._closures:
                frame.closures[value.callable_id] = self._closures[value.callable_id]
        elif isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._assign(item, _runtime_child(value, value.origin), frame)

    def _record_site(self, node: ast.Call, frame: _Frame, function: _Value) -> None:
        line = int(getattr(node, "lineno", 1)) + frame.unit.line_offset
        column = int(getattr(node, "col_offset", 0)) + 1
        expression = _expression_text(node.func)
        kind = "callable"
        if isinstance(node.func, ast.Attribute):
            kind = "method"
        elif isinstance(node.func, ast.Call) and _call_name(node.func.func).rsplit(".", 1)[-1] == "getattr":
            kind = "getattr"
        key = (frame.unit.path, line, column, expression)
        if key in self._site_keys:
            return
        self._site_keys.add(key)
        self.sites.append(
            RuntimeDispatchSite(
                path=frame.unit.path,
                line=line,
                column=column,
                dispatch_kind=kind,
                expression=expression,
                origin=function.origin or "runtime value",
            )
        )

    def _module_state_names(self, path: str, module: ModuleType | None) -> set[str]:
        resolved = _absolute_path(path) if path else path
        if resolved not in self._module_state:
            tree = self._tree_for_module(resolved, module)
            self._module_state[resolved] = _mutable_module_state_names(tree) if tree is not None else set()
        return self._module_state[resolved]

    def _module_function(self, path: str, name: str, module: ModuleType | None):
        resolved = _absolute_path(path) if path else path
        if resolved not in self._module_functions:
            tree = self._tree_for_module(resolved, module)
            self._module_functions[resolved] = _top_level_functions(tree) if tree is not None else {}
        return self._module_functions[resolved].get(name)

    def _class_method(self, path: str, owner: str, name: str):
        resolved = _absolute_path(path) if path else path
        key = f"{resolved}:{owner}"
        if key not in self._class_functions:
            tree = self._tree_for_module(resolved, None)
            self._class_functions[key] = _class_functions(tree, owner) if tree is not None else {}
        return self._class_functions[key].get(name)

    def _tree_for_module(self, path: str, module: ModuleType | None) -> ast.Module | None:
        if path in self._module_trees:
            return self._module_trees[path]
        text = ""
        try:
            if module is None:
                return None
            text = inspect.getsource(module)
            tree = ast.parse(text, filename=path)
        except (OSError, TypeError, SyntaxError):
            return None
        self._module_trees[path] = tree
        return tree


def _bind_initial_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, _Value]:
    parameters = _parameters(node)
    values: dict[str, _Value] = {}
    for name in parameters:
        if name == "inputs":
            values[name] = _Value(_INPUTS, origin="input envelope")
        elif name in {"self", "cls", "params"}:
            values[name] = _Value(_OWNED)
        else:
            values[name] = _Value(_UNKNOWN)
    return values


def _bind_call_arguments(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    positional: list[_Value],
    keywords: Mapping[str, _Value],
) -> dict[str, _Value]:
    names = _parameters(node)
    bound = {name: _Value(_UNKNOWN) for name in names}
    for index, value in enumerate(positional):
        if index < len(names):
            bound[names[index]] = value
    for name, value in keywords.items():
        if name in bound:
            bound[name] = value
    return bound


def _parameters(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> list[str]:
    names = [
        argument.arg
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    ]
    if node.args.vararg is not None:
        names.append(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.append(node.args.kwarg.arg)
    return names


def _mutable_module_state_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    static_names = set(_STATIC_BUILTINS)
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            static_names.add(statement.name)
        elif isinstance(statement, ast.Import):
            static_names.update(
                alias.asname or alias.name.split(".", 1)[0]
                for alias in statement.names
            )
        elif isinstance(statement, ast.ImportFrom):
            static_names.update(
                alias.asname or alias.name
                for alias in statement.names
                if alias.name != "*"
            )
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = set().union(*(_target_names(target) for target in statement.targets))
            if _module_value_is_runtime_state(statement.value, static_names):
                names.update(targets)
            else:
                static_names.update(targets)
        elif isinstance(statement, ast.AnnAssign):
            targets = _target_names(statement.target)
            if statement.value is None or _module_value_is_runtime_state(statement.value, static_names):
                names.update(targets)
            else:
                static_names.update(targets)
    return names - _METADATA_NAMES


def _module_value_is_runtime_state(value: ast.AST, static_names: set[str]) -> bool:
    if isinstance(value, (ast.Dict, ast.List, ast.Set, ast.Call)):
        return True
    if isinstance(value, ast.Lambda):
        return False
    if isinstance(value, ast.Constant):
        return value.value is None
    if isinstance(value, ast.Tuple):
        return any(_module_value_is_runtime_state(item, static_names) for item in value.elts)
    if isinstance(value, ast.Name):
        return value.id not in static_names
    if isinstance(value, ast.Attribute):
        return _reference_root(value) not in static_names
    return True


def _top_level_functions(tree: ast.Module | None) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    if tree is None:
        return {}
    return {
        item.name: item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _class_functions(tree: ast.Module | None, owner: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    if tree is None:
        return {}
    class_node = next(
        (item for item in tree.body if isinstance(item, ast.ClassDef) and item.name == owner),
        None,
    )
    if class_node is None:
        return {}
    return {
        item.name: item
        for item in class_node.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _module_reference(module: ModuleType | None, name: str) -> object | None:
    if module is None:
        return None
    return vars(module).get(name)


def _static_attribute(reference: object | None, attribute: str) -> object | None:
    if reference is None or not attribute:
        return None
    try:
        return inspect.getattr_static(reference, attribute)
    except (AttributeError, TypeError):
        return None


def _unit_module_path(unit: _FunctionUnit) -> str:
    path = unit.path
    return _absolute_path(path) if path else path


def _absolute_path(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _project_root(source_path: str) -> str:
    """Infer the import root without traversing or reading the project tree."""

    candidates: list[str] = []
    filesystem_root = os.path.abspath(os.sep)
    for raw_entry in sys.path:
        entry = _absolute_path(raw_entry or os.getcwd())
        if entry == filesystem_root:
            continue
        try:
            if os.path.commonpath((entry, source_path)) == entry:
                candidates.append(entry)
        except ValueError:
            continue
    if candidates:
        return max(candidates, key=len)
    return os.path.dirname(source_path)


def _merge_values(*values: _Value) -> _Value:
    values = tuple(values)
    if not values:
        return _Value(_UNKNOWN)
    for kind in (_RUNTIME, _ENVELOPE, _INPUTS, _CALLABLE, _OWNED, _STATIC, _UNKNOWN):
        matches = [value for value in values if value.kind == kind]
        if matches:
            first = matches[0]
            if all(value.kind == kind for value in values):
                return first
            if kind in {_RUNTIME, _ENVELOPE, _INPUTS}:
                return first
    return _Value(_UNKNOWN)


def _merge_environments(*environments: Mapping[str, _Value]) -> dict[str, _Value]:
    names = set().union(*(environment.keys() for environment in environments))
    return {
        name: _merge_values(
            *(environment.get(name, _Value(_UNKNOWN)) for environment in environments)
        )
        for name in names
    }


def _runtime_child(value: _Value, origin: str) -> _Value:
    if value.kind in {_RUNTIME, _ENVELOPE, _INPUTS}:
        return _Value(_RUNTIME, origin=origin or value.origin or "runtime value")
    return _Value(_UNKNOWN)


def _target_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return set().union(*(_target_names(item) for item in target.elts)) if target.elts else set()
    return set()


def _reference_root(node: ast.AST) -> str:
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""


def _pattern_names(pattern: ast.pattern) -> set[str]:
    return {
        node.id
        for node in ast.walk(pattern)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }


def _literal_string(node: ast.AST) -> str:
    return str(node.value) if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def _expression_text(node: ast.AST) -> str:
    try:
        text = ast.unparse(node)
    except (AttributeError, ValueError):
        text = node.__class__.__name__
    return text if len(text) <= 160 else f"{text[:157]}..."


__all__ = [
    "RuntimeDispatchAnalysis",
    "RuntimeDispatchSite",
    "analyze_runtime_dispatch",
]
