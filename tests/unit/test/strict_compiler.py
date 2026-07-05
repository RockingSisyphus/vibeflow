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
        examples=({"inputs": {"value.out": 1}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


def test_compiler_merges_duplicate_explicit_and_data_edges_with_when() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("copy", "test.copy", "Copies the output value.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy")]),
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


def test_config_node_visual_metadata_and_style_are_not_runtime_params() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {
                        "name": "seed",
                        "type": "test.seed",
                        "display_name": "Readable Seed",
                        "category": "demo",
                        "version": "2.0.0",
                        "description": "Produces a seed value for the visual metadata test.",
                        "style": {"fill": "#123ABC", "stroke": "#456DEF", "text": "#654321"},
                        "similar_to": {
                            "node": "base_seed",
                            "relationship": "variant",
                            "reason": "Exercises metadata isolation for duplicate-like nodes.",
                        },
                        "config": {
                            "display_name": "runtime display parameter",
                            "description": "runtime description parameter",
                            "style": "runtime style parameter",
                            "similar_to": "runtime similarity parameter",
                        },
                        "provides": [PROV_SPEC("value.in")],
                    },
                    _node_call("base_seed", "test.seed", "Reference node for similar_to.", provides=[PROV_SPEC("base.value")]),
                ]
            }
        }
    )

    node = graph.nodes[0]

    assert node.metadata.display_name == "Readable Seed"
    assert node.metadata.category == "demo"
    assert node.metadata.version == "2.0.0"
    assert node.metadata.description == "Produces a seed value for the visual metadata test."
    assert node.style.to_dict() == {"fill": "#123abc", "stroke": "#456def", "text": "#654321"}
    assert node.similar_to.to_dict() == {
        "node": "base_seed",
        "relationship": "variant",
        "reason": "Exercises metadata isolation for duplicate-like nodes.",
    }
    assert node.params == {
        "display_name": "runtime display parameter",
        "description": "runtime description parameter",
        "style": "runtime style parameter",
        "similar_to": "runtime similarity parameter",
    }


def test_mermaid_renders_sectioned_labels_default_node_and_custom_style() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces a seed value with a long readable description that should wrap deterministically in the SVG label.",
                        display_name="Readable Seed",
                        category="demo",
                        version="2.0.0",
                        style={"fill": "#123abc", "stroke": "#456def", "text": "#654321"},
                        provides=[PROV_SPEC("value.in")],
                    )
                ]
            }
        }
    )

    text = export_mermaid(graph)

    assert "classDef defaultNode fill:#ECECFF,stroke:#9370DB,color:#333333;" in text
    assert 'seed@{ shape: rect, label: "Readable Seed\\n\\nid: seed\\ntype: test.seed' in text
    assert "\\n-- meta --\\ncategory: demo\\nversion: 2.0.0\\ndesc: Produces a seed value with a long readable" in text
    assert "\\n      description that should wrap deterministically in\\n      the SVG label." in text
    assert "requires:" not in text
    assert "provides:" not in text
    assert "class seed defaultNode;" in text
    assert "style seed fill:#123abc,stroke:#456def,color:#654321;" in text


def test_mermaid_renders_contracts_on_edges_and_hides_them_when_requested() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                ],
                "edges": [{"from": "seed", "to": "add", "when": "flow.route == 'again'"}],
            }
        }
    )

    text = export_mermaid(graph)
    hidden = export_mermaid(graph, show_contract=False)

    assert "seed -->|when: flow.route == 'again'\\ndata: value.in| add" in text
    assert "requires:" not in text
    assert "provides:" not in text
    assert "seed -->|flow.route == 'again'| add" in hidden


def test_mermaid_edge_contract_labels_summarize_provider_key_type_mapping() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "producer",
                        "test.seed",
                        "Produces several values.",
                        provides=[
                            PROV_SPEC("value.copy", "value.in"),
                            PROV_SPEC("other.copy", "other.in"),
                            PROV_SPEC("extra.copy", "extra.in"),
                        ],
                    ),
                    _node_call(
                        "consumer",
                        "test.add",
                        "Consumes several values.",
                        requires=[REQ_SPEC("value.in"), REQ_SPEC("other.in"), REQ_SPEC("extra.in")],
                    ),
                ],
                "edges": [{"from": "producer", "to": "consumer"}],
            }
        }
    )

    text = export_mermaid(graph)

    assert "producer -->|value.copy -> value.in, other.copy -> other.in, +1 more| consumer" in text


def test_config_schema_rejects_reserved_and_invalid_node_style_colors() -> None:
    reserved = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces value.in.",
                        style={"fill": "#ECECFF"},
                        provides=[PROV_SPEC("value.in")],
                    )
                ]
            }
        }
    )
    invalid = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces value.in.",
                        style={"stroke": "red"},
                        provides=[PROV_SPEC("value.in")],
                    )
                ]
            }
        }
    )

    assert any(finding.rule_id == "CONFIG.SCHEMA.NODE_STYLE_RESERVED_COLOR" for finding in reserved)
    assert any(finding.rule_id == "CONFIG.SCHEMA.NODE_STYLE_COLOR" for finding in invalid)


def test_config_schema_rejects_invalid_node_similarity_metadata() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], similar_to={"node": "seed", "relationship": "variant", "reason": ""}),
                    _node_call("copy", "test.seed", "Produces copied value.", provides=[PROV_SPEC("value.copy")], similar_to={"node": "missing", "relationship": "clone", "reason": "bad target"}),
                ]
            }
        }
    )
    messages = [finding.message for finding in findings if finding.rule_id == "CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID"]

    assert any("cannot reference itself" in message for message in messages)
    assert any("references unknown node" in message for message in messages)
    assert any("relationship must be variant or copy" in message for message in messages)
    assert any("reason must be a non-empty string" in message for message in messages)
    with pytest.raises(GraphConfigError, match="CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID"):
        parse_graph_config({"pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.", similar_to={"node": "seed", "relationship": "copy", "reason": "self"})]}})


def test_graph_health_warns_when_config_node_lacks_visual_metadata() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the metadata warning fixture."),
                    {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    _node_call("end", "test.in_end", "Consumes value.in at the end.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "seed", "end"),
            }
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {warning.rule_id for warning in report.warnings}

    assert report.status == "CONCERNS"
    assert "GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME" in rule_ids
    assert "GRAPH.SMELL.MISSING_NODE_DESCRIPTION" in rule_ids


def test_config_rejects_removed_loop_registration() -> None:
    with pytest.raises(GraphConfigError, match="pipeline.loops is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])],
                    "loops": [{"name": "old", "edges": [["seed", "seed"]], "max_iterations": 2}],
                }
            }
        )


def test_compiler_rejects_cycle_without_router() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("copy", "test.copy", "Copies the output value.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy")]),
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
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Routes the cycle branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.copy", "Copies the output value.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy")]),
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


def test_graph_health_reports_decision_cycle_without_exit() -> None:
    from tests.unit.strict_support_runtime_nodes import RouteNode as RuntimeRouteNode

    registry = _registry()
    register_node(registry, "test.route", RuntimeRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Routes the cycle branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.seed", "Recreates value.in for the loop.", provides=[PROV_SPEC("value.in")]),
                    _node_call("end", "test.start", "Unreachable exit placeholder."),
                ],
                "edges": [
                    {"from": "add", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "add"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert any(error.rule_id == "GRAPH.CYCLE.MISSING_DECISION_EXIT" for error in report.errors)


def test_compiler_rejects_unconditional_edge_from_decision() -> None:
    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Routes the branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.copy", "Copies the output value.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy")]),
                ],
                "edges": [{"from": "route", "to": "copy"}],
            }
        }
    )

    with pytest.raises(GraphCompileError, match="GRAPH.DECISION.MISSING_EDGE_CONDITION"):
        GraphCompiler().compile(graph, registry=registry)


def test_compiled_payload_uses_registry_flow_kind() -> None:
    from vibeflow.mermaid import compiled_graph_payload

    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("add", "test.add", "Adds the incoming value.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Routes the branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph, registry=registry)

    assert compiled_graph_payload(graph, compiled)["nodes"][1]["flow_kind"] == "decision"
    assert 'route@{ shape: diam, label: "Route\\n\\nid: route\\ntype: test.route' in export_mermaid(graph, compiled=compiled)


def test_planned_nodes_compile_without_registry_and_render_as_architecture() -> None:
    from vibeflow.mermaid import compiled_graph_payload

    graph = parse_graph_config(
        {
            "nodesets": [
                {"name": "a", "status": "planned"},
                {"name": "b", "status": "planned"},
                {"name": "c", "status": "planned"},
            ],
            "pipeline": {
                "nodes": [
                    _node_call("a", "nodeset.a", "Planned composite a.", status="planned", flow_kind="predefined"),
                    _node_call("b", "nodeset.b", "Planned composite b.", status="planned", flow_kind="predefined"),
                    _node_call("c", "nodeset.c", "Planned composite c.", status="planned", flow_kind="predefined"),
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
    assert 'a@{ shape: fr-rect, label: "A\\n\\nid: a\\ntype: nodeset.a' in text
    assert "-- status --" in text
    assert "planned" in text
    assert "class a plannedNode;" in text


def test_implemented_node_cannot_declare_config_flow_kind() -> None:
    with pytest.raises(GraphConfigError, match="flow_kind is only allowed for planned"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("seed", "test.seed", "Produces value.in.", flow_kind="process", provides=[PROV_SPEC("value.in")]),
                    ]
                }
            }
        )
