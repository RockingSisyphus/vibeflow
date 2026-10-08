"""Project structure consumes symbol imports from the same cached syntax facts."""

import ast
from pathlib import Path

from vibeflow.targets.python.quality.parse_cache import parse_python_source
from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context


def python_import_scopes(scopes, root, parse_cache):
    paths = {owner["path"] for scope in scopes for owner in scope["owners"]}
    files = []
    for relative in sorted(paths):
        path = Path(root) / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = parse_python_source(path, text, parse_cache)
        except SyntaxError:
            continue  # The ordinary parser reports the actual syntax diagnostic.
        files.append(PythonSourceFile(str(path), relative.removesuffix(".py").replace("/", "."), text, _tree=tree))
    context = build_python_source_context((), files)
    return tuple({**scope, "owners": [_owner_imports(owner, root, context) for owner in scope["owners"]]}
                 for scope in scopes)


def _owner_imports(owner, root, context):
    if owner["role"] != "entry" or not owner["symbol"]:
        return owner
    path = str(Path(root) / owner["path"])
    if not any(source.path == path for source in context.files):
        return owner
    tree = context._analysis._implementation_tree(context, path, owner["symbol"])
    if tree is None:
        return owner
    return {**owner, "import_lines": [item.lineno for item in ast.walk(tree)
            if isinstance(item, (ast.Import, ast.ImportFrom))]}
