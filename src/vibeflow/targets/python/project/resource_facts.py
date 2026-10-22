"""Python source attribution for resource Rules; no permission decisions."""
import ast
from pathlib import Path

from vibeflow.targets.python.quality.parse_cache import parse_python_source
from vibeflow.targets.python.project.source_closure import _resolve_local_imports
from vibeflow.targets.python.project.structure_sources import python_import_scopes


def resource_import_facts(workspace, root, prepared, owners, *, syntax_cache, node_command):
    paths = {item["path"] for item in owners}
    paths.update(path for package in prepared.packages for path in package["source_paths"])
    edges = []
    for value in sorted(paths):
        path = Path(value)
        if path.suffix != ".py" or not path.is_file() or not path.is_relative_to(workspace.root):
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = parse_python_source(path, text, syntax_cache)
        except SyntaxError:
            continue
        for statement in ast.walk(tree):
            if not isinstance(statement, (ast.Import, ast.ImportFrom)):
                continue
            for target in _resolve_local_imports(statement, current_path=path, source_roots=(root.path, workspace.root)):
                edges.append({"path": str(path), "target": str(target), "line": statement.lineno, "column": statement.col_offset + 1,
                    "symbols": tuple(alias.name for alias in statement.names),
                    "empty_package": target.name == "__init__.py" and not any(not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))
                        for node in parse_python_source(target, target.read_text(encoding="utf-8"), syntax_cache).body)})
    scopes = python_import_scopes(({"owners": owners},), root.path, syntax_cache)
    return {"owners": tuple(scopes[0]["owners"]), "imports": tuple(edges)}
