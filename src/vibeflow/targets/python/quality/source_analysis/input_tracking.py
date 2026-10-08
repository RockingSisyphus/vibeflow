from __future__ import annotations

import ast

from vibeflow.targets.python.quality.source_analysis.ast_rules import name_targets
from vibeflow.targets.python.quality.source_analysis.bindings import _comprehension_evaluation_steps, _function_definition_expressions, _function_scope_bindings
from vibeflow.targets.python.quality.source_analysis.helpers import _dict_literal_keys, _literal_subscript_key
from vibeflow.targets.python.quality.source_analysis.types import MUTATING_METHODS


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
    sources: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, set[str]]] = [
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
        for call, input_arguments in _input_call_facts(source, seeds).items():
            if not isinstance(call.func, ast.Name) or call.func.id not in helpers:
                continue
            next_names = _tainted_helper_parameters(call, helpers[call.func.id], input_arguments)
            unseen = next_names - tainted[call.func.id]
            if unseen:
                tainted[call.func.id].update(unseen)
                sources.append((helpers[call.func.id], set(tainted[call.func.id])))
    return tainted


def source_input_parameters(sources, node) -> dict[str, set[str]]:
    """Propagate input ownership along resolved, project-local symbol calls."""
    symbols = {item.id:item for item in sources.helpers(node.type_key) if isinstance(item._node,(ast.FunctionDef,ast.AsyncFunctionDef))}
    seeds = {key:{"inputs"} for key,item in symbols.items() if item.path == node.path and item.name.startswith(node.symbol+".") and item.name.endswith(".run_pure")}
    tainted = {key:set(value) for key,value in seeds.items()}
    pending = list(seeds)
    while pending:
        key = pending.pop()
        symbol = symbols[key]
        references = {(ref.line,ref.column):ref.target for ref in sources.references
                      if ref.source.rpartition(":")[0] == symbol.path and ref.kind == "call"}
        for call, input_arguments in _input_call_facts(symbol._node, tainted[key]).items():
            target = symbols.get(references.get((call.lineno,call.col_offset+1)))
            if target is None:
                continue
            helper = target._node
            bound_method = (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
                            and call.func.value.id in {"self", "cls"})
            names = _tainted_helper_parameters(call, helper, input_arguments, bound_method=bound_method)
            unseen = names-tainted.setdefault(target.id,set())
            if unseen:
                tainted[target.id].update(unseen)
                pending.append(target.id)
    return tainted


def _called_module_helpers(node: ast.AST, helpers: dict[str, ast.AST]) -> set[str]:
    return {
        child.func.id
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id in helpers
    }


def _input_call_facts(node: ast.FunctionDef | ast.AsyncFunctionDef, seeds: set[str]):
    """Possible input ownership of actual arguments within each lexical scope."""
    return _InputCallFacts(node, seeds).collect()


class _InputCallFacts(ast.NodeVisitor):
    def __init__(self, root, seeds):
        self.root, self.seeds = root, set(seeds)
        self.assigned = {}
        self.bindings = {}
        self.comprehension_names = {}
        self.calls = {}

    def collect(self):
        # Keep assignment possibilities across branches, loops and closures.
        # Only aliases derived in the same lexical scope participate in this
        # finite fixed point; a comprehension target never becomes an alias.
        while True:
            self.changed = False
            self.aliases, self.frames = set(), []
            self.visit(self.root)
            if not self.changed:
                return self.calls

    def visit_FunctionDef(self, node):
        for expression in _function_definition_expressions(node):
            self.visit(expression)
        bindings = self.bindings.get(node)
        if bindings is None:
            bindings = self.bindings[node] = _function_scope_bindings(node)
        local = bindings.names - bindings.global_names - bindings.nonlocal_names
        aliases = self.aliases - local - bindings.global_names
        aliases |= self.assigned.get(node, set())
        if node is self.root:
            aliases |= self.seeds
        previous = self.aliases
        self.aliases = aliases
        self.frames.append((node, aliases, False))
        aliases.update(name for name in self.assigned.get(None, ())
                       if self._declared_binding_frame(name) is None)
        try:
            if isinstance(node, ast.Lambda):
                self.visit(node.body)
            else:
                for statement in node.body:
                    self.visit(statement)
        finally:
            self.frames.pop()
            self.aliases = previous

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef

    def visit_ListComp(self, node):
        previous, entered = self.aliases, False
        try:
            for expression, bound in _comprehension_evaluation_steps(node):
                if bound is not None and not entered:
                    self.aliases = self.aliases - bound
                    self.comprehension_names[node] = bound
                    self.frames.append((node, self.aliases, True))
                    entered = True
                self.visit(expression)
        finally:
            if entered:
                self.frames.pop()
            self.aliases = previous

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def _declared_binding_frame(self, name, frames=None, *, containing=False):
        # None is the module owner. An external nonlocal cell can be represented
        # only inside the selected function root; never treat it as a global.
        external_nonlocal = None
        for frame in reversed(self.frames if frames is None else frames):
            node, _, comprehension = frame
            if comprehension:
                if not containing and name in self.comprehension_names[node]:
                    return frame
                continue
            bindings = self.bindings[node]
            if name in bindings.global_names:
                return None
            if name in bindings.nonlocal_names:
                if external_nonlocal is None:
                    external_nonlocal = frame
                continue
            if name in bindings.names:
                return frame
        return external_nonlocal

    def _record_alias(self, target, *, containing=False):
        if not isinstance(target, ast.Name) or not self.frames:
            return
        frame = self._declared_binding_frame(target.id, containing=containing)
        owner = frame[0] if frame is not None else None
        known = self.assigned.setdefault(owner, set())
        if target.id not in known:
            known.add(target.id)
            self.changed = True
        # A declared nonlocal/global write may escape its immediate function.
        # Preserve the possible alias only in scopes reading that same binding;
        # a sibling local, lambda parameter or comprehension target stays local.
        for index, active in enumerate(self.frames):
            if self._declared_binding_frame(target.id, self.frames[:index + 1]) is frame:
                active[1].add(target.id)

    def visit_Assign(self, node):
        self.visit(node.value)
        owned = _is_input_reference(node.value, self.aliases)
        for target in node.targets:
            self.visit(target)
            if owned:
                self._record_alias(target)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit(node.value)
            if _is_input_reference(node.value, self.aliases):
                self._record_alias(node.target)
        self.visit(node.target)

    def visit_NamedExpr(self, node):
        self.visit(node.value)
        if _is_input_reference(node.value, self.aliases):
            self._record_alias(node.target, containing=True)

    def visit_Call(self, node):
        self.visit(node.func)
        arguments, keywords = [], []
        for argument in node.args:
            self.visit(argument)
            arguments.append(_is_input_reference(argument, self.aliases))
        for keyword in node.keywords:
            self.visit(keyword.value)
            keywords.append(_is_input_reference(keyword.value, self.aliases))
        previous = self.calls.get(node)
        if previous is not None:
            arguments = [current or earlier for current, earlier in zip(arguments, previous[0])]
            keywords = [current or earlier for current, earlier in zip(keywords, previous[1])]
        self.calls[node] = tuple(arguments), tuple(keywords)


def _tainted_helper_parameters(call, helper, input_arguments, *, bound_method=False) -> set[str]:
    positional = (*helper.args.posonlyargs, *helper.args.args)
    arguments, keywords = input_arguments
    if bound_method:
        arguments = (False, *arguments)
    tainted = {positional[index].arg for index, owned in enumerate(arguments)
               if owned and index < len(positional)}
    parameters = {arg.arg for arg in (*positional, *helper.args.kwonlyargs)}
    for keyword, owned in zip(call.keywords, keywords):
        if keyword.arg in parameters and owned:
            tainted.add(str(keyword.arg))
    return tainted


def _is_input_reference(node: ast.AST, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.NamedExpr):
        return _is_input_reference(node.value, aliases)
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
        del key_node, node

    def _check_assignment_target(self, target: ast.AST, node: ast.AST) -> None:
        if self._target_mutates_node_input(target):
            self._add("input_mutation", "node must not mutate inputs", node, suggested_fix_type="fix_node")
        if self._ambient_target(target):
            return
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id != "self":
            self._add("monkey_patch", "assigning to external object attributes is forbidden", node, suggested_fix_type="fix_node")

    def _target_mutates_node_input(self, target: ast.AST) -> bool:
        return isinstance(target, (ast.Subscript, ast.Attribute)) and self._is_node_input_reference(target.value)

    def _is_node_input_reference(self, node: ast.AST) -> bool:
        return _is_input_reference(node, self._input_aliases)

    def _return_keys(self, value: ast.AST | None) -> tuple[set[str] | None, bool]:
        if isinstance(value, ast.Dict):
            return _dict_literal_keys(value)
        if isinstance(value, ast.Name) and value.id in self._output_dicts:
            return set(self._output_dicts[value.id]), False
        return None, True


def _reference_root_name(node: ast.AST) -> str:
    while isinstance(node, (ast.Attribute, ast.Subscript)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else ""
