"""Operation-owned Python imports, shared by declarations and implementations."""
from __future__ import annotations

import builtins
import importlib
import importlib.abc
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
from threading import RLock
from uuid import uuid4


def source_namespace(directory, *, namespaces=None, source_roots=()):
    namespaces = {} if namespaces is None else namespaces
    directory = Path(directory).resolve()
    if directory not in namespaces:
        SourceNamespace(directory, namespaces=namespaces, source_roots=source_roots)
    return namespaces[directory]


class SourceNamespace:
    """An owner's normal package tree, without global project-name aliases."""
    def __init__(self, directory, *, namespaces=None, source_roots=()):
        self.directory = Path(directory).resolve()
        self.namespaces = {} if namespaces is None else namespaces
        self.namespaces[self.directory] = self
        self.roots = tuple(dict.fromkeys((self.directory, *(Path(root).resolve() for root in source_roots))))
        self.name = "_vibeflow_sources_" + uuid4().hex
        self._load_lock = RLock()
        spec = _package_spec(self.name, self.directory)
        package = importlib.util.module_from_spec(spec)
        package.__vibeflow_source_namespace__ = self
        sys.modules[self.name] = package

    def load(self, path):
        path = Path(path).resolve()
        parts = path.relative_to(self.directory).with_suffix("").parts
        if parts[-1] == "__init__":
            parts = parts[:-1]
        with self._load_lock:
            return importlib.import_module(".".join((self.name, *parts)))

    def _import(self, name, globals=None, locals=None, fromlist=(), level=0):
        if not level:
            parts = name.split(".")
            for root in self.roots:
                path = root.joinpath(*parts)
                if not path.is_dir() and not path.with_suffix(".py").is_file():
                    continue
                owner = source_namespace(root, namespaces=self.namespaces, source_roots=tuple(candidate for candidate in self.roots if root.is_relative_to(candidate)))
                qualified = owner.name + "." + name
                module = builtins.__import__(qualified, globals, locals, fromlist or ("__doc__",), 0)
                return module if fromlist else sys.modules[owner.name + "." + parts[0]]
        return builtins.__import__(name, globals, locals, fromlist, level)


class _SourceLoader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname, namespace, path):
        super().__init__(fullname, str(path))
        self.namespace, self.source_path = namespace, path

    def exec_module(self, module):
        module.__dict__["__builtins__"] = {**vars(builtins), "__import__": self.namespace._import}
        exec(compile(self.source_path.read_text(encoding="utf-8"), self.path, "exec"), module.__dict__)


class _PackageLoader(importlib.machinery.SourceFileLoader):
    """A directory package with a standard resource reader and no initializer."""
    def exec_module(self, module):
        pass


def _package_spec(name, directory):
    loader = _PackageLoader(name, str(directory / "__init__.py"))
    spec = importlib.machinery.ModuleSpec(name, loader, is_package=True)
    spec.submodule_search_locations = [str(directory)]
    return spec


class _SourceFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        prefix, _, relative = fullname.partition(".")
        module = sys.modules.get(prefix)
        namespace = vars(module).get("__vibeflow_source_namespace__") if module is not None else None
        if namespace is None or not relative:
            return None
        directory = namespace.directory.joinpath(*relative.split("."))
        source = directory / "__init__.py" if directory.is_dir() else directory.with_suffix(".py")
        if source.is_file():
            return importlib.util.spec_from_file_location(fullname, source,
                loader=_SourceLoader(fullname, namespace, source),
                submodule_search_locations=[str(directory)] if directory.is_dir() else None)
        if directory.is_dir():
            return _package_spec(fullname, directory)
        return None


_FINDER = _SourceFinder()
sys.meta_path.insert(0, _FINDER)
