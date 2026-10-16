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
        module.__package__ = package
    sys.modules[name] = module
    try:
        specification.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(name, None)
        raise
    return module


def load_plugin(source, *, root, source_roots=()):
    """Entry modules are trusted bootstrap code, not preflighted Node code."""
    with source_paths((root, *source_roots)):
        _discard_foreign_project_modules((root, *source_roots))
        if source.kind in {"module", "package"}:
            module = importlib.import_module(source.ref)
        elif source.kind == "file":
            path = (Path(root) / source.ref).resolve()
            owner = next((Path(value).resolve() for value in (root,*source_roots)
                          if path.is_relative_to(Path(value).resolve())), path.parent)
            parts = path.parent.relative_to(owner).parts
            package = ".".join(parts) if all(part.isidentifier() for part in parts) else ""
            name = package if path.name == "__init__.py" and package else f"_vibeflow_plugin_{abs(hash(str(path)))}"
            spec = importlib.util.spec_from_file_location(name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot load plugin entry: {path}")
            module = importlib.util.module_from_spec(spec)
            if package:
                if path.name != "__init__.py":importlib.import_module(package)
                module.__package__ = package
            sys.modules[name] = module
            try:
                # Read current source for this command; Python's coarse .pyc
                # timestamps must not select a previous fixed definition.
                exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), module.__dict__)
            except BaseException:
                sys.modules.pop(name, None)
                raise
        else:
            raise ValueError("plugin source must be a file, module or package")
        value = getattr(module, source.export or "plugin")
        if not isinstance(value, Plugin):
            raise ValueError("plugin export must be a fixed SDK Plugin object; declaration factories are not supported")
        return value


def _discard_foreign_project_modules(roots):
    """A selected project's imports must not reuse another project's modules."""
    replaced = set()
    for name, module in tuple(sys.modules.items()):
        if name == "vibeflow" or name.startswith("vibeflow."):
            continue
        relative = Path(*name.split("."))
        expected_file, namespace_roots = None, set()
        for root in roots:
            directory = Path(root) / relative
            candidates = (directory / "__init__.py", directory.with_suffix(".py"))
            expected_file = next((item.resolve() for item in candidates if item.is_file()), None)
            if expected_file is not None:
                break
            if directory.is_dir():
                namespace_roots.add(str(directory.resolve()))
        filename = getattr(module, "__file__", None)
        if expected_file is not None:
            if not filename or Path(filename).resolve() != expected_file:
                replaced.add(name)
        elif namespace_roots:
            actual = {str(Path(value).resolve()) for value in getattr(module, "__path__", ())}
            if filename or not namespace_roots.issubset(actual):
                replaced.add(name)
    for name in tuple(sys.modules):
        if name in replaced or any(name.startswith(parent + ".") for parent in replaced):
            sys.modules.pop(name, None)
