from tests.unit.strict_support import *


class RouteNode:
    NODE_INFO = NodeInfo(
        type_key="test.route",
        display_name="Route",
        category="test",
        description="Routes the next step.",
        version="0.1.0",
        flow_kind="decision",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("flow.route",),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"flow.route": ("branch route",)},
        output_schema={"flow.route": {"type": "string", "enum": ["again", "done"]}},
        examples=({"inputs": {"value.out": 1}, "params": {}, "outputs": {"flow.route": "done"}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


def test_compiler_merges_duplicate_explicit_and_data_edges_with_when() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "edges": [
                    {"from": "add", "to": "copy", "when": "flow.route == 'again'"},
                ],
            }
        }
    )

    compiled = GraphCompiler().compile(graph)

    assert [edge.pair for edge in compiled.effective_edges] == [("add", "copy")]
    assert compiled.effective_edges[0].when == "flow.route == 'again'"


def test_config_rejects_removed_loop_registration() -> None:
    with pytest.raises(GraphConfigError, match="pipeline.loops is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}],
                    "loops": [{"name": "old", "edges": [["seed", "seed"]], "max_iterations": 2}],
                }
            }
        )


def test_compiler_rejects_cycle_without_router() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                        {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "edges": [{"from": "add", "to": "copy"}, {"from": "copy", "to": "add"}],
            }
        }
    )

    with pytest.raises(GraphCompileError, match="cycle requires decision"):
        GraphCompiler().compile(graph, registry=_registry())


def test_compiler_allows_cycle_with_decision_router() -> None:
    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "route", "type": "test.route", "requires": ["value.out"], "provides": ["flow.route"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "edges": [
                    {"from": "add", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "add"},
                ],
            }
        }
    )

    compiled = GraphCompiler().compile(graph, registry=registry)

    assert ("copy", "add") in [edge.pair for edge in compiled.effective_edges]


def test_compiler_rejects_unconditional_edge_from_decision() -> None:
    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "route", "type": "test.route", "requires": ["value.out"], "provides": ["flow.route"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "edges": [{"from": "route", "to": "copy"}],
            }
        }
    )

    with pytest.raises(GraphCompileError, match="GRAPH.DECISION.MISSING_EDGE_CONDITION"):
        GraphCompiler().compile(graph, registry=registry)


def test_compiled_payload_uses_registry_flow_kind() -> None:
    from topology_kernel.mermaid import compiled_graph_payload

    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "route", "type": "test.route", "requires": ["value.out"], "provides": ["flow.route"]},
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph, registry=registry)

    assert compiled_graph_payload(graph, compiled)["nodes"][1]["flow_kind"] == "decision"
    assert 'route@{ shape: diam, label: "route' in export_mermaid(graph, compiled=compiled)


def test_planned_nodes_compile_without_registry_and_render_as_architecture() -> None:
    from topology_kernel.mermaid import compiled_graph_payload

    graph = parse_graph_config(
        {
            "nodesets": [
                {"name": "a", "status": "planned"},
                {"name": "b", "status": "planned"},
                {"name": "c", "status": "planned"},
            ],
            "pipeline": {
                "nodes": [
                    {"name": "a", "type": "nodeset.a", "status": "planned", "flow_kind": "predefined"},
                    {"name": "b", "type": "nodeset.b", "status": "planned", "flow_kind": "predefined"},
                    {"name": "c", "type": "nodeset.c", "status": "planned", "flow_kind": "predefined"},
                ],
                "edges": [["a", "b"], ["b", "c"]],
            },
        }
    )
    compiled = GraphCompiler().compile(graph)

    payload = compiled_graph_payload(graph, compiled)
    text = export_mermaid(graph, compiled=compiled)
    assert payload["nodes"][0]["status"] == "planned"
    assert payload["nodes"][0]["flow_kind"] == "predefined"
    assert 'a@{ shape: fr-rect, label: "a' in text
    assert "planned" in text
    assert ":::plannedNode" in text


def test_implemented_node_cannot_declare_config_flow_kind() -> None:
    with pytest.raises(GraphConfigError, match="flow_kind is only allowed for planned"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "seed", "type": "test.seed", "flow_kind": "process", "provides": ["value.in"]},
                    ]
                }
            }
        )
