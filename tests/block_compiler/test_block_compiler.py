"""Tests for the canonical language-neutral Block Compiler boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.block_compiler import (
    ExecutionLockPlan,
    WORKFLOW_ABI_VERSION,
    PortablePlanError,
    SourceRef,
    WorkflowPlan,
    compile_graph_plan,
    compile_workflow,
)
from vibeflow.core.constants import (
    EFFECT_SCOPE_GLOBAL_STATE,
    FLOW_KIND_GLOBAL_STATE,
    TARGET_FEATURE_EXECUTION_LOCKS,
    TARGET_FEATURE_GLOBAL_STATE,
)
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.compiler import GraphCompileError, compile_core
from vibeflow.core.flow import (
    EdgeSpec,
    ExecutionLockSpec,
    GraphConfig,
    LoopSpec,
    NodeCallSpec,
    NodesetTypeSpec,
)
from vibeflow.core.models import (
    CoreCompileRequest,
    ImplementationFact,
    ImplementationFacts,
    TargetFeatureSet,
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
            NodeCallSpec("start", "fixture.terminal"),
            NodeCallSpec("step", "fixture.step", params=params or {}),
            NodeCallSpec("end", "fixture.terminal"),
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
            known_nodeset_types=frozenset(graph.nodeset_types),
        )
    ).workflow
    return compile_workflow(validated, facts)


def _compile_global(
    graph: GraphConfig,
    facts: ImplementationFacts,
) -> WorkflowPlan:
    target_features = TargetFeatureSet(
        target="python",
        features=frozenset(
            {
                TARGET_FEATURE_EXECUTION_LOCKS,
                TARGET_FEATURE_GLOBAL_STATE,
            }
        ),
    )
    validated = compile_core(
        CoreCompileRequest(
            graph=graph,
            implementation_facts=facts,
            known_nodeset_types=frozenset(graph.nodeset_types),
            target_features=target_features,
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
    with pytest.raises(PortablePlanError, match="workflow ABI must be"):
        replace(first, abi_version="vibeflow.workflow.v2")


def test_compile_workflow_compiles_nested_nodesets_without_target_objects() -> None:
    child = _linear_graph(params={"amount": 2})
    nodeset = NodesetTypeSpec(
        type_key="fixture.group",
        display_name="Group",
        description="A nested portable calculation.",
        requires=(),
        provides=(),
        graph=child,
    )
    graph = GraphConfig(
        nodes=(
            NodeCallSpec("start", "fixture.terminal"),
            NodeCallSpec("group", "fixture.group"),
            NodeCallSpec("end", "fixture.terminal"),
        ),
        edges=(EdgeSpec("start", "group"), EdgeSpec("group", "end")),
        nodeset_types={nodeset.type_key: nodeset},
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
            source_by_definition={"fixture.step": lambda: None},  # type: ignore[dict-item]
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


def test_abi_v5_serializes_global_state_and_locks_without_dispatch() -> None:
    facts = ImplementationFacts(
        (
            ImplementationFact(
                "fixture.state",
                flow_kind=FLOW_KIND_GLOBAL_STATE,
                effect_scope=EFFECT_SCOPE_GLOBAL_STATE,
            ),
            ImplementationFact(
                "fixture.step",
                flow_kind="process",
                effect_scope="none",
            ),
        ),
        strict=True,
    )
    graph = GraphConfig(
        nodes=(
            NodeCallSpec("state", "fixture.state"),
            NodeCallSpec(
                "step",
                "fixture.step",
                execution_lock=ExecutionLockSpec("trainer"),
            ),
        ),
        execution_lock=ExecutionLockSpec("trainer"),
        root_id="fixture.locked",
    )

    plan = _compile_global(graph, facts)
    payload = plan.to_dict()
    root = plan.block(plan.entry_block)

    assert plan.abi_version == WORKFLOW_ABI_VERSION == "vibeflow.workflow.v10"
    assert plan.contains_global_state is True
    assert "root_exclusive" not in payload
    assert payload["execution_lock"] == {"key": "trainer", "scope": "root"}
    assert root.contains_global_state is True
    assert "root_exclusive" not in root.to_dict()
    state = root.node("state")
    assert state.effect_scope == EFFECT_SCOPE_GLOBAL_STATE
    assert "runtime_dispatch" not in state.to_dict()
    assert state.contains_global_state is True
    assert "runtime_dispatch" not in root.node("step").to_dict()
    assert root.node("step").execution_lock.to_dict() == {
        "key": "trainer",
        "scope": "node",
    }
    with pytest.raises(PortablePlanError, match="reserved prefix"):
        ExecutionLockPlan("vibeflow.internal", "node")
    with pytest.raises(PortablePlanError, match="workflow ABI must be"):
        replace(plan, abi_version="vibeflow.workflow.v3")


def test_nested_global_state_and_ordinary_calls_have_independent_plan_facts():
    facts = ImplementationFacts((ImplementationFact("fixture.state",flow_kind=FLOW_KIND_GLOBAL_STATE),
        ImplementationFact("fixture.side",flow_kind="process")),strict=True)
    child = GraphConfig(nodes=(NodeCallSpec("state","fixture.state"),))
    group = NodesetTypeSpec("fixture.group","Group","Contains process-global work",(),(),child)
    graph = GraphConfig(nodes=(NodeCallSpec("group","fixture.group"),NodeCallSpec("side","fixture.side")),
        nodeset_types={group.type_key:group})
    plan = _compile_global(graph,facts)
    root = plan.block(plan.entry_block)
    assert plan.contains_global_state and root.node("group").contains_global_state
    assert not root.node("side").contains_global_state
    assert all(block.kind in {"workflow","nodeset","loop"} for block in plan.blocks)
    assert "tasks" not in root.to_dict()



@pytest.mark.parametrize("planned_definition", (False, True))
def test_planned_nodeset_subtree_is_visible_but_never_compiled_for_execution(
    planned_definition: bool,
) -> None:
    child = GraphConfig(
        nodes=(NodeCallSpec("state", "fixture.unavailable_global"),)
    )
    nodeset = NodesetTypeSpec(
        type_key="fixture.future_group",
        display_name="Future Group",
        description="A planned subtree that is architecture-only.",
        requires=(),
        provides=(),
        graph=child,
        status="planned" if planned_definition else "implemented",
    )
    invocation = NodeCallSpec(
        "future",
        nodeset.type_key,
        status="implemented" if planned_definition else "planned",
        flow_kind="" if planned_definition else FLOW_KIND_GLOBAL_STATE,
        execution_lock=ExecutionLockSpec("project.future"),
    )
    graph = GraphConfig(
        nodes=(invocation,),
        nodeset_types={nodeset.type_key: nodeset},
    )

    # No global-state/lock Target features and no implementation fact for the
    # child are intentional: planned subtrees are review data, not execution.
    plan = _compile(graph)
    root = plan.block(plan.entry_block)
    future = root.node("future")

    assert len(plan.blocks) == 1
    assert plan.contains_global_state is False
    assert root.contains_global_state is False
    assert future.status == "planned"
    assert future.child_block == ""
    assert future.contains_global_state is False
    assert future.execution_lock.key == "project.future"
    assert future.execution_lock.scope == "block"


def test_nested_execution_locks_must_reuse_same_key() -> None:
    facts = ImplementationFacts(
        (ImplementationFact("fixture.step", flow_kind="process"),),
        strict=True,
    )
    child = GraphConfig(
        nodes=(NodeCallSpec("step", "fixture.step"),),
        execution_lock=ExecutionLockSpec("child"),
    )
    nodeset = NodesetTypeSpec(
        type_key="fixture.group",
        display_name="Group",
        description="Nested lock fixture.",
        requires=(),
        provides=(),
        graph=child,
    )
    graph = GraphConfig(
        nodes=(NodeCallSpec("group", "fixture.group"),),
        nodeset_types={nodeset.type_key: nodeset},
        execution_lock=ExecutionLockSpec("root"),
    )

    with pytest.raises(
        GraphCompileError,
        match="GRAPH.EXECUTION_LOCK.NESTED_KEY_CONFLICT",
    ):
        _compile_global(graph, facts)


def test_composite_invocation_locks_use_block_scope() -> None:
    facts = _facts()
    child = _linear_graph()
    nodeset = NodesetTypeSpec(
        type_key="fixture.group",
        display_name="Group",
        description="Composite lock scope fixture.",
        requires=(),
        provides=(),
        graph=child,
    )
    graph = GraphConfig(
        nodes=(
            NodeCallSpec(
                "group",
                "fixture.group",
                execution_lock=ExecutionLockSpec("project.group"),
            ),
            NodeCallSpec(
                "loop",
                "vibeflow.loop.while",
                loop=LoopSpec(body="fixture.group", stop_after=1),
                execution_lock=ExecutionLockSpec("project.loop"),
            ),
        ),
        nodeset_types={nodeset.type_key: nodeset},
    )

    root = _compile_global(graph, facts).block("block:/")

    assert root.node("group").execution_lock.scope == "block"
    assert root.node("loop").execution_lock.scope == "block"


def test_portable_plan_has_no_hidden_task_execution_protocol():
    from vibeflow.core.config.graph import parse_graph_config_data
    from vibeflow.core.flow import GraphConfigError
    with pytest.raises(GraphConfigError,match="GRAPH.TASK.MIGRATION"):
        parse_graph_config_data({"pipeline":{"nodes":[{"id":"dispatch","definition_id":"fixture.work",
            "task_targets":{"work":{"definition_id":"fixture.work"}}}]}})
    with pytest.raises(TypeError,match="task_targets"):
        NodeCallSpec("dispatch","fixture.work",task_targets={})
