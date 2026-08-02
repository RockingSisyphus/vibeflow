"""Tests for the Python-only binding sidecar boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import json
from typing import Mapping

import pytest

from vibeflow.block_compiler.model import (
    BlockPlan,
    NodeCallPlan,
    SourceRef,
    freeze_json_object,
)
from vibeflow.targets.python.project.bindings import (
    PythonBindingError,
    PythonBindingPlan,
    PythonCallBinding,
)


class _HostilePythonObject:
    def __repr__(self) -> str:
        raise AssertionError("metadata must not call repr")

    def __call__(self, *args, **kwargs):
        raise AssertionError("metadata must not invoke the implementation")

    def to_dict(self) -> dict[str, object]:
        raise AssertionError("metadata must not invoke object serializers")


def _binding(
    path: tuple[str, ...],
    implementation: object,
    *,
    params: Mapping[str, object] | None = None,
) -> PythonCallBinding:
    return PythonCallBinding(
        path=path,
        type_key="fixture.python",
        implementation=implementation,
        effective_params=params or {},
        source=SourceRef(
            kind="python",
            ref="fixture.nodes",
            export="PythonNode",
        ),
        source_hash="sha256:fixture",
    )


def test_binding_sidecar_is_frozen_and_preserves_live_object_identity() -> None:
    implementation = _HostilePythonObject()
    parameter_object = _HostilePythonObject()
    plugin_registry = _HostilePythonObject()
    binding = _binding(
        ("step",),
        implementation,
        params={"nested": {"items": [parameter_object, 2]}},
    )
    plan = PythonBindingPlan(
        block_id="block:/",
        calls=[binding],  # type: ignore[arg-type]
        plugin_registry=plugin_registry,
    )

    assert binding.implementation is implementation
    assert binding.effective_params["nested"]["items"][0] is parameter_object  # type: ignore[index]
    assert plan.calls[0] is binding
    assert plan.plugin_registry is plugin_registry
    assert isinstance(binding.effective_params, Mapping)
    assert binding.effective_params["nested"]["items"] == (parameter_object, 2)  # type: ignore[index]

    with pytest.raises(FrozenInstanceError):
        binding.source_hash = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        binding.effective_params["new"] = 1  # type: ignore[index]
    with pytest.raises(TypeError):
        binding.effective_params["nested"]["new"] = 1  # type: ignore[index]

    metadata = plan.to_metadata()
    json.dumps(metadata, sort_keys=True)
    assert metadata["plugin_registry"] == {
        "kind": "instance",
        "type": {
            "module": __name__,
            "qualname": "_HostilePythonObject",
        },
    }
    call_metadata = metadata["calls"][0]  # type: ignore[index]
    assert call_metadata["source_hash"] == "sha256:fixture"
    assert call_metadata["implementation"]["kind"] == "instance"


def test_recursive_lookup_returns_the_original_binding_instances() -> None:
    implementation = object()
    root_call = _binding(("root",), implementation)
    child_call = _binding(("group", "child"), implementation)
    grandchild_call = _binding(("group", "nested", "leaf"), implementation)
    grandchild = PythonBindingPlan(
        block_id="block:/group/nested",
        calls=(grandchild_call,),
    )
    child = PythonBindingPlan(
        block_id="block:/group",
        calls=(child_call,),
        children=(grandchild,),
    )
    root = PythonBindingPlan(
        block_id="block:/",
        calls=(root_call,),
        children=(child,),
    )

    assert root.binding(("root",)) is root_call
    assert root.binding(("group", "child")) is child_call
    assert root.get(("group", "nested", "leaf")) is grandchild_call
    assert root.get(("missing",)) is None
    assert root.all_bindings() == (root_call, child_call, grandchild_call)
    with pytest.raises(KeyError, match="missing"):
        root.binding(("missing",))

    duplicate = PythonBindingPlan(
        block_id="block:/duplicate",
        calls=(_binding(("root",), object()),),
    )
    with pytest.raises(PythonBindingError, match="paths must be unique"):
        PythonBindingPlan(
            block_id="block:/",
            calls=(root_call,),
            children=(duplicate,),
        )


def test_metadata_projection_is_plain_and_deterministic() -> None:
    implementation = _HostilePythonObject()
    first = PythonBindingPlan(
        block_id="block:/",
        calls=(
            _binding(
                ("step",),
                implementation,
                params={
                    "z": [3, {"b": 2, "a": 1}],
                    "a": True,
                    "opaque": implementation,
                },
            ),
        ),
    )
    second = PythonBindingPlan(
        block_id="block:/",
        calls=(
            _binding(
                ("step",),
                implementation,
                params={
                    "opaque": implementation,
                    "a": True,
                    "z": [3, {"a": 1, "b": 2}],
                },
            ),
        ),
    )

    first_metadata = first.to_metadata()
    second_metadata = second.to_metadata()
    assert first_metadata == second_metadata
    assert json.dumps(
        first_metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ) == json.dumps(
        second_metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    opaque = first_metadata["calls"][0]["effective_params"]["opaque"]  # type: ignore[index]
    assert opaque == {
        "$python": {
            "kind": "instance",
            "type": {
                "module": __name__,
                "qualname": "_HostilePythonObject",
            },
        }
    }


def test_portable_block_plan_never_contains_python_binding_objects() -> None:
    implementation = _HostilePythonObject()
    plugin_registry = _HostilePythonObject()
    source = SourceRef(
        kind="python",
        ref="fixture.nodes",
        export="PythonNode",
    )
    binding = _binding(("step",), implementation)
    sidecar = PythonBindingPlan(
        block_id="block:/",
        calls=(binding,),
        plugin_registry=plugin_registry,
    )
    call = NodeCallPlan(
        id="step",
        type_used="fixture.python",
        implementation=source,
        requires=(),
        provides=(),
        params=freeze_json_object({}),
        config_overrides=freeze_json_object({}),
        flow_kind="process",
        join_policy="safe_any",
        status="implemented",
        planned_behavior="blocking_stub",
        async_mode="",
        result_key="",
        is_terminal=False,
        is_nodeset=False,
        is_loop=False,
        nodeset_type_key="",
        child_block="",
        exports=(),
    )
    block = BlockPlan(
        id="block:/",
        kind="workflow",
        path=(),
        source=SourceRef(kind="graph", ref="fixture"),
        inputs=(),
        outputs=(),
        nodes=(call,),
        routes=(),
        order=("step",),
        entries=("step",),
        exits=("step",),
        max_steps=10,
    )

    values = tuple(_walk_values(block))
    assert sidecar.binding(("step",)) is binding
    assert call.implementation is source
    assert implementation not in values
    assert plugin_registry not in values
    assert PythonCallBinding not in {field.type for field in fields(BlockPlan)}
    assert PythonBindingPlan not in {field.type for field in fields(BlockPlan)}
    json.dumps(block.to_dict(), sort_keys=True)


def _walk_values(value: object):
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for dataclass_field in fields(value):
            yield from _walk_values(getattr(value, dataclass_field.name))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_values(key)
            yield from _walk_values(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _walk_values(item)


def test_effective_params_reject_circular_or_non_string_mappings() -> None:
    circular: dict[str, object] = {}
    circular["self"] = circular
    with pytest.raises(PythonBindingError, match="circular"):
        _binding(("step",), object(), params=circular)

    with pytest.raises(PythonBindingError, match="non-string"):
        _binding(("step",), object(), params={1: "value"})  # type: ignore[dict-item]
