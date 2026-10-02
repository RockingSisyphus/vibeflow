"""Python syntax and symbol ownership for an explicitly selected source scope."""

from __future__ import annotations

import ast
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Iterable, Mapping

from vibeflow.core.descriptors.models import NodeDescriptor


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


def build_python_source_context(nodes: Iterable[PythonSourceNode], files: Iterable[PythonSourceFile], *, calls: Iterable[PythonSourceCall] = ()) -> PythonSourceContext:
    selected_nodes = tuple(sorted(nodes, key=lambda item: (item.type_key, item.path, item.symbol)))
    selected_files = tuple(sorted(files, key=lambda item: item.path))
    symbols = tuple(symbol for source in selected_files if source._tree for symbol in _symbols(source))
    by_id = {symbol.id: symbol for symbol in symbols}
    by_module = {source.module: source.path for source in selected_files}
    imports = tuple(item for source in selected_files for item in _source_imports(source,by_module))
    references: list[PythonSourceReference] = []
    for source in selected_files:
        aliases = {item.alias:(item.resolved_path,item.symbol) for item in imports if item.path == source.path and item.resolved_path}
        for symbol in (item for item in symbols if item.path == source.path):
            if symbol.kind == "class":
                continue
            locals_ = _local_names(symbol._node)
            for expression in ast.walk(symbol._node):
                if isinstance(expression, ast.Call):
                    target = _resolve_call(expression.func, symbol, aliases, by_id)
                    if target is not None:
                        references.append(PythonSourceReference(symbol.id, target, "call", expression.lineno,expression.col_offset+1))
                elif isinstance(expression, ast.Name) and expression.id not in locals_:
                    target = _resolve_call(expression, symbol, aliases, by_id)
                    if target is not None and by_id[target].kind == "global":
                        references.append(PythonSourceReference(symbol.id, target, "global_reference", expression.lineno))
    adjacency: dict[str, set[str]] = {}
    for reference in references:
        adjacency.setdefault(reference.source, set()).add(reference.target)
    ownership: list[PythonSourceOwnership] = []
    for node in selected_nodes:
        root_id = f"{node.path}:{node.symbol}"
        if root_id not in by_id:
            continue
        ownership.append(PythonSourceOwnership(node.type_key, root_id, "implementation"))
        seeds = [symbol.id for symbol in symbols if symbol.path == node.path and symbol.name.startswith(node.symbol + ".")]
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

    def collect(body: list[ast.stmt], prefix: str = "") -> None:
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

    collect(source._tree.body if source._tree else [])
    return tuple(found)


def _assigned_names(target):
    return {item.id for item in ast.walk(target) if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store)}


def _local_names(node):
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return set()
    names = {item.arg for item in (*node.args.posonlyargs,*node.args.args,*node.args.kwonlyargs)}
    globals_ = set()
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and isinstance(item.ctx, ast.Store):
            names.add(item.id)
        if isinstance(item, ast.Global):
            globals_.update(item.names)
    return names - globals_


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


def _resolve_call(expression: ast.AST, source: PythonSymbol, aliases: dict[str, tuple[str, str]], symbols: dict[str, PythonSymbol]) -> str | None:
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
