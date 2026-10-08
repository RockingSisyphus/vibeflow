"""Lexical bindings shared by Node and library source review."""

import ast


def _bound_names(target: ast.AST) -> set[str]:
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, ast.Starred):
        return _bound_names(target.value)
    if isinstance(target, (ast.List, ast.Tuple)):
        names: set[str] = set()
        for item in target.elts:
            names.update(_bound_names(item))
        return names
    return set()


def _comprehension_evaluation_steps(node):
    """Yield expressions with their enclosing or comprehension lexical scope."""
    names = frozenset().union(*(_bound_names(item.target) for item in node.generators))
    for index, generator in enumerate(node.generators):
        # All targets belong to the implicit comprehension scope, including
        # names not assigned yet. Only the first iterable uses its parent.
        yield generator.iter, None if index == 0 else names
        yield generator.target, names
        for condition in generator.ifs:
            yield condition, names
    if isinstance(node, ast.DictComp):
        yield node.key, names
        yield node.value, names
    else:
        yield node.elt, names


def _comprehension_outer_bindings(node):
    collector = _FunctionBindingCollector()
    collector.visit(node)
    return collector.names


def _function_definition_expressions(node):
    """Expressions inspected in the enclosing scope of a function definition."""
    yield from getattr(node, "decorator_list", ())
    yield from node.args.defaults
    yield from (expression for expression in node.args.kw_defaults if expression is not None)
    for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
                     *((node.args.vararg,) if node.args.vararg else ()),
                     *((node.args.kwarg,) if node.args.kwarg else ())):
        if argument.annotation is not None:
            yield argument.annotation
    if getattr(node, "returns", None) is not None:
        yield node.returns
    yield from getattr(node, "type_params", ())


def _function_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[set[str], set[str]]:
    collector = _function_scope_bindings(node)
    names = collector.names - collector.global_names - collector.nonlocal_names
    return names, collector.import_names


def _function_scope_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
) -> "_FunctionBindingCollector":
    collector = _FunctionBindingCollector()
    collector.names.update({
        argument.arg
        for argument in (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
        )
    })
    if node.args.vararg is not None:
        collector.names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        collector.names.add(node.args.kwarg.arg)
    if isinstance(node, ast.Lambda):
        collector.visit(node.body)
    else:
        for statement in node.body:
            collector.visit(statement)
    return collector


class _FunctionBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.names: set[str] = set()
        self.import_names: set[str] = set()
        self.global_names: set[str] = set()
        self.nonlocal_names: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        bound = {alias.asname or alias.name.split(".", 1)[0] for alias in node.names}
        self.names.update(bound)
        self.import_names.update(bound)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        bound = {alias.asname or alias.name for alias in node.names if alias.name != "*"}
        self.names.update(bound)
        self.import_names.update(bound)

    def visit_Global(self, node: ast.Global) -> None:
        self.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.nonlocal_names.update(node.names)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.names.add(node.name)
        for expression in _function_definition_expressions(node):
            self.visit(expression)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.names.add(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for expression in _function_definition_expressions(node):
            self.visit(expression)

    def visit_ListComp(self, node):
        targets = {generator.target for generator in node.generators}
        for expression, _ in _comprehension_evaluation_steps(node):
            if expression in targets:
                self._visit_comprehension_target(expression)
            else:
                self.visit(expression)

    visit_SetComp = visit_ListComp
    visit_DictComp = visit_ListComp
    visit_GeneratorExp = visit_ListComp

    def _visit_comprehension_target(self, target):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                self._visit_comprehension_target(item)
        elif isinstance(target, ast.Starred):
            self._visit_comprehension_target(target.value)
        elif not isinstance(target, ast.Name):
            # Indexed/attribute targets may themselves contain expressions.
            self.generic_visit(target)
