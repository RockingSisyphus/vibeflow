"""Finite direct input writes; no helper, closure or execution-path propagation."""
import ast
from vibeflow.targets.python.quality.source_analysis.bindings import (
    _bound_names, _comprehension_evaluation_steps, _comprehension_outer_bindings,
    _function_definition_expressions, _FunctionBindingCollector,
)


def direct_input_writes(function, *, mutating_methods):
    """Inspect entry-bound inputs and straight-line aliases, borrowing its AST."""
    parameters = (*function.args.posonlyargs, *function.args.args, *function.args.kwonlyargs)
    if not any(item.arg == "inputs" for item in parameters):
        return ()
    scanner = _DirectInputWrites(mutating_methods)
    scanner.references = {"inputs"}
    for statement in function.body:
        scanner.visit(statement)
    return tuple(scanner.writes)


class _DirectInputWrites(ast.NodeVisitor):
    def __init__(self, methods):
        self.methods = frozenset(methods)
        self.references = set()
        self.writes = []

    def _reference(self, node):
        while isinstance(node, (ast.Attribute, ast.Subscript, ast.NamedExpr)):
            node = node.value
        return isinstance(node, ast.Name) and node.id in self.references

    def _target(self, target, statement):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._target(item, statement)
        elif isinstance(target, ast.Starred):
            self._target(target.value, statement)
        elif isinstance(target, (ast.Subscript, ast.Attribute)) and self._reference(target.value):
            self.writes.append(statement)

    def _assignment(self, node, targets):
        # The value is evaluated before rebinding a target; no call result is an alias.
        self.visit(node.value)
        is_reference = self._reference(node.value)
        for target in targets:
            self._target(target, node)
            self.visit(target)
            self.references.difference_update(_bound_names(target))
            if is_reference and isinstance(target, ast.Name):
                self.references.add(target.id)

    def visit_Assign(self, node):
        self._assignment(node, node.targets)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self._assignment(node, (node.target,))
        else:
            self.visit(node.target)

    def visit_NamedExpr(self, node):
        self._assignment(node, (node.target,))

    def visit_AugAssign(self, node):
        self._target(node.target, node)
        self.generic_visit(node)
        self.references.difference_update(_bound_names(node.target))

    def visit_Delete(self, node):
        for target in node.targets:
            self._target(target, node)
            self.visit(target)
            self.references.difference_update(_bound_names(target))

    def visit_Call(self, node):
        if (isinstance(node.func, ast.Attribute) and node.func.attr in self.methods
                and self._reference(node.func.value)):
            self.writes.append(node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        for expression in _function_definition_expressions(node):
            self.visit(expression)
        self.references.discard(node.name)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        for expression in (*node.bases, *(item.value for item in node.keywords), *node.decorator_list):
            self.visit(expression)
        self.references.discard(node.name)

    def visit_Lambda(self, node):
        for expression in _function_definition_expressions(node):
            self.visit(expression)

    def visit_ListComp(self, node):
        before = set(self.references)
        try:
            for expression, local_names in _comprehension_evaluation_steps(node):
                self.references.difference_update(local_names or ())
                self.visit(expression)
        finally:
            self.references = before - _comprehension_outer_bindings(node)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    def visit_GeneratorExp(self, node):
        # Only creation of the first iterable is immediate; no consumption proof.
        self.visit(node.generators[0].iter)

    def _fork(self, node, prefix, branches):
        before = set(self.references)
        try:
            self.visit(prefix)
            entry = set(self.references)
            for branch in branches:
                self.references = set(entry)
                for item in branch:
                    self.visit(item)
                if isinstance(node, ast.Match):
                    # A failed pattern/guard may bind before trying the next
                    # case; only the case body is mutually exclusive.
                    case = branch[0]
                    entry.difference_update(_rebound_names(case.pattern))
                    if case.guard is not None:
                        entry.difference_update(_rebound_names(case.guard))
        finally:
            # Siblings start at the same lexical identity. Rebinding in any
            # branch becomes unknown afterwards, without joining paths.
            self.references = before - _rebound_names(node)

    def visit_If(self, node):
        self._fork(node, node.test, (node.body, node.orelse))

    def visit_IfExp(self, node):
        self._fork(node, node.test, ((node.body,), (node.orelse,)))

    def visit_Match(self, node):
        self._fork(node, node.subject, ((case,) for case in node.cases))

    def _compound(self, node):
        before = set(self.references)
        try:
            for field, value in ast.iter_fields(node):
                self.references = set(before)
                if isinstance(node, (ast.For, ast.AsyncFor)) and field in {"body", "orelse"}:
                    self.references.difference_update(_bound_names(node.target))
                if isinstance(node, (ast.With, ast.AsyncWith)) and field == "body":
                    for item in node.items:
                        self.references.difference_update(_bound_names(item.optional_vars))
                if isinstance(node, ast.match_case):
                    self.references.difference_update(_rebound_names(node.pattern))
                if isinstance(node, ast.ExceptHandler) and node.name:
                    self.references.discard(node.name)
                if isinstance(value, list):
                    entry = set(self.references)
                    for item in value:
                        if isinstance(item, ast.AST):
                            if field == "handlers":
                                self.references = set(entry)
                            self.visit(item)
                            if field == "handlers" and item.type is not None:
                                # Exception types are evaluated in order;
                                # aliases and bodies bind only when selected.
                                entry.difference_update(_rebound_names(item.type))
                elif isinstance(value, ast.AST):
                    self.visit(value)
                # A later field must not resurrect a name rebound in an
                # earlier expression or branch. Conditional bindings become
                # unknown; we do not join paths or propagate new aliases.
                # A loop target binds after its iterable is evaluated.
                if field != "target":
                    for item in value if isinstance(value, list) else (value,):
                        if isinstance(item, ast.AST):
                            before.difference_update(_rebound_names(item))
        finally:
            # No union, fixed point or path proof: names rebound anywhere in a
            # compound statement become unknown after it. Direct roots remain
            # available when that statement did not rebind them.
            self.references = before - _rebound_names(node)

    visit_For = _compound
    visit_AsyncFor = _compound
    visit_While = _compound
    visit_Try = _compound
    visit_TryStar = _compound
    visit_With = _compound
    visit_AsyncWith = _compound
    visit_ExceptHandler = _compound
    visit_match_case = _compound
    visit_BoolOp = _compound

    def visit_Import(self, node):
        self.references.difference_update(alias.asname or alias.name.split(".", 1)[0] for alias in node.names)

    def visit_ImportFrom(self, node):
        self.references.difference_update(alias.asname or alias.name for alias in node.names)


def _rebound_names(node):
    bindings = _FunctionBindingCollector()
    bindings.visit(node)
    return bindings.names
