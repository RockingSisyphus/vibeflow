from __future__ import annotations

from typing import Any, Mapping

from .data_contract import DataProvider
from .graph_config_types import (
    GraphConfigError,
    LoopCarrySpec,
    LoopCollectSpec,
    LoopOutputSpec,
    LoopSpec,
    LoopStopWhenSpec,
    LOOP_NODE_TYPES,
)

def _parse_loop_spec(value: Any, *, type_used: str, provides: tuple[DataProvider, ...], field: str) -> LoopSpec:
    if type_used not in LOOP_NODE_TYPES:
        if value not in (None, {}):
            raise GraphConfigError(f"{field} is only allowed on VibeFlow loop nodes")
        return LoopSpec()
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    allowed = {"body", "max_iterations", "stop_after", "stop_when", "carry", "collect", "outputs"}
    unknown = sorted(set(str(key) for key in value) - allowed)
    if unknown:
        raise GraphConfigError(f"{field} contains unsupported loop keys: {unknown}")
    body = _parse_required_text(value.get("body"), field=f"{field}.body")
    max_iterations = _parse_positive_int(value.get("max_iterations", 1000), field=f"{field}.max_iterations")
    has_stop_after = "stop_after" in value
    has_stop_when = "stop_when" in value
    if has_stop_after == has_stop_when:
        raise GraphConfigError(f"{field} must declare exactly one of stop_after or stop_when")
    stop_after = _parse_positive_int(value.get("stop_after"), field=f"{field}.stop_after") if has_stop_after else 0
    if stop_after and stop_after > max_iterations:
        raise GraphConfigError(f"{field}.stop_after must be <= max_iterations")
    stop_when = _parse_loop_stop_when(value.get("stop_when"), field=f"{field}.stop_when") if has_stop_when else LoopStopWhenSpec()
    carry = tuple(_parse_loop_carry_item(item, field=f"{field}.carry[{index}]") for index, item in enumerate(_parse_list(value.get("carry", ()), field=f"{field}.carry")))
    collect = tuple(_parse_loop_collect_item(item, field=f"{field}.collect[{index}]") for index, item in enumerate(_parse_list(value.get("collect", ()), field=f"{field}.collect")))
    outputs = tuple(_parse_loop_output_item(item, field=f"{field}.outputs[{index}]") for index, item in enumerate(_parse_list(value.get("outputs", ()), field=f"{field}.outputs")))
    if not outputs:
        outputs = tuple(LoopOutputSpec(source=provider.key, target=provider.key) for provider in provides)
    return LoopSpec(
        body=_normalize_loop_body(body),
        max_iterations=max_iterations,
        stop_after=stop_after,
        stop_when=stop_when,
        carry=carry,
        collect=collect,
        outputs=outputs,
    )

def _parse_loop_stop_when(value: Any, *, field: str) -> LoopStopWhenSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    equals = value.get("equals", True)
    if not isinstance(equals, bool):
        raise GraphConfigError(f"{field}.equals must be a boolean")
    return LoopStopWhenSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        equals=equals,
    )

def _parse_loop_carry_item(value: Any, *, field: str) -> LoopCarrySpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    return LoopCarrySpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
        update=_parse_required_text(value.get("update"), field=f"{field}.update"),
    )

def _parse_loop_collect_item(value: Any, *, field: str) -> LoopCollectSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    mode = str(value.get("mode", "all")).strip()
    if mode != "all":
        raise GraphConfigError(f"{field}.mode must be 'all'")
    return LoopCollectSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
        mode=mode,
    )

def _parse_loop_output_item(value: Any, *, field: str) -> LoopOutputSpec:
    if not isinstance(value, Mapping):
        raise GraphConfigError(f"{field} must be an object")
    return LoopOutputSpec(
        source=_parse_required_text(value.get("from"), field=f"{field}.from"),
        target=_parse_required_text(value.get("as"), field=f"{field}.as"),
    )

def _parse_required_text(value: Any, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GraphConfigError(f"{field} must be a non-empty string")
    return text

def _parse_positive_int(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise GraphConfigError(f"{field} must be an integer >= 1")
    return value

def _parse_list(value: Any, *, field: str) -> list[Any]:
    if value in (None, ()):
        return []
    if isinstance(value, str) or not isinstance(value, list):
        raise GraphConfigError(f"{field} must be a list")
    return value

def _normalize_loop_body(value: str) -> str:
    if value.startswith("nodeset."):
        raise GraphConfigError("loop.body must use the nodeset type_key directly, not nodeset.<name>")
    return value
