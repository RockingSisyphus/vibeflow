"""Python declarations. Attaching a definition never registers a resource."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any, Mapping

from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.models import SourceLocator
from vibeflow.core.rules.models import RuleCall, RuleRelation, RulesetDescriptor


@dataclass(frozen=True)
class ResourceDefinition:
    descriptor: Any
    implementation: Any = None
    path: str = ""
    line: int | None = None
    symbol: str = ""


def definition(value: Any) -> ResourceDefinition:
    if isinstance(value, ResourceDefinition):
        return value
    result = getattr(value, "__vibeflow_resource__", None)
    if not isinstance(result, ResourceDefinition):
        raise ValueError("plugin resources must be declared with the VibeFlow SDK")
    return result


def _location(value=None):
    if value is not None:
        path = inspect.getsourcefile(value) or ""
        try:
            line = inspect.getsourcelines(value)[1]
        except (OSError, TypeError):
            line = None
        return path, line, value.__qualname__
    frame = inspect.currentframe()
    while frame is not None:
        if not frame.f_globals.get("__name__", "").startswith(__package__):
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
    if kind in {"node", "rule", "base_lib", "host_extension", "plugin"} and not (kind == "rule" and options.get("handler") and value is None and source is None):
        locator = _json(source) if source is not None else {"kind": "file", "ref": path, "export": symbol}
        implementation = {"language": "python", "source": locator}
        if kind != "rule":
            implementation["targets"] = ["python"]
        data.setdefault("implementations", [implementation])
    try:
        descriptor = decode_resource(data)
    except ValueError as error:
        error.location = {"path":path, **({"line":line} if line is not None else {})}
        raise
    return ResourceDefinition(descriptor, value, path, line, symbol)


def _decorator(kind, options, source=None):
    if source is not None:
        return _declare(kind, options, source=source)
    def attach(value):
        result = _declare(kind, options, value)
        value.__vibeflow_resource__ = result
        return value
    return attach


def node(*, type_key: str, contract, flow_kind="process", source=None, **options):
    """Declare a class implementing run_pure; source enables delayed binding."""
    options = {"type_key": type_key, "contract": contract, "flow_kind": flow_kind,
               "display_name": type_key, "description": type_key, "version": "1.0.0", **options}
    return _decorator("node", options, source)


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


def base_lib(*, id: str, source=None, **options):
    return _decorator("base_lib", {"id": id, "display_name": id, "description": id, **options}, source)


def host_extension(*, id: str, **options):
    return _declare("host_extension", {"id": id, **options})


__all__ = ["ResourceDefinition", "node", "rule", "ruleset", "data_schema", "capability",
           "base_lib", "host_extension", "RuleCall", "RuleRelation", "SourceLocator", "RulesetDescriptor"]
