"""Project-owned source loading for Python quality preflight."""

from __future__ import annotations

import ast
from pathlib import Path

from vibeflow.targets.python.quality.source_analysis.preflight import (
    PythonSourceFact,
    preflight_python_source_facts,
)


def preflight_python_import_tree(
    entry_path: Path,
    *,
    project_root: Path | None = None,
    source_roots: tuple[Path, ...] = (),
) -> None:
    """Load a local import graph, then pass plain source facts to quality."""

    path = entry_path.resolve()
    root = (project_root or path.parent).resolve()
    facts = collect_python_source_facts(
        path,
        project_root=root,
        source_roots=source_roots,
    )
    preflight_python_source_facts(str(path), facts)


def collect_python_source_facts(
    entry_path: Path,
    *,
    project_root: Path | None = None,
    source_roots: tuple[Path, ...] = (),
) -> tuple[PythonSourceFact, ...]:
    """Read and resolve the project-local sources reachable from ``entry_path``."""

    path = entry_path.resolve()
    root = (project_root or path.parent).resolve()
    roots = tuple(
        dict.fromkeys(
            candidate.resolve()
            for candidate in (root, *source_roots)
        )
    )
    facts: dict[str, PythonSourceFact] = {}
    _collect_source_fact(path, source_roots=roots, facts=facts)
    return tuple(facts[source_id] for source_id in sorted(facts))


def resolve_local_module_path(
    module_ref: str,
    *,
    project_root: Path,
) -> Path | None:
    """Resolve a dotted module reference when it belongs to ``project_root``."""

    parts = tuple(module_ref.split("."))
    paths = _paths_for_module_parts(project_root.resolve(), parts)
    return paths[-1] if paths else None


def _collect_source_fact(
    path: Path,
    *,
    source_roots: tuple[Path, ...],
    facts: dict[str, PythonSourceFact],
) -> None:
    resolved = path.resolve()
    source_id = str(resolved)
    if source_id in facts:
        return
    project_root = _owning_source_root(resolved, source_roots)
    if project_root is None:
        return
    try:
        source = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        facts[source_id] = PythonSourceFact(
            source_id=source_id,
            path=source_id,
            source="",
            module_name=_module_name(resolved, project_root),
            load_error=str(exc),
        )
        return

    try:
        tree = ast.parse(source, filename=source_id)
    except SyntaxError:
        facts[source_id] = PythonSourceFact(
            source_id=source_id,
            path=source_id,
            source=source,
            module_name=_module_name(resolved, project_root),
            is_base_lib=_is_base_lib_source(resolved),
        )
        return

    import_time_nodes = _import_time_import_nodes(tree)
    import_time_node_ids = {id(node) for node in import_time_nodes}
    runtime_nodes = tuple(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and id(node) not in import_time_node_ids
    )
    import_time_paths = _resolve_import_nodes(
        import_time_nodes,
        current_path=resolved,
        source_roots=source_roots,
    )
    runtime_paths = tuple(
        child
        for child in _resolve_import_nodes(
            runtime_nodes,
            current_path=resolved,
            source_roots=source_roots,
        )
        if not _is_base_lib_source(child)
    )
    facts[source_id] = PythonSourceFact(
        source_id=source_id,
        path=source_id,
        source=source,
        module_name=_module_name(resolved, project_root),
        import_time_dependencies=tuple(str(child) for child in import_time_paths),
        runtime_dependencies=tuple(str(child) for child in runtime_paths),
        is_base_lib=_is_base_lib_source(resolved),
    )
    for child in (*import_time_paths, *runtime_paths):
        _collect_source_fact(child, source_roots=source_roots, facts=facts)


def _resolve_import_nodes(
    nodes: tuple[ast.Import | ast.ImportFrom, ...],
    *,
    current_path: Path,
    source_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for node in nodes:
        paths.extend(
            _resolve_local_imports(
                node,
                current_path=current_path,
                source_roots=source_roots,
            )
        )
    return tuple(dict.fromkeys(paths))


def _resolve_local_imports(
    node: ast.Import | ast.ImportFrom,
    *,
    current_path: Path,
    source_roots: tuple[Path, ...],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    project_root = _owning_source_root(current_path, source_roots)
    if project_root is None:
        return ()
    if isinstance(node, ast.Import):
        for alias in node.names:
            for source_root in source_roots:
                paths.extend(
                    _paths_for_module_parts(
                        source_root,
                        tuple(alias.name.split(".")),
                    )
                )
        return tuple(dict.fromkeys(paths))

    module_parts = tuple((node.module or "").split(".")) if node.module else ()
    if node.level:
        base = current_path.parent
        for _ in range(max(0, node.level - 1)):
            base = base.parent
        paths.extend(_paths_for_relative_base(base, module_parts))
        for alias in node.names:
            if alias.name != "*":
                paths.extend(
                    _paths_for_relative_base(
                        base,
                        (*module_parts, *alias.name.split(".")),
                    )
                )
    else:
        for source_root in source_roots:
            paths.extend(_paths_for_module_parts(source_root, module_parts))
            for alias in node.names:
                if alias.name != "*":
                    paths.extend(
                        _paths_for_module_parts(
                            source_root,
                            (*module_parts, *alias.name.split(".")),
                        )
                    )
    return tuple(
        dict.fromkeys(
            path
            for path in paths
            if any(_is_within(path, source_root) for source_root in source_roots)
        )
    )


def _paths_for_module_parts(root: Path, parts: tuple[str, ...]) -> tuple[Path, ...]:
    return _paths_for_relative_base(root, parts)


def _paths_for_relative_base(base: Path, parts: tuple[str, ...]) -> tuple[Path, ...]:
    if not parts or any(not part or part in {".", ".."} for part in parts):
        return ()
    paths: list[Path] = []
    for index in range(1, len(parts) + 1):
        candidate = base.joinpath(*parts[:index])
        package = candidate / "__init__.py"
        module = candidate.with_suffix(".py")
        if package.is_file():
            paths.append(package.resolve())
        if index == len(parts) and module.is_file():
            paths.append(module.resolve())
    return tuple(paths)


def _import_time_import_nodes(
    tree: ast.Module,
) -> tuple[ast.Import | ast.ImportFrom, ...]:
    collector = _ImportTimeImportCollector()
    collector.visit(tree)
    return tuple(collector.nodes)


class _ImportTimeImportCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.nodes: list[ast.Import | ast.ImportFrom] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.nodes.append(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.nodes.append(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return


def _is_base_lib_source(path: Path) -> bool:
    return "base_lib" in path.parts


def _owning_source_root(
    path: Path,
    source_roots: tuple[Path, ...],
) -> Path | None:
    matches = tuple(
        root
        for root in source_roots
        if _is_within(path, root)
    )
    if not matches:
        return None
    return max(matches, key=lambda root: len(root.parts))


def _module_name(path: Path, project_root: Path) -> str:
    try:
        relative = path.resolve().relative_to(project_root.resolve())
    except ValueError:
        return ""
    parts = list(relative.parts)
    if not parts or parts[-1].startswith("."):
        return ""
    if parts[-1] == "__init__.py":
        parts.pop()
    elif parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(part for part in parts if part)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


__all__ = [
    "collect_python_source_facts",
    "preflight_python_import_tree",
    "resolve_local_module_path",
]
