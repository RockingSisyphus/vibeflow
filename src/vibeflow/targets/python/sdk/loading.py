"""Target-owned loading of trusted, fixed plugin objects."""

from contextlib import contextmanager
import importlib
import importlib.util
from pathlib import Path
import sys
from threading import RLock

from vibeflow.targets.python.sdk.plugin import Plugin

_PATH_LOCK = RLock()
_PATH_USERS = {}


@contextmanager
def source_paths(paths):
    roots = tuple(dict.fromkeys(str(Path(path).resolve()) for path in paths))
    with _PATH_LOCK:
        additions = []
        for root in roots:
            users, inserted = _PATH_USERS.get(root, (0, root not in sys.path))
            _PATH_USERS[root] = users + 1, inserted
            if not users and inserted:
                additions.append(root)
        sys.path[:0] = additions
    try:
        yield
    finally:
        with _PATH_LOCK:
            for root in roots:
                users, inserted = _PATH_USERS[root]
                if users > 1:
                    _PATH_USERS[root] = users - 1, inserted
                else:
                    del _PATH_USERS[root]
                    if inserted and root in sys.path:
                        sys.path.remove(root)


def load_source_module(path, name, *, package=None):
    """Load one native implementation, reusing only the same physical source."""
    path = Path(path).resolve()
    existing = sys.modules.get(name)
    filename = getattr(existing, "__file__", None)
    if filename is not None and Path(filename).resolve() == path:
        return existing
    if package:
        importlib.import_module(package)
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise ImportError(f"cannot load Python implementation: {path}")
    module = importlib.util.module_from_spec(specification)
    if package:
        module.__package__ = name if path.name == "__init__.py" else package
    sys.modules[name] = module
    try:
        exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def load_plugin(source, *, root, source_roots=(), namespaces=None):
    """Entry modules are trusted bootstrap code, not preflighted Node code."""
    with source_paths((root, *source_roots)):
        if source.kind in {"module", "package"}:
            module = importlib.import_module(source.ref)
        elif source.kind == "file":
            path = (Path(root) / source.ref).resolve()
            owner = next((Path(value).resolve() for value in (root,*source_roots)
                          if path.is_relative_to(Path(value).resolve())), path.parent)
            from vibeflow.targets.python.sdk.source_namespace import source_namespace
            module = source_namespace(owner, namespaces=namespaces, source_roots=source_roots).load(path)
        else:
            raise ValueError("plugin source must be a file, module or package")
        value = getattr(module, source.export or "plugin")
        if not isinstance(value, Plugin):
            raise ValueError("plugin export must be a fixed SDK Plugin object; declaration factories are not supported")
        return value
