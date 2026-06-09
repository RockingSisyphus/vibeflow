from __future__ import annotations

import pytest

from topology_kernel import (
    GraphCompileError,
    GraphCompiler,
    NodeContract,
    NodeInfo,
    NodeRegistry,
    PipelineRuntime,
    export_mermaid,
    parse_graph_config,
    validate_graph_health,
)
from topology_kernel.purity import PurityPolicy, validate_node_class


class SeedNode:
    NODE_INFO = NodeInfo(
        type_key="test.seed",
        display_name="Seed",
        category="test",
        description="Produces a seed value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(provides=("value.seed",))

    def run_pure(self, inputs, params):
        return {params.get("output_key", "value.seed"): params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="test.add",
        display_name="Add",
        category="test",
        description="Adds delta to input.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(requires=("value.in",), provides=("value.out",))

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"] + params.get("delta", 1)}


class CopyNode:
    NODE_INFO = NodeInfo(
        type_key="test.copy",
        display_name="Copy",
        category="test",
        description="Copies a value.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(requires=("value.out",), provides=("value.in",))

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


class BadIoNode:
    NODE_INFO = NodeInfo(
        type_key="test.bad_io",
        display_name="Bad IO",
        category="test",
        description="Illegally performs IO.",
        version="0.1.0",
    )
    CONTRACT = NodeContract(provides=("value.out",))

    def run_pure(self, inputs, params):
        with open("forbidden.txt", "w", encoding="utf-8") as handle:
            handle.write("bad")
        return {"value.out": 1}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("test.seed", SeedNode)
    registry.register("test.add", AddNode)
    registry.register("test.copy", CopyNode)
    return registry


def test_pure_node_metadata_and_static_check() -> None:
    assert validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1000)) == []
    violations = validate_node_class(BadIoNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "banned_call" for item in violations)


def test_source_size_limit_is_enforced() -> None:
    violations = validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1))
    assert any(item.code == "source_too_large" for item in violations)


def test_requires_provides_data_edges_are_inferred_and_runtime_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"], "output_key": "value.in", "value": 4},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                ],
                "edges": [],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("seed", "add") in [edge.pair for edge in compiled.data_edges]
    context = PipelineRuntime(graph, registry=_registry()).run()
    assert context.get("value.out") == 7


def test_undeclared_cycle_is_rejected() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 3},
                    {"from": "copy", "to": "add", "max_executions": 3},
                ],
            }
        }
    )
    with pytest.raises(GraphCompileError):
        GraphCompiler().compile(graph)


def test_declared_bounded_loop_compiles_and_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 1},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.in"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "max_executions": 4},
                    {"from": "copy", "to": "add", "max_executions": 3, "loop": "counter_loop"},
                ],
                "loops": [
                    {
                        "name": "counter_loop",
                        "edges": [["copy", "add"]],
                        "nodes": ["add", "copy"],
                        "max_iterations": 3,
                    }
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("copy", "add") in [edge.pair for edge in compiled.loop_edges]
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 0}})
    assert context.get("value.in") == 4


def test_nodeset_can_be_used_as_a_node() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                {
                    "name": "math.add_one",
                    "display_name": "Add One",
                    "category": "math",
                    "description": "Composite add-one flow.",
                    "version": "0.1.0",
                    "requires": ["value.in"],
                    "provides": ["value.out"],
                    "exports": ["value.out"],
                    "pipeline": {
                        "inputs": ["value.in"],
                        "nodes": [
                            {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 1}
                        ],
                    },
                }
            ],
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {
                        "name": "composite",
                        "type": "nodeset.math.add_one",
                        "requires": ["value.in"],
                        "provides": ["value.out"],
                    }
                ],
            },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value": {"in": 2}})
    assert context.get("value.out") == 3


def test_health_report_and_mermaid_export() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "ok"
    mermaid = export_mermaid(graph)
    assert "flowchart TD" in mermaid
    assert "seed -->|max=1| add" in mermaid
