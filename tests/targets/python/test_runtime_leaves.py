"""Python Target runtime leaf-module behavior gates."""

from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec
from vibeflow.core.planned import PlannedBehavior


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


def test_runtime_leaf_imports_do_not_load_outer_engine_or_frontends() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.python.runtime.errors
import vibeflow.targets.python.runtime.options
import vibeflow.targets.python.runtime.summaries
import vibeflow.targets.python.runtime.trace
import vibeflow.targets.python.runtime.types
import vibeflow.targets.python.runtime.values
import vibeflow.targets.python.runtime.helpers
import vibeflow.targets.python.runtime.config
import vibeflow.targets.python.runtime.block_compiler
import vibeflow.targets.python.runtime.compiled

forbidden = (
    "vibeflow.targets.python.project.compiler",
    "vibeflow.graph_config",
    "vibeflow.targets.python.project.node",
    "vibeflow.targets.python.project.plugins",
    "vibeflow.runtime",
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


def test_python_block_compiler_source_is_deterministic_golden() -> None:
    from vibeflow.targets.python.runtime.block_compiler import compile_blocks

    def frame():
        return SimpleNamespace(
            is_loop=False,
            is_nodeset=False,
            is_planned_stub=False,
            async_mode="",
            outgoing=(),
        )

    plan = SimpleNamespace(
        order=("start", "finish"),
        frames={"start": frame(), "finish": frame()},
        graph=SimpleNamespace(
            nodes=(SimpleNamespace(name="start"), SimpleNamespace(name="finish"))
        ),
        compiled=SimpleNamespace(resolved_schedule_edges=()),
    )

    first = compile_blocks(plan)
    second = compile_blocks(plan)

    assert len(first) == 1
    assert first[0].name == "graph:start"
    assert first[0].nodes == ("start", "finish")
    assert first[0].source == second[0].source
    assert sha256(first[0].source.encode("utf-8")).hexdigest() == (
        "8f4020800294f513cb8c113e9b62c62bcb5a8e65eabd87e075a364e67df9473c"
    )


def test_condition_matching_keeps_portable_literal_semantics() -> None:
    from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
    from vibeflow.targets.python.runtime.helpers import condition_matches

    assert condition_matches("ready == true", {"ready": True})
    assert not condition_matches("ready == true", {"ready": 1})
    assert condition_matches("state != 'closed'", {"state": "open"})
    with pytest.raises(
        PipelineRuntimeError,
        match="unsupported edge condition: ready",
    ):
        condition_matches("ready", {"ready": True})
    with pytest.raises(
        PipelineRuntimeError,
        match="invalid edge condition: == true",
    ):
        condition_matches("== true", {"ready": True})


def test_planned_helpers_traverse_nested_nodesets_once() -> None:
    from vibeflow.targets.python.runtime.helpers import (
        all_planned_are_python_stub,
        has_planned,
        planned_items,
        referenced_nodeset_names,
    )

    planned_leaf = NodeSpec(
        id="leaf",
        type_used="example.leaf",
        status="planned",
        planned_behavior=PlannedBehavior(
            kind="python_stub",
            stub_module="stubs/leaf.py",
        ),
    )
    nested_graph = GraphConfig(nodes=(planned_leaf,))
    nested = NodesetSpec(
        type_key="example.group",
        display_name="Group",
        description="Nested planned traversal fixture.",
        requires=(),
        provides=(),
        graph=nested_graph,
    )
    root = GraphConfig(
        nodes=(NodeSpec(id="group", type_used="example.group"),),
        nodesets={"example.group": nested},
    )

    assert has_planned(root)
    assert planned_items(root) == (
        {
            "id": "nodeset.example.group.leaf",
            "object_type": "node",
            "behavior": "python_stub",
            "stub_module": "stubs/leaf.py",
        },
    )
    assert all_planned_are_python_stub(root)
    assert referenced_nodeset_names(root) == ("example.group",)
