"""Resolve SDK source assertions to the actual, already loaded Python object."""

from dataclasses import replace
from importlib.machinery import PathFinder
import inspect
from pathlib import Path
import sys

from vibeflow.core.descriptors.contributions import resource_kind
from vibeflow.core.descriptors.models import ResourceImplementationConflict, SourceLocator


def _source_path(source, root, roots):
    if source.kind == "file":
        return (root / source.ref).resolve()
    if source.kind not in {"module", "package"}:
        raise ValueError(f"Python source kind '{source.kind}' cannot identify a direct implementation")
    parts = source.ref.split(".")
    for directory in (root, *roots):
        module = Path(directory).joinpath(*parts)
        for candidate in (module.with_suffix(".py"), module / "__init__.py"):
            if candidate.is_file():
                return candidate.resolve()
    loaded = sys.modules.get(source.ref)
    if loaded is not None and getattr(loaded, "__file__", None):
        return Path(loaded.__file__).resolve()
    # PathFinder inspects package paths without executing package initializers.
    paths = sys.path
    spec = None
    for index in range(len(parts)):
        spec = PathFinder.find_spec(".".join(parts[:index + 1]), paths)
        if spec is None:
            break
        paths = spec.submodule_search_locations
        if index < len(parts) - 1 and paths is None:
            spec = None
            break
    if spec is None or not spec.origin or spec.origin in {"built-in", "frozen"}:
        raise ValueError(f"cannot resolve declared Python module '{source.ref}'")
    return Path(spec.origin).resolve()


def _loaded_export(path, symbol, *, module_name=""):
    modules = tuple(sys.modules.values())
    preferred = sys.modules.get(module_name)
    if preferred is not None:
        modules = (preferred, *(module for module in modules if module is not preferred))
    from vibeflow.targets.python.sdk.resources import ResourceDefinition
    for module in modules:
        filename = getattr(module, "__file__", None)
        if not isinstance(filename, str) or Path(filename).resolve() != path:
            continue
        value = module
        try:
            for part in symbol.split("."):
                value = inspect.getattr_static(value, part)
        except AttributeError:
            continue
        if isinstance(value, (staticmethod, classmethod)):
            value = value.__func__
        return value.implementation if isinstance(value, ResourceDefinition) else value
    return None


def normalize_resource(entry, value, *, root, source_roots=()):
    """Validate one loaded implementation for either ownership category."""
    if value is None:
        return entry
    descriptor = entry.descriptor
    filename = inspect.getsourcefile(value)
    symbol = getattr(value, "__qualname__", "")
    implementations = list(getattr(descriptor, "implementations", ()))
    compatible = [index for index, item in enumerate(implementations) if item.language == "python"]
    field = f"{resource_kind(descriptor)}.{descriptor.id}.implementations"
    if not filename or not symbol or len(compatible) != 1:
        raise ResourceImplementationConflict("a direct Python implementation requires one Python source", field_name=field)
    index = compatible[0]
    actual_path = Path(filename).resolve()
    source = implementations[index].source
    try:
        declared_path = _source_path(source, Path(root), source_roots)
        same_position = declared_path == actual_path and (source.export is None or source.export == symbol)
        exported = _loaded_export(declared_path, source.export, module_name=getattr(value, "__module__", "")) if not same_position and source.export else None
        same_object = exported is value or (inspect.ismethod(value) and exported is value.__func__)
    except ValueError as error:
        same_object = same_position = False
        resolution_error = str(error)
    else:
        resolution_error = ""
    if not (same_object or same_position):
        error = ResourceImplementationConflict(
            f"declared source for '{descriptor.id}' does not identify its direct Python implementation", field_name=field + f"[{index}].source")
        error.location.update(path=entry.origin.path, **({"line":entry.origin.line} if entry.origin.line else {}))
        error.details = {"declared":source.to_dict(), "actual":{"path":str(actual_path),"symbol":symbol},
                         **({"resolution_error":resolution_error} if resolution_error else {})}
        raise error
    canonical = SourceLocator("file", str(actual_path), symbol)
    if source != canonical:
        implementations[index] = replace(implementations[index], source=canonical)
        descriptor = replace(descriptor, implementations=tuple(implementations))
        entry = replace(entry, descriptor=descriptor)

    return entry


def normalize_contributions(contribution, bindings, *, root, source_roots=()):
    resources = tuple(normalize_resource(entry, bindings.get((resource_kind(entry.descriptor), entry.descriptor.id)),
        root=root, source_roots=source_roots) for entry in contribution.resources)
    return replace(contribution, resources=resources) if resources != contribution.resources else contribution
