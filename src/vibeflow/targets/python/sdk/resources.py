"""Python declarations. Attaching a definition never registers a resource."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.models import SourceLocator, DescriptorModelError
from vibeflow.core.rules.models import RuleCall, RuleRelation, RulesetDescriptor
from vibeflow.core.descriptors.declarations import ResourceDefinition


def definition(value: Any) -> ResourceDefinition:
    if isinstance(value, ResourceDefinition):
        return value
    result = getattr(value, "__vibeflow_resource__", None)
    if not isinstance(result, ResourceDefinition):
        raise ValueError("plugin resources must be declared with the VibeFlow SDK")
    return result


def _location(value=None):
    if value is not None:
        try:
            path = inspect.getsourcefile(value) or ""
            line = inspect.getsourcelines(value)[1]
        except (OSError, TypeError):
            path = ""
            line = None
        return path, line, value.__qualname__
    frame = inspect.currentframe()
    while frame is not None:
        if not frame.f_globals.get("__name__", "").startswith((__package__, "vibeflow.targets.python.sdk.nodes")):
            return frame.f_code.co_filename, frame.f_lineno, ""
        frame = frame.f_back
    return "", None, ""


def _json(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


def _declare(kind, options, value=None, source=None):
    path, line, symbol = _location(value)
    data = {"kind": kind, **_json(options)}
    declaration_path, declaration_line, _ = _location()
    file_values = data.pop("implementation_files", ())
    try:
        files = _implementation_files(file_values, declaration_path)
    except ValueError as error:
        error.location = {"path":declaration_path, "field":"implementation_files",
                          **({"line":declaration_line} if declaration_line is not None else {})}
        raise
    if kind in {"node", "rule", "base_lib",  "plugin"} and not (kind == "rule" and options.get("handler") and value is None and source is None):
        locator = _json(source) if source is not None else {"kind": "file", "ref": path, "export": symbol}
        implementation = {"language": "python", "source": locator}
        if kind == "plugin":
            implementation["completion"] = data.pop("completion", "immediate")
        if kind == "node" and value is not None:
            implementation["completion"] = "suspend" if inspect.iscoroutinefunction(getattr(value, "run_pure", None)) else "immediate"
        if kind != "rule":
            implementation["targets"] = ["python"]
            if files:
                implementation["implementation_files"] = [item.to_dict() for item in files]
        data.setdefault("implementations", [implementation])
        if kind != "rule" and options.get("implementations") and isinstance(data["implementations"], (list, tuple)):
            for item in data["implementations"]:
                if isinstance(item, dict):
                    parts = _implementation_files(item.get("implementation_files", ()), declaration_path)
                    item["implementation_files"] = [part.to_dict() for part in (*parts, *files)]
    try:
        descriptor = decode_resource(data)
    except ValueError as error:
        error.location = {**getattr(error, "location", {}), "path":path, **({"line":line} if line is not None else {})}
        raise
    return ResourceDefinition(descriptor, value, declaration_path, declaration_line, symbol)


def _implementation_files(values, declaration_path):
    if isinstance(values, str) or not isinstance(values, (tuple, list)):
        raise DescriptorModelError("implementation_files must be a list of explicit file paths")
    result = []
    for value in values:
        if not isinstance(value,(SourceLocator,str,Mapping)):
            raise DescriptorModelError("implementation_files accepts file paths or source locators")
        locator = value if isinstance(value, SourceLocator) else SourceLocator("file", value) if isinstance(value, str) else SourceLocator(**value)
        if locator.kind != "file":
            raise DescriptorModelError("implementation_files accepts only file sources")
        ref = Path(declaration_path).parent / locator.ref
        result.append(SourceLocator("file", str(ref.resolve()), locator.export))
    # Apply the same pure validation as other Target declarations.
    from vibeflow.core.descriptors.models import ImplementationDescriptor
    return ImplementationDescriptor("python", ("python",), SourceLocator("file", declaration_path or "."), implementation_files=tuple(result)).implementation_files


def _decorator(kind, options, source=None):
    if source is not None:
        return _declare(kind, options, source=source)
    def attach(value):
        result = _declare(kind, options, value)
        value.__vibeflow_resource__ = result
        return value
    return attach


def rule(*, id: str, source=None, **options):
    """Declare an ordinary check(context, inputs, params) function."""
    if options.get("handler") and source is None and not options.get("implementations"):
        return _declare("rule", {"id": id, **options})
    return _decorator("rule", {"id": id, **options}, source)


def ruleset(*, id: str, calls=(), relations=(), entrypoints=None, **options):
    """Use the same RuleCall/RuleRelation graph model as Core."""
    return _declare("ruleset", {"id": id, "calls": calls, "relations": relations,
                               "entrypoints": entrypoints or {}, **options})


def data_schema(*, type_key: str, schema, **options):
    return _declare("data_schema", {"type_key": type_key, "schema": schema, **options})


def capability(*, id: str, **options):
    return _declare("capability", {"id": id, **options})


def node_type(*, id: str, **options):
    """Declare an implementation-free NodeType shell owned by a Plugin."""
    return _declare("node_type", {"id": id, **options})


def base_lib(*, id: str, source=None, **options):
    return _decorator("base_lib", {"id": id, "display_name": id, "description": id, **options}, source)


def lifecycle(*, id: str, type: str, source=None, **options):
    """Declare a compiler/runtime factory with its own rules and source bundle."""
    return _decorator("plugin", {"id": id, "type": type, "targets": ["python"], **options}, source)





__all__ = ["ResourceDefinition", "rule", "ruleset", "data_schema", "capability", "node_type",
           "base_lib", "lifecycle",  "RuleCall", "RuleRelation", "SourceLocator", "RulesetDescriptor"]
