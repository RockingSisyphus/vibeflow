from tests.unit.strict_support import *

import time


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


def test_config_node_join_policy_and_loop_are_not_runtime_params() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "sum.step",
                    requires=["total.current"],
                    provides=["total.next"],
                    exports=["total.next"],
                    pipeline={
                        "inputs": [PROV_SPEC("total.current")],
                        "nodes": [_node_call("start", "test.start", "Starts loop body.")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {
                        "name": "loop",
                        "type": "vibeflow.loop.while",
                        "display_name": "Loop",
                        "description": "Runs a body nodeset.",
                        "requires": [REQ_SPEC("total.current")],
                        "provides": [PROV_SPEC("total.final")],
                        "join_policy": "all",
                        "loop": {
                            "body": "sum.step",
                            "stop_after": 1,
                            "carry": [{"from": "total.current", "as": "total.current", "update": "total.next"}],
                            "outputs": [{"from": "total.next", "as": "total.final"}],
                        },
                        "config": {"join_policy": "runtime", "loop": "runtime"},
                    }
                ]
            },
        }
    )

    node = graph.nodes[0]
    assert node.join_policy == "all"
    assert node.loop.to_dict()["body"] == "sum.step"
    assert node.params == {"join_policy": "runtime", "loop": "runtime"}


def test_nodeset_parser_uses_shared_symbol_table_for_forward_references_and_large_chains() -> None:
    nodesets = []
    for index in range(20):
        if index == 19:
            nodes = [_node_call("seed", "test.seed", "Produces the terminal chain value.", provides=[PROV_SPEC("value.out")])]
        else:
            nodes = [
                _node_call(
                    "next",
                    f"nodeset.perf.ns{index + 1}",
                    "Calls a nodeset declared later in the same config.",
                    provides=[PROV_SPEC("value.out")],
                )
            ]
        nodesets.append(
            _nodeset_config(
                f"perf.ns{index}",
                provides=["value.out"],
                exports=["value.out"],
                pipeline={"nodes": nodes},
            )
        )

    started = time.perf_counter()
    graph = parse_graph_config(
        {
            "nodesets": nodesets,
            "pipeline": {
                "nodes": [
                    _node_call("top", "nodeset.perf.ns0", "Calls the first chain nodeset.", provides=[PROV_SPEC("value.out")]),
                ]
            },
        }
    )

    assert time.perf_counter() - started < 1.0
    assert len(graph.nodesets) == 20
    assert graph.nodesets["perf.ns19"].graph.nodesets is graph.nodesets
    assert graph.nodesets["perf.ns0"].graph.nodesets["perf.ns19"] is graph.nodesets["perf.ns19"]


def test_parse_rejects_unknown_nodeset_call_with_reference_detail() -> None:
    with pytest.raises(GraphConfigError, match="unknown nested nodeset: missing.body"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("missing", "nodeset.missing.body", "References a missing composite.", provides=[PROV_SPEC("value.out")]),
                    ]
                }
            }
        )


def test_config_parse_trace_reports_nodeset_timing(monkeypatch, capsys) -> None:
    monkeypatch.setenv("VIBEFLOW_CONFIG_TRACE", "1")

    parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "trace.body",
                    pipeline={"nodes": [_node_call("seed", "test.seed", "Produces trace output.", provides=[PROV_SPEC("value.out")])]},
                )
            ],
            "pipeline": {
                "nodes": [_node_call("flow", "nodeset.trace.body", "Calls trace body.", provides=[PROV_SPEC("value.out")])]
            },
        }
    )

    err = capsys.readouterr().err
    assert "[vibeflow config] parsed nodeset name=trace.body" in err
    assert "parsed graph nodes=1 nodesets=1" in err


def test_config_schema_rejects_invalid_join_policy_and_loop_shape() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call("bad_join", "test.seed", "Bad join.", join_policy="sometimes", provides=[PROV_SPEC("value.in")]),
                    _node_call("bad_loop", "vibeflow.loop.while", "Bad loop.", loop={"body": "", "items": {"from": "", "as": ""}}),
                ]
            }
        }
    )

    assert {finding.rule_id for finding in findings} >= {"CONFIG.SCHEMA.NODE_JOIN_POLICY", "CONFIG.SCHEMA.NODE_LOOP_INVALID"}


def test_parse_rejects_removed_for_each_loop_type_and_old_loop_fields() -> None:
    with pytest.raises(GraphConfigError, match="only allowed on VibeFlow loop nodes"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call(
                            "loop",
                            "vibeflow.loop.for_each",
                            "Old for-each loop syntax is removed.",
                            loop={"body": "body", "items": {"from": "items", "as": "item"}},
                        )
                    ]
                }
            }
        )
    with pytest.raises(GraphConfigError, match="unsupported loop keys"):
        parse_graph_config(
            {
                "nodesets": [_nodeset_config("body", pipeline={"nodes": [_node_call("start", "test.start", "Starts body.")]})],
                "pipeline": {
                    "nodes": [
                        _node_call(
                            "loop",
                            "vibeflow.loop.while",
                            "Old loop fields are removed.",
                            loop={"body": "body", "items": {"from": "items", "as": "item"}, "epochs": 2},
                        )
                    ]
                },
            }
        )


def test_parse_rejects_invalid_while_loop_stop_conditions() -> None:
    body = _nodeset_config("body", pipeline={"nodes": [_node_call("start", "test.start", "Starts body.")]})
    for loop, match in (
        ({"body": "body"}, "exactly one"),
        ({"body": "body", "stop_after": 2, "stop_when": {"from": "loop.done"}}, "exactly one"),
        ({"body": "body", "max_iterations": 1, "stop_after": 2}, "<= max_iterations"),
        ({"body": "body", "stop_when": {"from": "loop.done", "equals": "true"}}, "equals must be a boolean"),
    ):
        with pytest.raises(GraphConfigError, match=match):
            parse_graph_config(
                {
                    "nodesets": [body],
                    "pipeline": {
                        "nodes": [
                            _node_call("loop", "vibeflow.loop.while", "Invalid stop condition.", loop=loop),
                        ]
                    },
                }
            )


def test_parse_rejects_loop_body_unknown_nodeset() -> None:
    with pytest.raises(GraphConfigError, match="unknown nodeset"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call(
                            "loop",
                            "vibeflow.loop.while",
                            "References a missing loop body.",
                            requires=[REQ_SPEC("value.in")],
                            provides=[PROV_SPEC("items.out")],
                            loop={"body": "missing.body", "stop_after": 1},
                        )
                    ]
                }
            }
        )


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
    assert "\\n---------- meta ----------\\ncategory: demo\\nversion: 2.0.0\\ndesc: Produces a seed value with a long readable" in text
    assert "\\n      description that should wrap deterministically in\\n      the SVG label." in text
    assert "requires:" not in text
    assert "provides:" not in text
    assert "class seed defaultNode;" in text
    assert "style seed fill:#123abc,stroke:#456def,color:#654321;" in text


def test_mermaid_custom_style_overrides_health_class_color() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call(
                        "seed",
                        "test.seed",
                        "Produces a styled seed with a warning class.",
                        style={"fill": "#123abc", "stroke": "#456def", "text": "#654321"},
                        provides=[PROV_SPEC("value.in")],
                    )
                ]
            }
        }
    )
    report = HealthReport(
        status="CONCERNS",
        warnings=(
            HealthFinding(
                rule_id="TEST.WARNING",
                severity="warning",
                object_type="node",
                object_id="seed",
                message="fixture warning",
            ),
        ),
    )

    text = export_mermaid(graph, health_report=report)

    assert "class seed healthWarning;" in text
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


def test_mermaid_renders_while_loop_shape_class_and_stop_condition() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [_nodeset_config("loop.body", pipeline={"nodes": [_node_call("start", "test.start", "Starts loop body.")]})],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts loop render fixture."),
                    _node_call(
                        "loop",
                        "vibeflow.loop.while",
                        "Renders a structured while loop.",
                        display_name="Loop",
                        provides=[PROV_SPEC("loop.iterations")],
                        style={"fill": "#123abc", "stroke": "#456def", "text": "#654321"},
                        loop={
                            "body": "loop.body",
                            "max_iterations": 5,
                            "stop_after": 2,
                            "outputs": [{"from": "loop.iterations", "as": "loop.iterations"}],
                        },
                    ),
                    _node_call("end", "test.start", "Ends loop render fixture."),
                ],
                "edges": _edge_chain("start", "loop", "end"),
            },
        }
    )

    text = export_mermaid(graph)

    assert 'loop@{ shape: trap-b, label: "Loop' in text
    assert "class loop loopNode;" in text
    assert "classDef loopNode" in text
    assert "style loop fill:#123abc,stroke:#456def,color:#654321;" in text
    assert "stop: stop_after: 2" in text


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

    with pytest.raises(GraphCompileError, match="explicit flow cycle is forbidden") as exc_info:
        GraphCompiler().compile(graph, registry=_registry())
    assert exc_info.value.rule_id == "GRAPH.CYCLE.FORBIDDEN"
    assert exc_info.value.details["members"] == ["add", "copy"]


def test_compiler_rejects_cycle_with_decision_router() -> None:
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
                    _node_call("end", "test.start", "Exits the old decision cycle."),
                ],
                "edges": [
                    {"from": "add", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                    {"from": "copy", "to": "add"},
                ],
            }
        }
    )

    with pytest.raises(GraphCompileError) as exc_info:
        GraphCompiler().compile(graph, registry=registry)
    assert exc_info.value.rule_id == "GRAPH.CYCLE.FORBIDDEN"
    assert exc_info.value.details["edges"] == ["add->route", "copy->add", "route->copy"]


def test_graph_health_reports_forbidden_cycle() -> None:
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

    assert any(error.rule_id == "GRAPH.CYCLE.FORBIDDEN" for error in report.errors)
    finding = next(error for error in report.errors if error.rule_id == "GRAPH.CYCLE.FORBIDDEN")
    assert finding.details["members"] == ["add", "copy", "route"]


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
    assert "---------- status ----------" in text
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
