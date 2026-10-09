"""Python syntax and symbol ownership for an explicitly selected source scope."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from vibeflow.core.descriptors.models import NodeDescriptor
from vibeflow.targets.python.quality.source_analysis.bindings import _comprehension_evaluation_steps, _function_definition_expressions, _function_scope_bindings


@dataclass(frozen=True)
class PythonSourceFile:
    path: str
    module: str
    text: str
    root_id: str = ""
    _tree: ast.Module | None = field(default=None, compare=False, repr=False)
    parse_error: str = ""
    parse_line: int = 1
    parse_column: int = 1

    @property
    def tree(self) -> ast.Module | None:
        """An isolated view; a rule cannot mutate another rule's facts."""
        return deepcopy(self._tree)

    @classmethod
    def parse(cls, path: str, module: str, text: str, *, root_id: str = "") -> PythonSourceFile:
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError as exc:
            return cls(path, module, text, root_id, parse_error=str(exc),parse_line=exc.lineno or 1,parse_column=exc.offset or 1)
        return cls(path, module, text, root_id, tree)


@dataclass(frozen=True)
class PythonSymbol:
    path: str
    name: str
    kind: str
    line: int
    end_line: int
    _node: ast.AST = field(compare=False, repr=False)

    @property
    def node(self) -> ast.AST:
        return deepcopy(self._node)

    @property
    def id(self) -> str:
        return f"{self.path}:{self.name}"


@dataclass(frozen=True)
class PythonSourceNode:
    descriptor: NodeDescriptor
    path: str
    symbol: str
    root_id: str = ""
    calls: tuple[tuple[str, str], ...] = ()

    @property
    def type_key(self) -> str:
        return self.descriptor.type_key


@dataclass(frozen=True)
class PythonSourceReference:
    source: str
    target: str
    kind: str
    line: int
    column: int = 1


@dataclass(frozen=True)
class PythonSourceImport:
    path: str
    specifier: str
    module: str
    resolved_path: str
    symbol: str
    alias: str
    line: int
    column: int


@dataclass(frozen=True)
class PythonSourceOwnership:
    type_key: str
    symbol_id: str
    relation: str


@dataclass(frozen=True)
class PythonSourceCall:
    owner: str
    node_id: str
    type_key: str
    params: Mapping[str, object]
    source_path: str = ""
    local_id: str = ""
    call_path: tuple[str, ...] = ()

    def __post_init__(self):
        from vibeflow.core.rules.models import readonly
        object.__setattr__(self,"params",readonly(self.params))


@dataclass(frozen=True)
class PythonSourceContext:
    """A reusable snapshot, never a promise that references grant ownership.

    ``implementation`` identifies the declared class. ``helper_reference``
    records a reachable symbol and may have several owners. Domain rules must
    decide allowed definition locations rather than legalising whole modules.
    """

    nodes: tuple[PythonSourceNode, ...]
    files: tuple[PythonSourceFile, ...]
    symbols: tuple[PythonSymbol, ...]
    references: tuple[PythonSourceReference, ...]
    ownership: tuple[PythonSourceOwnership, ...]
    calls: tuple[PythonSourceCall, ...] = ()
    imports: tuple[PythonSourceImport, ...] = ()
    _analysis: object = field(default=None, init=False, compare=False, repr=False)

    def __post_init__(self):
        from vibeflow.targets.python.quality.analysis_metrics import PythonSourceAnalysis
        object.__setattr__(self, "_analysis", PythonSourceAnalysis())

    def metrics(self, type_key: str) -> Mapping[str, object]:
        """Read the same immutable measurements consumed by built-in Rules."""
        from dataclasses import asdict
        from vibeflow.core.rules import RuleContext
        from vibeflow.core.rules.models import readonly
        measured = self._analysis.measurements(RuleContext(facts={"source_context": self},
            subject={"type_key": type_key, "kind": "node"}, target="python"))
        if measured is None:
            raise ValueError(f"implementation measurements unavailable for {type_key}")
        return readonly(asdict(measured))

    def import_closure(self, path: str) -> tuple[PythonSourceFile, ...]:
        """Actual local module imports, including Python package initializers."""
        by_path = {source.path: source for source in self.files}
        by_module = {source.module: source for source in self.files}
        visited, pending = set(), [path]
        while pending:
            current = pending.pop()
            if current in visited or current not in by_path:
                continue
            visited.add(current)
            source = by_path[current]
            parts = source.module.split(".")
            for size in range(1, len(parts)):
                package = by_module.get(".".join(parts[:size]))
                if package is not None and package.path.endswith("/__init__.py"):
                    pending.append(package.path)
            pending.extend(item.resolved_path for item in self.imports
                           if item.path == current and item.resolved_path)
        return tuple(source for source in self.files if source.path in visited)

    def file(self, path: str) -> PythonSourceFile:
        return next(item for item in self.files if item.path == path)

    def symbol(self, path: str, name: str) -> PythonSymbol | None:
        return next((item for item in self.symbols if item.path == path and item.name == name), None)

    def owners(self, symbol_id: str) -> tuple[PythonSourceOwnership, ...]:
        return tuple(item for item in self.ownership if item.symbol_id == symbol_id)

    def call(self, owner: str, node_id: str) -> PythonSourceCall | None:
        return next((item for item in self.calls if item.owner == owner and item.node_id == node_id), None)

    def helpers(self, type_key: str) -> tuple[PythonSymbol, ...]:
        owned = {item.symbol_id for item in self.ownership if item.type_key == type_key and item.relation == "helper_reference"}
        return tuple(item for item in self.symbols if item.id in owned)

    def class_members(self, symbol: PythonSymbol) -> Mapping[str, PythonSymbol]:
        """Effective source-visible methods, including imported base classes."""
        from types import MappingProxyType
        from vibeflow.targets.python.quality.source_analysis.class_members import class_members
        return MappingProxyType(class_members(symbol, self.symbols, self.imports))

    def resolved_function_calls(self, path: str) -> frozenset[tuple[int, int]]:
        """Call/callable-reference sites with function bodies in this snapshot."""
        functions = {item.id for item in self.symbols if item.kind == "function"}
        callable_targets = functions | self._function_alias_globals(functions)
        return frozenset((item.line, item.column) for item in self.references
            if item.source.rpartition(":")[0] == path and item.target in callable_targets)

    def _function_alias_globals(self, functions):
        """Project explicit global value-reference chains without changing facts."""
        by_source = {}
        for reference in self.references:
            if reference.kind in {"global_reference", "callable_reference"}:
                by_source.setdefault(reference.source, []).append(reference)
        globals_ = {item.id: item for item in self.symbols if item.kind == "global"}
        targets = {}
        eligible = functions | set(globals_)
        for identity, symbol in globals_.items():
            value = getattr(symbol._node, "value", None)
            if not isinstance(value, (ast.Name, ast.Attribute)):
                continue
            candidates = {reference.target for reference in by_source.get(identity, ())
                if (reference.line, reference.column) == (value.lineno, value.col_offset + 1)
                and reference.target in eligible}
            if len(candidates) == 1:
                targets[identity] = candidates.pop()
        proven = set()
        for identity in targets:
            current, visited = identity, set()
            while current in targets and current not in visited:
                visited.add(current)
                current = targets[current]
            if current in functions:
                proven.add(identity)
        return proven

    def implementation_tree(self, path: str, name: str) -> ast.Module | None:
        """Isolate an exported implementation and its resolved local helpers."""
        return deepcopy(self._analysis._implementation_tree(self, path, name))


def build_python_source_context(nodes: Iterable[PythonSourceNode], files: Iterable[PythonSourceFile], *, calls: Iterable[PythonSourceCall] = ()) -> PythonSourceContext:
    selected_nodes = tuple(sorted(nodes, key=lambda item: (item.type_key, item.path, item.symbol)))
    selected_files = tuple(sorted(files, key=lambda item: item.path))
    symbols = tuple(symbol for source in selected_files if source._tree for symbol in _symbols(source))
    by_id = {symbol.id: symbol for symbol in symbols}
    by_module = {source.module: source.path for source in selected_files}
    imports = tuple(item for source in selected_files for item in _source_imports(source,by_module))
    from vibeflow.targets.python.quality.source_analysis.class_members import class_members
    members = {}
    for symbol in symbols:
        if symbol.kind == "class":
            try:
                members[symbol.id] = class_members(symbol, symbols, imports)
            except ValueError:
                members[symbol.id] = {}
    references: list[PythonSourceReference] = []
    for source in selected_files:
        for symbol in (item for item in symbols if item.path == source.path):
            if symbol.kind == "class":
                continue
            aliases = _symbol_bindings(symbol, symbols, imports, by_id, members)
            locals_ = _local_names(symbol._node)
            definition_aliases, definition_locals = _definition_scope_bindings(symbol, symbols, imports, by_id, members)
            expressions = tuple(_reference_scope_nodes(symbol._node, symbol.path, aliases, locals_,
                definition_aliases=definition_aliases, definition_locals=definition_locals))
            direct_callees = {id(item.func) for item, _, _ in expressions if isinstance(item, ast.Call)}
            for expression, expression_aliases, expression_locals in expressions:
                if isinstance(expression, ast.Call):
                    target = _resolve_call(expression.func, symbol, expression_aliases, by_id, members)
                    if target is not None:
                        references.append(PythonSourceReference(symbol.id, target, "call", expression.lineno,expression.col_offset+1))
                        if by_id[target].kind == "class":
                            for name in ("__init__", "__new__"):
                                method = members.get(target, {}).get(name)
                                if method is not None:
                                    references.append(PythonSourceReference(symbol.id, method.id, "constructor_call", expression.lineno,expression.col_offset+1))
                    if isinstance(expression.func, ast.Attribute):
                        receiver = _resolve_call(expression.func.value, symbol, expression_aliases, by_id, members)
                        if receiver is not None and by_id[receiver].kind == "class":
                            references.append(PythonSourceReference(symbol.id, receiver, "receiver", expression.lineno,expression.col_offset+1))
                elif isinstance(expression, (ast.Name, ast.Attribute)) and (
                        not isinstance(expression, ast.Name) or expression.id not in expression_locals):
                    if isinstance(expression, ast.Attribute) and expression.attr.startswith("_"):
                        receiver = _resolve_call(expression.value, symbol, expression_aliases, by_id, members)
                        if receiver is not None and by_id[receiver].kind == "class":
                            references.append(PythonSourceReference(symbol.id, receiver, "member_reference", expression.lineno, expression.col_offset + 1))
                    target = _resolve_call(expression, symbol, expression_aliases, by_id, members)
                    if target is not None and by_id[target].kind in {"global", "function"}:
                        if by_id[target].kind == "function" and id(expression) in direct_callees:
                            continue
                        kind = "global_reference" if by_id[target].kind == "global" else "callable_reference"
                        references.append(PythonSourceReference(symbol.id, target, kind, expression.lineno, expression.col_offset + 1))
    adjacency: dict[str, set[str]] = {}
    for reference in references:
        adjacency.setdefault(reference.source, set()).add(reference.target)
    ownership: list[PythonSourceOwnership] = []
    for node in selected_nodes:
        root_id = f"{node.path}:{node.symbol}"
        if root_id not in by_id:
            continue
        ownership.append(PythonSourceOwnership(node.type_key, root_id, "implementation"))
        from vibeflow.targets.python.quality.source_analysis.class_members import class_members
        try:
            seeds = [item.id for item in class_members(by_id[root_id], symbols, imports).values()]
        except ValueError:
            # An invalid MRO is a source fact; the interface Rule reports it.
            seeds = []
        visited: set[str] = set()
        pending = list(seeds)
        while pending:
            symbol_id = pending.pop()
            if symbol_id in visited:
                continue
            visited.add(symbol_id)
            ownership.append(PythonSourceOwnership(node.type_key, symbol_id, "helper_reference"))
            pending.extend(adjacency.get(symbol_id, ()))
    return PythonSourceContext(selected_nodes, selected_files, symbols, tuple(dict.fromkeys(references)), tuple(dict.fromkeys(ownership)), tuple(calls), imports)


def _symbols(source: PythonSourceFile) -> tuple[PythonSymbol, ...]:
    found: list[PythonSymbol] = []

    def collect(body: Iterable[ast.AST], prefix: str = "") -> None:
        for item in body:
            if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                name = prefix + item.name
                kind = "class" if isinstance(item, ast.ClassDef) else "function"
                found.append(PythonSymbol(source.path, name, kind, item.lineno, item.end_lineno or item.lineno, item))
                collect(item.body, name + ".")
            elif not prefix and isinstance(item, (ast.Assign, ast.AnnAssign)):
                targets = item.targets if isinstance(item, ast.Assign) else (item.target,)
                for target in targets:
                    for name in _assigned_names(target):
                        found.append(PythonSymbol(source.path, name, "global", item.lineno, item.end_lineno or item.lineno, item))
            else:
                # Control suites share their enclosing lexical scope. Only a
                # class or function definition changes the qualified prefix.
                collect(ast.iter_child_nodes(item), prefix)

    collect(source._tree.body if source._tree else [])
    return tuple(found)


def _assigned_names(target):
    return {item.id for item in ast.walk(target) if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)}


def _local_names(node):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    bindings = _function_scope_bindings(node)
    return bindings.names - bindings.global_names - bindings.nonlocal_names - bindings.import_names


def _scope_nodes(node):
    pending = [node]
    while pending:
        current = pending.pop()
        yield current
        if current is node or not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            pending.extend(reversed(tuple(ast.iter_child_nodes(current))))


def _reference_scope_nodes(node, path, aliases, locals_, *, definition_aliases, definition_locals):
    """Walk references with their lexical bindings, including unnamed lambdas."""
    def walk(current, visible_aliases, visible_locals):
        yield current, visible_aliases, visible_locals
        if isinstance(current, ast.Lambda):
            for expression in _function_definition_expressions(current):
                yield from walk(expression, visible_aliases, visible_locals)
            bindings = _function_scope_bindings(current)
            bound = bindings.names - bindings.global_names - bindings.nonlocal_names
            body_aliases = visible_aliases.copy()
            for name in bound:
                body_aliases[name] = (path, "<local>" + name)
            yield from walk(current.body, body_aliases, visible_locals | bound)
        elif isinstance(current, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for expression, bound in _comprehension_evaluation_steps(current):
                if bound is None:
                    yield from walk(expression, visible_aliases, visible_locals)
                else:
                    comprehension_aliases = visible_aliases.copy()
                    for name in bound:
                        comprehension_aliases[name] = (path, "<local>" + name)
                    yield from walk(expression, comprehension_aliases, visible_locals | bound)
        elif not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.iter_child_nodes(current):
                yield from walk(child, visible_aliases, visible_locals)

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        yield node, aliases, locals_
        for expression in _function_definition_expressions(node):
            yield from walk(expression, definition_aliases, definition_locals)
        for statement in node.body:
            yield from walk(statement, aliases, locals_)
    else:
        yield from walk(node, aliases, locals_)


def _source_imports(source: PythonSourceFile, modules: dict[str, str]) -> tuple[PythonSourceImport,...]:
    imports = []
    for item in ast.walk(source._tree) if source._tree else ():
        if isinstance(item, ast.Import):
            for alias in item.names:
                imports.append(PythonSourceImport(source.path,alias.name,alias.name,modules.get(alias.name,""),"",
                    alias.asname or alias.name,item.lineno,item.col_offset+1))
        elif isinstance(item, ast.ImportFrom):
            module = item.module or ""
            specifier = "."*item.level + module
            if item.level:
                parts = source.module.split(".")
                package = parts if source.path.endswith("/__init__.py") else parts[:-1]
                prefix = package[:len(package) - item.level + 1]
                module = ".".join((*prefix, module)) if module else ".".join(prefix)
            for alias in item.names:
                submodule = module + "." + alias.name if module else alias.name
                target = modules.get(submodule,modules.get(module,""))
                symbol = "" if submodule in modules else alias.name
                imports.append(PythonSourceImport(source.path,specifier,module,target,symbol,alias.asname or alias.name,
                    item.lineno,item.col_offset+1))
    return tuple(imports)


def _symbol_bindings(source, symbols, imports, by_id, members):
    """Resolve visible imports and simple source-proven callable/instance aliases."""
    scopes = [item for item in symbols if item.path == source.path and item.kind in {"class", "function"}]
    nodes = tuple(_scope_nodes(source._node))
    local_imports = {item.lineno for item in nodes if isinstance(item, (ast.Import, ast.ImportFrom))}
    visible = [item for item in imports if item.path == source.path and item.resolved_path and (
        item.line in local_imports or not any(scope.line <= item.line <= scope.end_line for scope in scopes))]
    module_aliases = {item.alias:(item.resolved_path,item.symbol) for item in visible if item.line not in local_imports}
    parents = [item for item in scopes if item.kind == "function" and source.name.startswith(item.name + ".")]
    if parents:
        parent = max(parents, key=lambda item: len(item.name))
        aliases = _symbol_bindings(parent, symbols, imports, by_id, members)
    else:
        aliases = module_aliases.copy()
    aliases.update({item.alias:(item.resolved_path,item.symbol) for item in visible if item.line in local_imports})
    if isinstance(source._node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for name in _function_scope_bindings(source._node).global_names:
            aliases.pop(name, None)
            if name in module_aliases:
                aliases[name] = module_aliases[name]
    for name in _local_names(source._node):
        if name not in {item.alias for item in visible if source.line <= item.line <= source.end_line}:
            aliases[name] = (source.path, "<local>" + name)
    for statement in nodes:
        if statement is not source._node and isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            declared = f"{source.path}:{source.name}.{statement.name}"
            if declared in by_id:
                aliases[statement.name] = (source.path, by_id[declared].name)
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)) or statement.value is None:
            continue
        target = _resolve_call(statement.value, source, aliases, by_id, members)
        if target is None or by_id[target].kind not in {"class", "function"}:
            continue
        value = by_id[target]
        for assigned in statement.targets if isinstance(statement, ast.Assign) else (statement.target,):
            if isinstance(assigned, ast.Name):
                aliases[assigned.id] = (value.path, value.name)
    return aliases


def _definition_scope_bindings(source, symbols, imports, by_id, members):
    parents = [item for item in symbols if item.path == source.path and item.kind in {"class", "function"}
               and source.name.startswith(item.name + ".")]
    if parents:
        parent = max(parents, key=lambda item: len(item.name))
        return _symbol_bindings(parent, symbols, imports, by_id, members), _local_names(parent._node)
    scopes = [item for item in symbols if item.path == source.path and item.kind in {"class", "function"}]
    aliases = {item.alias:(item.resolved_path,item.symbol) for item in imports
               if item.path == source.path and item.resolved_path
               and not any(scope.line <= item.line <= scope.end_line for scope in scopes)}
    return aliases, set()


def _resolve_call(expression: ast.AST, source: PythonSymbol, aliases: dict[str, tuple[str, str]], symbols: dict[str, PythonSymbol], members=None) -> str | None:
    if isinstance(expression, ast.Call):
        candidate = _resolve_call(expression.func, source, aliases, symbols, members)
        return candidate if candidate is not None and symbols[candidate].kind == "class" else None
    if isinstance(expression, ast.Name):
        name = expression.id
        if name in aliases:
            path, symbol = aliases[name]
            candidate = f"{path}:{symbol}"
        else:
            candidate = f"{source.path}:{name}"
    elif isinstance(expression, ast.Attribute):
        dotted = _qualified_name(expression)
        root = dotted.split(".",1)[0]
        if root in {"self", "cls"}:
            if not isinstance(expression.value, ast.Name):
                # self.resource.close is not the enclosing class's close.
                return None
            prefix = source.name.rpartition(".")[0]
            candidate = f"{source.path}:{prefix}.{expression.attr}"
        else:
            alias = next((name for name in sorted(aliases,key=len,reverse=True) if dotted.startswith(name+".")),None)
            if alias is not None:
                path, prefix = aliases[alias]
                suffix = dotted[len(alias)+1:]
                candidate = f"{path}:{prefix + '.' if prefix else ''}{suffix}"
            else:
                candidate = f"{source.path}:{dotted}"
        if candidate not in symbols and members is not None:
            receiver = _resolve_call(expression.value, source, aliases, symbols, members)
            member = members.get(receiver, {}).get(expression.attr)
            if member is not None:
                candidate = member.id
    else:
        return None
    return candidate if candidate in symbols else None


def _qualified_name(expression):
    if isinstance(expression,ast.Name):
        return expression.id
    if isinstance(expression,ast.Attribute):
        prefix = _qualified_name(expression.value)
        return prefix+"."+expression.attr if prefix else ""
    return ""


__all__ = ["PythonSourceContext", "PythonSourceFile", "PythonSourceNode", "PythonSymbol", "PythonSourceReference", "PythonSourceImport", "PythonSourceOwnership", "PythonSourceCall", "build_python_source_context"]
