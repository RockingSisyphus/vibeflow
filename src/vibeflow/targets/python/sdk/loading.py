"""Target-owned loading of trusted, fixed plugin objects."""

from contextlib import contextmanager
import importlib
import importlib.util
from pathlib import Path
import sys

from vibeflow.targets.python.sdk.plugin import Plugin


@contextmanager
def source_paths(paths):
    additions = [str(Path(path).resolve()) for path in dict.fromkeys(paths) if str(Path(path).resolve()) not in sys.path]
    sys.path[:0] = additions
    try:
        yield
    finally:
        for item in additions:
            sys.path.remove(item)


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
    """A prior project must not satisfy a same-named local import."""
    for name, module in tuple(sys.modules.items()):
        filename = getattr(module, "__file__", None)
        if name.startswith("vibeflow."):
            continue
        relative = Path(*name.split("."))
        if not filename:
            expected = next((Path(root)/relative for root in roots if (Path(root)/relative).is_dir()),None)
            namespace = getattr(module,"__path__",None)
            if expected is not None and namespace is not None and str(expected.resolve()) not in namespace:
                sys.modules.pop(name,None)
            continue
        candidates = (candidate for root in roots
                      for candidate in (Path(root) / relative.with_suffix(".py"), Path(root) / relative / "__init__.py"))
        expected = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
        if expected is not None and Path(filename).resolve() != expected:
            sys.modules.pop(name, None)
