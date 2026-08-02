"""Tests for the canonical language-neutral Block Compiler boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.block_compiler import (
    PortablePlanError,
    SourceRef,
    WorkflowPlan,
    compile_graph_plan,
    compile_workflow,
)
from vibeflow.core.compiler import compile_core
from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec, NodesetSpec
from vibeflow.core.models import (
    CoreCompileRequest,
    ImplementationFact,
    ImplementationFacts,
)


ROOT = Path(__file__).resolve().parents[2]


def _facts() -> ImplementationFacts:
    return ImplementationFacts(
        (
            ImplementationFact(
                "fixture.step",
                flow_kind="process",
                source_kind="typescript",
                source_ref="nodes/step.ts",
                source_export="run",
            ),
            ImplementationFact(
                "fixture.terminal",
                flow_kind="terminal",
                source_kind="typescript",
                source_ref="nodes/terminal.ts",
                source_export="run",
            ),
        ),
        strict=True,
    )


def _linear_graph(*, params: dict[str, object] | None = None) -> GraphConfig:
    return GraphConfig(
        nodes=(
            NodeSpec("start", "fixture.terminal"),
            NodeSpec("step", "fixture.step", params=params or {}),
            NodeSpec("end", "fixture.terminal"),
        ),
        edges=(EdgeSpec("start", "step"), EdgeSpec("step", "end")),
        root_id="fixture.workflow",
    )


def _compile(graph: GraphConfig) -> WorkflowPlan:
    facts = _facts()
    validated = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            known_nodesets=frozenset(graph.nodesets),
        )
    ).workflow
    return compile_workflow(validated, facts)


def _values(value: object):
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from _values(getattr(value, field.name))
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _values(key)
            yield from _values(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _values(item)


def test_canonical_ir_identity_and_compilation_are_deterministic() -> None:
    first = _compile(
        _linear_graph(params={"z": [3, {"b": 2, "a": 1}], "a": True})
    )
    second = _compile(
        _linear_graph(params={"a": True, "z": [3, {"a": 1, "b": 2}]})
    )

    assert WorkflowPlan.__module__ == "vibeflow.block_compiler.model"
    assert first.to_json() == second.to_json()
    assert json.loads(first.to_json()) == first.to_dict()
    step = first.block(first.entry_block).node("step")
    assert step.implementation == SourceRef(
        kind="typescript",
        ref="nodes/step.ts",
        export="run",
    )
    assert not any(
        isinstance(value, type) or callable(value)
        for value in _values(first)
    )
    with pytest.raises(FrozenInstanceError):
        first.max_steps = 1


def test_compile_workflow_compiles_nested_nodesets_without_target_objects() -> None:
    child = _linear_graph(params={"amount": 2})
    nodeset = NodesetSpec(
        type_key="fixture.group",
        display_name="Group",
        description="A nested portable calculation.",
        requires=(),
        provides=(),
        graph=child,
    )
    graph = GraphConfig(
        nodes=(
            NodeSpec("start", "fixture.terminal"),
            NodeSpec("group", "fixture.group"),
            NodeSpec("end", "fixture.terminal"),
        ),
        edges=(EdgeSpec("start", "group"), EdgeSpec("group", "end")),
        nodesets={nodeset.type_key: nodeset},
        root_id="fixture.nested",
    )

    first = _compile(graph)
    second = _compile(graph)

    assert first.to_json() == second.to_json()
    assert [block.kind for block in first.blocks] == ["workflow", "nodeset"]
    group = first.block(first.entry_block).node("group")
    assert group.child_block == "block:/group"
    assert first.block(group.child_block).node("step").params.to_value() == {
        "amount": 2
    }


@pytest.mark.parametrize("binding", (lambda: None, dict))
def test_compile_workflow_rejects_language_bindings(binding: object) -> None:
    graph = _linear_graph(params={"binding": binding})

    with pytest.raises(PortablePlanError, match="non-portable value"):
        _compile(graph)


def test_source_override_rejects_language_bindings() -> None:
    graph = _linear_graph()
    facts = _facts()
    compilation = compile_core(
        CoreCompileRequest(graph=graph, implementation_facts=facts)
    )

    with pytest.raises(PortablePlanError, match="must be a SourceRef"):
        compile_graph_plan(
            graph,
            compilation.compiled_graph,
            source_by_type={"fixture.step": lambda: None},  # type: ignore[dict-item]
        )


def test_importing_block_compiler_loads_only_core_and_stdlib_layers() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(ROOT / "src"), env.get("PYTHONPATH", ""))
        if part
    )
    script = """
import json
import sys
import vibeflow.block_compiler
forbidden = (
    'vibeflow.portable',
    'vibeflow.runtime',
    'vibeflow.aot',
    'vibeflow.workspace',
    'vibeflow.rendering',
    'vibeflow.targets',
    'vibeflow.tooling',
)
print(json.dumps(sorted(
    name for name in sys.modules
    if any(name == item or name.startswith(item + '.') for item in forbidden)
)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []
