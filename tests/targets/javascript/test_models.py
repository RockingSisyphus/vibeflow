"""Isolation and behavior gates for JavaScript Target models."""

from __future__ import annotations

from dataclasses import fields
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys

import pytest

from vibeflow.block_compiler import (
    BlockPlan,
    NodeCallPlan,
    PortablePlanError,
    SourceRef,
    WorkflowPlan,
    freeze_json_object,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptBindingPlan,
    JavascriptCallBinding,
    build_javascript_binding_plan,
)
from vibeflow.targets.javascript.frontend.model_types import CapabilityRequirement


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    environment = os.environ.copy()
    existing = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), existing) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_javascript_target_import_does_not_load_removed_or_python_layers() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.javascript

forbidden = (
    "vibeflow.aot",
    "vibeflow.targets.python",
    "vibeflow.tooling",
)
loaded = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden)
)
assert loaded == [], loaded
"""
    )


def _binding_plan(*, reverse: bool = False) -> JavascriptBindingPlan:
    schema = {
        "required": ["value"],
        "properties": {"value": {"type": "number"}},
        "type": "object",
    }
    if reverse:
        schema = dict(reversed(tuple(schema.items())))
    call = JavascriptCallBinding(
        path=("calculate",),
        type_key="demo.calculate",
        implementation=SourceRef(
            kind="typescript",
            ref="project/nodes/calculate.ts",
            export="run",
        ),
        params={"delta": 2},
        base_libs=("demo.math",),
        capabilities=(
            CapabilityRequirement("demo.clock", ("now",)),
        ),
    )
    return JavascriptBindingPlan(
        workflow_id="demo.workflow",
        calls=(call,),
        schemas={"demo.number": schema},
        base_libs={
            "demo.math": {
                "language": "typescript",
                "ref": "project/base_lib/math.ts",
            }
        },
        capabilities={
            "demo.clock": {
                "operations": {
                    "now": {"completion": "immediate"},
                }
            }
        },
        host_extensions=(
            {
                "id": "demo.host",
                "ref": "project/host.ts",
                "provides": ["demo.clock"],
            },
        ),
        import_policy={
            "owners": [],
            "nodeBaseLibs": {"demo.calculate": ["demo.math"]},
        },
    )


def test_javascript_binding_plan_is_deterministic_and_pickleable() -> None:
    first = _binding_plan()
    second = _binding_plan(reverse=True)

    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json()) == first.to_dict()
    assert first.binding(("calculate",)) is first.calls[0]


def _portable_call(
    node_id: str,
    type_key: str,
    *,
    child_block: str = "",
    is_nodeset: bool = False,
    is_loop: bool = False,
    io_operation: str = "",
) -> NodeCallPlan:
    return NodeCallPlan(
        id=node_id,
        type_used=type_key,
        implementation=SourceRef(
            kind=("catalog" if child_block or io_operation else "typescript"),
            ref=type_key if child_block or io_operation else f"nodes/{node_id}.ts",
            export="" if child_block or io_operation else "run",
        ),
        requires=(),
        provides=(),
        params=freeze_json_object({"node": node_id}),
        config_overrides=freeze_json_object({}),
        flow_kind="terminal" if io_operation else "process",
        join_policy="safe_any",
        status="implemented",
        planned_behavior="blocking",
        async_mode="",
        result_key="",
        is_terminal=bool(io_operation),
        is_nodeset=is_nodeset,
        is_loop=is_loop,
        nodeset_type_key=type_key if child_block else "",
        child_block=child_block,
        exports=(),
        io_operation=io_operation,
        io_port="events" if io_operation else "",
    )


def _binding_workflow_plan() -> WorkflowPlan:
    root = BlockPlan(
        id="block:/",
        kind="workflow",
        path=(),
        source=SourceRef(kind="graph", ref="binding.workflow"),
        inputs=(),
        outputs=(),
        nodes=(
            _portable_call("start", "demo.start"),
            _portable_call(
                "group",
                "demo.group",
                child_block="block:/group",
                is_nodeset=True,
            ),
            _portable_call(
                "repeat",
                "vibeflow.loop.while",
                child_block="block:/repeat",
                is_loop=True,
            ),
            _portable_call(
                "receive",
                "vibeflow.io",
                io_operation="receive",
            ),
        ),
        routes=(),
        order=("start", "group", "repeat", "receive"),
        entries=("start",),
        exits=("receive",),
        max_steps=50,
    )
    nested = BlockPlan(
        id="block:/group",
        kind="nodeset",
        path=("group",),
        source=SourceRef(kind="graph", ref="demo.group"),
        inputs=(),
        outputs=(),
        nodes=(_portable_call("add", "demo.add"),),
        routes=(),
        order=("add",),
        entries=("add",),
        exits=("add",),
        max_steps=20,
    )
    loop = BlockPlan(
        id="block:/repeat",
        kind="loop",
        path=("repeat",),
        source=SourceRef(kind="graph", ref="demo.loop"),
        inputs=(),
        outputs=(),
        nodes=(_portable_call("multiply", "demo.multiply"),),
        routes=(),
        order=("multiply",),
        entries=("multiply",),
        exits=("multiply",),
        max_steps=20,
    )
    return WorkflowPlan(
        abi_version="vibeflow.workflow.v3",
        workflow_id="binding.workflow",
        source=SourceRef(kind="graph", ref="binding.workflow"),
        entry_block="block:/",
        inputs=(),
        outputs=(),
        blocks=(root, nested, loop),
        max_steps=50,
        entry_mode="async",
    )


def test_binding_builder_shadows_all_call_paths_and_resource_facts() -> None:
    plan = _binding_workflow_plan()
    portable_before = plan.to_json()
    schemas = {
        "demo.output": {"type": "number"},
        "demo.input": {"type": "number"},
    }
    facts = {
        "implementations": {
            "demo.add": {"completion": "suspend"},
            "demo.start": {"completion": "immediate"},
        },
        "base_libs_by_type": {
            "demo.add": ("demo.math", "demo.core"),
            "demo.multiply": ("demo.math",),
        },
        "capabilities_by_type": {
            "demo.add": (
                {"id": "demo.storage", "operations": ["write", "read"]},
            ),
        },
        "schemas": schemas,
        "base_libs": {
            "demo.math": {"dependencies": ["demo.core"]},
            "demo.core": {"dependencies": []},
        },
        "capabilities": {
            "demo.storage": {
                "operations": {"read": {}, "write": {}},
            },
            "vibeflow.port": {"operations": {"receive": {}}},
        },
        "host_extensions": (
            {"id": "demo.host", "provides": ["demo.storage"]},
        ),
        "import_policy": {
            "owners": [],
            "node_base_libs": {"demo.add": ["demo.math", "demo.core"]},
        },
    }
    first = build_javascript_binding_plan(plan, **facts)
    second = build_javascript_binding_plan(
        plan,
        **{
            **facts,
            "implementations": dict(
                reversed(tuple(facts["implementations"].items()))
            ),
            "schemas": dict(reversed(tuple(schemas.items()))),
            "base_libs": dict(
                reversed(tuple(facts["base_libs"].items()))
            ),
            "capabilities": dict(
                reversed(tuple(facts["capabilities"].items()))
            ),
        },
    )

    assert first.to_json() == second.to_json()
    assert tuple(call.path for call in first.calls) == (
        ("start",),
        ("group",),
        ("repeat",),
        ("receive",),
        ("group", "add"),
        ("repeat", "multiply"),
    )
    add = first.binding(("group", "add"))
    assert add.base_libs == ("demo.core", "demo.math")
    assert add.completion == "suspend"
    assert add.executor == "event_loop"
    assert add.capabilities[0].to_dict() == {
        "id": "demo.storage",
        "operations": ["read", "write"],
    }
    receive = first.binding(("receive",))
    assert receive.capabilities[0].to_dict() == {
        "id": "vibeflow.port",
        "operations": ["receive"],
    }
    assert receive.completion == "suspend"
    assert receive.executor == "event_loop"
    assert first.host_extensions[0].to_value()["id"] == "demo.host"
    assert first.base_libs.to_value()["demo.math"]["dependencies"] == [
        "demo.core"
    ]
    assert first.import_policy.to_value()["owners"] == []
    assert plan.to_json() == portable_before
    assert "javascript_bindings" not in plan.to_dict()
    restored = pickle.loads(pickle.dumps(first))
    assert restored == first
    assert restored.to_json() == first.to_json()


def test_javascript_bindings_reject_live_objects_and_duplicate_paths() -> None:
    with pytest.raises(PortablePlanError, match="non-portable"):
        JavascriptBindingPlan(
            workflow_id="demo.invalid",
            schemas={"demo.value": {"default": object()}},
        )
    binding = _binding_plan().calls[0]
    with pytest.raises(ValueError, match="paths must be unique"):
        JavascriptBindingPlan(
            workflow_id="demo.duplicate",
            calls=(binding, binding),
        )


def test_portable_block_plan_has_no_javascript_binding_sidecar() -> None:
    assert "javascript_bindings" not in {field.name for field in fields(BlockPlan)}
    assert "JavascriptBindingPlan" not in BlockPlan.__annotations__.values()
