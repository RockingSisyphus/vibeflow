"""Characterization tests for the language-neutral Core boundary."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.targets.python.project.compiler import GraphCompiler as PythonGraphCompiler
from vibeflow.core.compiler import GraphCompileError, GraphCompiler, compile_core
from vibeflow.core.constants import FLOW_KIND_PROCESS
from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec
from vibeflow.core.models import (
    CoreCompileRequest,
    ImplementationFact,
    ImplementationFacts,
    TargetFeatureSet,
)


def _graph() -> GraphConfig:
    return GraphConfig(
        nodes=(
            NodeSpec(id="first", type_used="fixture.first"),
            NodeSpec(id="second", type_used="fixture.second"),
        ),
        edges=(EdgeSpec("first", "second"),),
    )


def _facts() -> ImplementationFacts:
    return ImplementationFacts(
        (
            ImplementationFact("fixture.second", flow_kind=FLOW_KIND_PROCESS),
            ImplementationFact("fixture.first", flow_kind=FLOW_KIND_PROCESS),
        ),
        strict=True,
    )


def test_compile_core_accepts_only_static_facts_and_is_deterministic() -> None:
    request = CoreCompileRequest(
        graph=_graph(),
        implementation_facts=_facts(),
        target_features=TargetFeatureSet(
            target="fixture",
            features=frozenset({"graph", "condition"}),
        ),
    )

    first = compile_core(request)
    second = compile_core(request)

    assert first == second
    assert first.workflow.graph is request.graph
    assert first.graph.order == ("first", "second")
    assert first.graph.flow_kinds == {
        "first": FLOW_KIND_PROCESS,
        "second": FLOW_KIND_PROCESS,
    }
    assert first.workflow.implementation_facts.to_dict() == {
        "strict": True,
        "nodes": [item.to_dict() for item in _facts().nodes],
    }


def test_pure_graph_compiler_rejects_missing_strict_implementation_fact() -> None:
    with pytest.raises(GraphCompileError, match="unknown type_used 'fixture.second'"):
        GraphCompiler().compile(
            _graph(),
            implementation_facts=ImplementationFacts(
                (ImplementationFact("fixture.first", flow_kind="process"),),
                strict=True,
            ),
        )


def test_python_registry_adapter_matches_pure_compiler_output() -> None:
    class Registered:
        flow_kind = FLOW_KIND_PROCESS

    class Registry:
        def require(self, type_key: str) -> type[Registered]:
            if type_key not in {"fixture.first", "fixture.second"}:
                raise KeyError(type_key)
            return Registered

    adapted = PythonGraphCompiler().compile(_graph(), registry=Registry())
    pure = GraphCompiler().compile(_graph(), implementation_facts=_facts())

    assert adapted == pure


def test_importing_core_does_not_load_target_or_tooling_layers() -> None:
    project_root = Path(__file__).resolve().parents[2]
    script = """
import json
import sys
sys.path.insert(0, 'src')
import vibeflow.core
forbidden = ('vibeflow.runtime', 'vibeflow.aot', 'vibeflow.workspace', 'vibeflow.rendering')
print(json.dumps(sorted(name for name in sys.modules if name.startswith(forbidden))))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout) == []
