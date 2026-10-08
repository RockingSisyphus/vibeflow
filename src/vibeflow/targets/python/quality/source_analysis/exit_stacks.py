"""Source-visible ExitStack receivers and deferred calls; never execute callbacks."""

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from vibeflow.targets.python.quality.source_analysis.ast_rules import (
    import_aliases_from_node, qualified_call_name, record_assignment_aliases,
)
from vibeflow.targets.python.quality.source_analysis.bindings import _function_bindings


_STACK = "contextlib.ExitStack.instance"


@dataclass(frozen=True)
class ExitStackCalls:
    closes: frozenset[int]
    deferred: Mapping[int, ast.Call]


def analyze_exit_stacks(tree, initial_aliases=None):
    collector = _StackBindings(initial_aliases)
    collector.visit(tree)
    memo = {}

    def is_stack(value, active=frozenset()):
        if value == _STACK:
            return True
        if not isinstance(value, tuple) or value in active:
            return False
        if value not in memo:
            assignments = collector.values.get(value, ())
            # None is a normal initializer for an instance field. A concrete
            # constructor assignment must still exist; unknown writes reject it.
            concrete = [item for item in assignments if item != "none"]
            memo[value] = bool(concrete) and all(is_stack(item, active | {value}) for item in concrete)
        return memo[value]

    closes, deferred = set(), {}
    for call, receiver, method, aliases, callback_receiver in collector.calls:
        if not is_stack(receiver):
            continue
        if method == "close":
            closes.add(id(call))
        elif method in {"callback", "push"} and call.args:
            function = call.args[0]
            args, keywords = list(call.args[1:]), list(call.keywords)
            if isinstance(function, ast.Call) and qualified_call_name(function.func, aliases) == "functools.partial" and function.args:
                args = [*function.args[1:], *args]
                keywords = [*function.keywords, *keywords]
                function = function.args[0]
            # Attribute/callable references are reviewed as the invocation that
            # ExitStack will perform later. Bodies remain in the normal scan.
            invocation = ast.copy_location(ast.Call(func=function, args=args, keywords=keywords), call)
            invocation._source_reference_position = (getattr(function, "lineno", call.lineno),
                getattr(function, "col_offset", call.col_offset) + 1)
            deferred[id(call)] = invocation
            if is_stack(callback_receiver):
                closes.add(id(invocation))
    return ExitStackCalls(frozenset(closes), MappingProxyType(deferred))


class _StackBindings(ast.NodeVisitor):
    def __init__(self, aliases):
        self.aliases = dict(aliases or {})
        self.scope = ()
        self.owner = ()
        self.bindings = []
        self.values = {}
        self.calls = []

    def key(self, expression):
        if isinstance(expression, ast.Name):
            for scope, names in reversed(self.bindings):
                if expression.id in names:
                    return (scope, expression.id)
            return ((), expression.id)
        if isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name) and expression.value.id == "self":
            return (self.owner, "self." + expression.attr)
        return "unknown"

    def value(self, expression):
        if isinstance(expression, ast.Call) and qualified_call_name(expression.func, self.aliases) == "contextlib.ExitStack":
            return _STACK
        if isinstance(expression, ast.Constant) and expression.value is None:
            return "none"
        return self.key(expression)

    def visit_Import(self, node):
        self.aliases.update(import_aliases_from_node(node))

    visit_ImportFrom = visit_Import

    def visit_ClassDef(self, node):
        previous_owner, previous_scope = self.owner, self.scope
        self.scope = (*self.scope, node.name)
        self.owner = self.scope
        for statement in node.body:
            self.visit(statement)
        self.owner, self.scope = previous_owner, previous_scope

    def visit_FunctionDef(self, node):
        previous_aliases, previous_scope = dict(self.aliases), self.scope
        names, _ = _function_bindings(node)
        self.scope = (*self.scope, node.name)
        self.bindings.append((self.scope, names))
        for name in names:
            self.aliases.pop(name, None)
        for statement in node.body:
            self.visit(statement)
        self.bindings.pop()
        self.aliases, self.scope = previous_aliases, previous_scope

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Assign(self, node):
        value = self.value(node.value)
        for target in node.targets:
            key = self.key(target)
            if isinstance(key, tuple):
                self.values.setdefault(key, []).append(value)
        self.visit(node.value)
        record_assignment_aliases(node, self.aliases)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit_Assign(ast.copy_location(ast.Assign(targets=[node.target], value=node.value), node))

    def visit_NamedExpr(self, node):
        self.visit_Assign(ast.copy_location(ast.Assign(targets=[node.target], value=node.value), node))

    def visit_With(self, node):
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                key = self.key(item.optional_vars)
                if isinstance(key, tuple):
                    self.values.setdefault(key, []).append(self.value(item.context_expr))
        for statement in node.body:
            self.visit(statement)

    def visit_Call(self, node):
        function = node.func
        if isinstance(function, ast.Name) and function.id in self.aliases:
            try:
                function = ast.parse(self.aliases[function.id], mode="eval").body
            except SyntaxError:
                function = node.func
        if isinstance(function, ast.Attribute) and function.attr in {"close", "callback", "push"}:
            callback_receiver = "unknown"
            if node.args:
                callback = node.args[0]
                if isinstance(callback, ast.Name) and callback.id in self.aliases:
                    try:
                        callback = ast.parse(self.aliases[callback.id], mode="eval").body
                    except SyntaxError:
                        pass
                if isinstance(callback, ast.Attribute) and callback.attr == "close":
                    callback_receiver = self.value(callback.value)
            self.calls.append((node, self.value(function.value), function.attr, dict(self.aliases), callback_receiver))
        self.generic_visit(node)
