"""Discover SDK declarations without importing ordinary implementation-only files."""
import ast
from pathlib import Path

from vibeflow.targets.python.sdk.loading import source_paths
from vibeflow.targets.python.sdk.source_namespace import source_namespace
from vibeflow.targets.python.sdk.resources import ResourceDefinition


_RESOURCE_CONSTRUCTORS = frozenset({"node", "node_type", "rule", "ruleset", "base_lib",
                                   "data_schema", "capability", "ResourceDefinition"})


def declares_resources(path, *, syntax_cache=None):
    """Resource constructors are SDK imports; a plain helper is never bootstrap."""
    from vibeflow.targets.python.quality.parse_cache import parse_python_source
    tree = parse_python_source(path, path.read_text(encoding="utf-8"), syntax_cache)
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom) and (statement.module or "").startswith("vibeflow.targets.python.sdk"):
            if any(alias.name in _RESOURCE_CONSTRUCTORS or alias.name == "*" for alias in statement.names):
                return True
        if isinstance(statement, ast.Import) and any(alias.name.startswith("vibeflow.targets.python.sdk") for alias in statement.names):
            return True
        if isinstance(statement, ast.ImportFrom) and statement.module == "vibeflow.targets.python" and any(alias.name == "sdk" for alias in statement.names):
            return True
    return False


def discover_resources(directory, *, source_roots=(), syntax_cache=None, namespaces=None):
    directory = Path(directory).resolve()
    return _discover(directory, source_namespace(directory, namespaces=namespaces, source_roots=source_roots), source_roots, syntax_cache)


def discover_file_resources(path, namespace, *, syntax_cache=None):
    """Read one declaration file in its existing operation-owned namespace."""
    if not declares_resources(path, syntax_cache=syntax_cache):
        return ()
    try:
        module = namespace.load(path)
    except (ValueError, TypeError) as error:
        if not getattr(error, "location", None):
            import traceback
            frames = [frame for frame in traceback.extract_tb(error.__traceback__)
                      if Path(frame.filename).resolve() == path]
            error.location = {"path": str(path), **({"line":frames[-1].lineno} if frames else {})}
        raise
    seen, found = set(), []
    for value in vars(module).values():
        resource = value if isinstance(value, ResourceDefinition) else getattr(value, "__vibeflow_resource__", None)
        if not isinstance(resource, ResourceDefinition) or id(resource) in seen:
            continue
        seen.add(id(resource))
        if Path(resource.path).resolve() == path:
            found.append(resource)
    return tuple(found)


def _discover(directory, namespace, source_roots, syntax_cache):
    found = []
    with source_paths(source_roots):
        for group, kind in (("nodes", "node"), ("base_lib", "base_lib")):
            for path in sorted((directory / group).rglob("*.py")):
                for resource in discover_file_resources(path, namespace, syntax_cache=syntax_cache):
                    found.append(resource)
    import sys
    from vibeflow.core.descriptors.declarations import ResourceDiscovery
    loaded = {str(Path(filename).resolve()): "loaded" for name, module in tuple(sys.modules.items())
              if name.startswith(namespace.name + ".") and isinstance(filename := getattr(module, "__file__", None), str)
              and Path(filename).resolve().is_relative_to(directory)}
    return ResourceDiscovery(tuple(found), loaded)
