"""Isolation and behavior checks for the Python frontend."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    env = os.environ.copy()
    current = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), current) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_neutral_imports_do_not_load_python_target() -> None:
    _run_isolated(
        """
import sys
import vibeflow
import vibeflow.core
import vibeflow.core.descriptors
import vibeflow.block_compiler

loaded = sorted(
    name for name in sys.modules
    if name == "vibeflow.targets" or name.startswith("vibeflow.targets.")
)
assert loaded == [], loaded
"""
    )


def test_core_descriptor_identity_and_file_provenance_boundary() -> None:
    from vibeflow.core.descriptors import (
        DescriptorCatalogs as CoreDescriptorCatalogs,
        NodeCatalog as CoreNodeCatalog,
        NodeDescriptor as CoreNodeDescriptor,
    )
    from vibeflow.core.descriptors.models import NodeDescriptor
    from vibeflow.tooling.project.descriptor_catalogs import DescriptorCatalogs

    assert NodeDescriptor is CoreNodeDescriptor
    assert CoreNodeDescriptor.__module__ == "vibeflow.core.descriptors.models"
    assert issubclass(DescriptorCatalogs, CoreDescriptorCatalogs)
    assert "source_files" not in CoreDescriptorCatalogs.__dataclass_fields__
    catalogs = DescriptorCatalogs.empty()
    assert isinstance(catalogs.nodes, CoreNodeCatalog)
    assert catalogs.source_files == ()


def test_registration_provenance_still_points_to_caller() -> None:
    from vibeflow.targets.python.project.node import NodeContract, NodeInfo
    from vibeflow.targets.python.project.registry import NodeRegistry

    class ExampleNode:
        NODE_INFO = NodeInfo(
            "test.provenance",
            "Provenance",
            "test",
            "Captures registration provenance.",
            "1",
            "process",
        )
        CONTRACT = NodeContract()

        def run_pure(self, inputs, params):
            return {}

    registry = NodeRegistry()
    expected_line = sys._getframe().f_lineno + 1
    registry.register(
        "test.provenance",
        ExampleNode,
        config_schema={},
        config_defaults={},
    )
    info = registry.registration_info()[0]
    assert Path(info.path).resolve() == Path(__file__).resolve()
    assert info.function == "test_registration_provenance_still_points_to_caller"
    assert info.line == expected_line


class _CompilerPluginRegistry:
    def __init__(self, *plugins: object) -> None:
        self._plugins = plugins

    def compiler_plugins(self) -> tuple[object, ...]:
        return self._plugins


def test_compiler_plugin_hooks_keep_declared_order() -> None:
    from vibeflow.core.flow import GraphConfig
    from vibeflow.targets.python.project.compiler import GraphCompiler

    events: list[str] = []

    class Hook:
        def __init__(self, name: str) -> None:
            self.name = name

        def before_compile(self, graph) -> None:
            events.append(f"{self.name}.before")

        def after_compile(self, graph, compiled) -> None:
            assert compiled.order == ()
            events.append(f"{self.name}.after")

    GraphCompiler().compile(
        GraphConfig(nodes=()),
        plugin_registry=_CompilerPluginRegistry(Hook("a"), Hook("b")),
    )
    assert events == ["a.before", "b.before", "a.after", "b.after"]


def test_compiler_plugin_failures_remain_fail_fast() -> None:
    from vibeflow.targets.python.project.compiler import GraphCompileError
    from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec
    from vibeflow.targets.python.project.compiler import GraphCompiler

    events: list[str] = []

    class Hook:
        name = "hook"

        def before_compile(self, graph) -> None:
            events.append("before")

        def after_compile(self, graph, compiled) -> None:
            events.append("after")

    cyclic = GraphConfig(
        nodes=(NodeSpec("a", "a"), NodeSpec("b", "b")),
        edges=(EdgeSpec("a", "b"), EdgeSpec("b", "a")),
    )
    with pytest.raises(GraphCompileError, match="CYCLE"):
        GraphCompiler().compile(
            cyclic,
            plugin_registry=_CompilerPluginRegistry(Hook()),
        )
    assert events == ["before"]

    class FailingHook(Hook):
        name = "failing"

        def before_compile(self, graph) -> None:
            events.append("failing.before")
            raise RuntimeError("stop")

    events.clear()
    with pytest.raises(GraphCompileError, match="before_compile failed"):
        GraphCompiler().compile(
            GraphConfig(nodes=()),
            plugin_registry=_CompilerPluginRegistry(FailingHook(), Hook()),
        )
    assert events == ["failing.before"]
