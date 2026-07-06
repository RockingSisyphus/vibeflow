from __future__ import annotations

from typing import Mapping

from .data_contract import DataEnvelope, DataProvider, RunResult
from .runtime_errors import PipelineRuntimeError

def _store_output(result: RunResult, result_key: str, envelope: DataEnvelope) -> None:
    result.set(result_key, envelope.to_input())

def _inputs_to_initial(inputs: Mapping[str, object]) -> dict[str, object]:
    initial: dict[str, object] = {}
    for value in inputs.values():
        if isinstance(value, list):
            for item in value:
                _copy_input_item(item, initial)
        else:
            _copy_input_item(value, initial)
    return initial

def _nodeset_inputs_to_initial(inputs: Mapping[str, object], graph_inputs: tuple[DataProvider, ...]) -> dict[str, object]:
    initial: dict[str, object] = {}
    input_items = list(_iter_input_items(inputs))
    for provider in graph_inputs:
        for item in input_items:
            if isinstance(item, Mapping) and item.get("type") == provider.type:
                initial[provider.key] = item.get("value")
                break
    return initial

def _initial_loop_values(inputs: Mapping[str, object], carry: tuple[object, ...]) -> dict[str, object]:
    values: dict[str, object] = {}
    for key, item in inputs.items():
        values[str(key)] = _result_value(item)
    for item in _iter_input_items(inputs):
        if isinstance(item, Mapping):
            if "type" in item:
                values[str(item["type"])] = item.get("value")
            if "key" in item:
                values[str(item["key"])] = item.get("value")
    for entry in carry:
        source = str(getattr(entry, "source"))
        target = str(getattr(entry, "target"))
        if source not in values:
            raise PipelineRuntimeError(f"loop carry source '{source}' is not available")
        values[target] = values[source]
    return values

def _loop_body_initial(values: Mapping[str, object], carry: tuple[object, ...]) -> dict[str, object]:
    initial: dict[str, object] = {}
    for entry in carry:
        target = str(getattr(entry, "target"))
        if target not in values:
            raise PipelineRuntimeError(f"loop carry target '{target}' is not available")
        initial[target] = values[target]
    return initial

def _update_loop_values(values: dict[str, object], result: RunResult, carry: tuple[object, ...], collect: tuple[object, ...]) -> None:
    for key, item in _iter_result_envelopes(result.to_dict(), prefix=""):
        values[key] = _result_value(item)
    for entry in carry:
        update = str(getattr(entry, "update"))
        target = str(getattr(entry, "target"))
        if update not in values:
            raise PipelineRuntimeError(f"loop carry update '{update}' is not available from body outputs")
        values[target] = values[update]
    for entry in collect:
        source = str(getattr(entry, "source"))
        target = str(getattr(entry, "target"))
        if source not in values:
            raise PipelineRuntimeError(f"loop collect source '{source}' is not available from body outputs")
        bucket = values.setdefault(target, [])
        if not isinstance(bucket, list):
            raise PipelineRuntimeError(f"loop collect target '{target}' conflicts with a non-list value")
        bucket.append(values[source])

def _loop_outputs(frame: object, values: Mapping[str, object]) -> dict[str, object]:
    outputs: dict[str, object] = {}
    for entry in frame.loop_spec.outputs:
        source = entry.source
        if source not in values:
            raise PipelineRuntimeError(f"loop output source '{source}' is not available")
        outputs[entry.target] = values[source]
    return outputs

def _loop_should_stop(frame: NodeFrame, values: Mapping[str, object], iteration_count: int) -> bool:
    spec = frame.loop_spec
    if spec.stop_after:
        return iteration_count >= spec.stop_after
    source = spec.stop_when.source
    if not source:
        raise PipelineRuntimeError(f"loop node '{frame.name}' has no stop_after or stop_when")
    if source not in values:
        raise PipelineRuntimeError(f"loop stop_when source '{source}' is not available from body outputs or loop state")
    value = values[source]
    if not isinstance(value, bool):
        raise PipelineRuntimeError(f"loop stop_when source '{source}' must be boolean, got {type(value).__name__}")
    return value == spec.stop_when.equals

def _iter_input_items(inputs: Mapping[str, object]):
    for value in inputs.values():
        if isinstance(value, list):
            yield from value
        else:
            yield value

def _iter_result_envelopes(value: object, *, prefix: str):
    if isinstance(value, Mapping) and {"key", "type", "value", "source_node"} <= set(value):
        if prefix:
            yield prefix, value
        return
    if not isinstance(value, Mapping):
        if prefix:
            yield prefix, value
        return
    for key, item in value.items():
        child = f"{prefix}.{key}" if prefix else str(key)
        yield from _iter_result_envelopes(item, prefix=child)

def _copy_input_item(item: object, initial: dict[str, object]) -> None:
    if isinstance(item, Mapping) and "key" in item:
        initial[str(item["key"])] = item.get("value")

def _result_value(item: object) -> object:
    if isinstance(item, Mapping) and {"key", "type", "value", "source_node"} <= set(item):
        return item.get("value")
    return item
