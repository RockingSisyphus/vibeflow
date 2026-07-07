from tests.unit.strict_support import *

from vibeflow.policy import EffectivePolicy

def test_architecture_smells_warn_for_mismatched_metadata_and_unstable_keys(tmp_path, capsys) -> None:
    info = VALID_NODE_INFO.replace('description="Demo node."', 'description="Calculates invoice total."')
    contract = """
    CONTRACT = NodeContract(
        provides=(PROV("Tmp Key"),),
        output_semantics={"Tmp Key": ("scratch debug value",)},
        output_schema={"Tmp Key": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )
""".rstrip()
    source = _valid_node_source(info=info, contract=contract, run_body='        return {"Tmp Key": 1}')
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 0
    warnings = {warning["details"].get("legacy_code") for warning in payload["health"]["warnings"]}
    assert "responsibility_mismatch" in warnings
    assert "temporary_key" in warnings
    assert "confusing_key_name" in warnings

def test_graph_health_reports_node_metrics_duplicate_logic_and_confusing_node_names() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.duplicate_one", DuplicateOneNode)
    register_node(registry, "test.duplicate_two", DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("DuplicateOne", "test.duplicate_one", "Produces the first duplicate fixture value.", provides=[PROV_SPEC("dup.one")]),
                    _node_call("duplicate_two", "test.duplicate_two", "Produces the second duplicate fixture value.", provides=[PROV_SPEC("dup.two")]),
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    assert payload["info"]["node_metrics"]["DuplicateOne"]["function_count"] == 1
    rule_ids = {warning["rule_id"] for warning in payload["warnings"]}
    assert "GRAPH.SMELL.CONFUSING_NODE_NAME" in rule_ids
    assert "GRAPH.SMELL.DUPLICATE_LOGIC" in rule_ids
    duplicate = next(warning for warning in payload["warnings"] if warning["rule_id"] == "GRAPH.SMELL.DUPLICATE_LOGIC")
    assert duplicate["details"]["nodes"] == ["DuplicateOne", "duplicate_two"]
    assert duplicate["details"]["node_types"] == {"DuplicateOne": "test.duplicate_one", "duplicate_two": "test.duplicate_two"}
    assert duplicate["details"]["fingerprint"]
    assert duplicate["details"]["duplicate_group"] == ["DuplicateOne", "duplicate_two"]
    assert "similar_to" in duplicate["details"]["suppression_hint"]
    from vibeflow.cli.reports import format_finding_text

    text = format_finding_text(next(warning for warning in report.warnings if warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC"))
    assert "\n  details:" in text
    assert '"nodes":["DuplicateOne","duplicate_two"]' in text


def test_graph_health_suppresses_declared_similar_duplicate_logic_pairs() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.duplicate_one", DuplicateOneNode)
    register_node(registry, "test.duplicate_two", DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.duplicate_one", "Produces the base duplicate fixture value.", provides=[PROV_SPEC("dup.base")]),
                    _node_call(
                        "variant",
                        "test.duplicate_two",
                        "Produces an intentional variant duplicate fixture value.",
                        provides=[PROV_SPEC("dup.variant")],
                        similar_to={"node": "base", "relationship": "variant", "reason": "Same pure shape, different contract semantics."},
                    ),
                ]
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert "GRAPH.SMELL.DUPLICATE_LOGIC" not in {warning.rule_id for warning in report.warnings}


def test_graph_health_flow_and_data_findings_include_owner_and_provider_context() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "inner.flow",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("start", "test.start", "Starts the nested flow."),
                            _node_call("add", "test.add", "Adds a missing nested input.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                            _node_call("end", "test.out_end", "Ends after nested value.out.", requires=[REQ_SPEC("value.out")]),
                        ],
                        "edges": [{"from": "start", "to": "end"}],
                    },
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the top-level flow."),
                    _node_call(
                        "composite",
                        "inner.flow",
                        "Runs the nested flow.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                    ),
                    _node_call("end", "test.out_end", "Ends after composite output.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    findings = [*payload["errors"], *payload["warnings"]]
    orphan = next(finding for finding in findings if finding["rule_id"] == "GRAPH.FLOW.ORPHAN_NODE")
    missing = next(finding for finding in findings if finding["rule_id"] == "GRAPH.DATA.MISSING_DIRECT_PROVIDER")
    unconsumed = next(finding for finding in findings if finding["rule_id"] == "GRAPH.DATA.UNCONSUMED_PROVIDER")

    assert orphan["details"]["owner"] == "nodeset:inner.flow"
    assert orphan["details"]["node"] == "add"
    assert missing["details"]["owner"] == "nodeset:inner.flow"
    assert missing["details"]["required_type"] == "value.in"
    assert missing["details"]["direct_sources"] == []
    assert missing["details"]["available_provider_types"] == []
    assert unconsumed["details"]["owner"] == "nodeset:inner.flow"
    assert unconsumed["details"]["provider_key"] == "value.out"
    assert unconsumed["details"]["downstream_nodes"] == []


def test_graph_health_checks_each_nested_nodeset_definition_once() -> None:
    graph = _nested_bad_leaf_graph(depth=6)

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    findings = [*report.errors, *report.warnings]

    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:ns0", node="bad", required_type="value.in")) == 1
    assert len(_findings(findings, "GRAPH.DATA.UNCONSUMED_PROVIDER", owner="nodeset:ns0", node="bad", provider_key="value.out")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.UNREACHABLE_FROM_START", owner="nodeset:ns0", node="bad")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.CANNOT_REACH_END", owner="nodeset:ns0", node="bad")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.ORPHAN_NODE", owner="nodeset:ns0", node="bad")) == 1
    assert len(_findings(findings, "GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME", owner="nodeset:ns0", object_id="bad")) == 1
    assert len(_findings(findings, "GRAPH.SMELL.MISSING_NODE_DESCRIPTION", owner="nodeset:ns0", object_id="bad")) == 1


def test_graph_health_keeps_same_node_problem_separate_by_owner() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _bad_leaf_nodeset("left.leaf"),
                _bad_leaf_nodeset("right.leaf"),
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the owner aggregation fixture."),
                    _node_call("left", "left.leaf", "Calls the left leaf.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("left.out")]),
                    _node_call("right", "right.leaf", "Calls the right leaf.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("right.out")]),
                    _node_call("end", "test.start", "Ends the owner aggregation fixture."),
                ],
                "edges": [{"from": "start", "to": "left"}, {"from": "start", "to": "right"}, {"from": "left", "to": "end"}, {"from": "right", "to": "end"}],
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    findings = [*report.errors, *report.warnings]

    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", node="bad", required_type="value.in")) == 2
    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:left.leaf", node="bad", required_type="value.in")) == 1
    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:right.leaf", node="bad", required_type="value.in")) == 1


def test_nodeset_override_path_errors_are_not_repeated_by_nested_definition_expansion() -> None:
    nodesets = [_bad_leaf_nodeset("ns0")]
    first_wrapper = _wrapper_nodeset("ns1", "ns0")
    first_wrapper["pipeline"]["nodes"][1]["node_configs"] = {"missing.path": {"delta": 1}}
    nodesets.append(first_wrapper)
    for index in range(2, 6):
        nodesets.append(_wrapper_nodeset(f"ns{index}", f"ns{index - 1}"))
    graph = parse_graph_config(
        {
            "nodesets": nodesets,
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the override aggregation fixture."),
                    _node_call("top", "ns5", "Calls the deepest wrapper.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Ends the override aggregation fixture.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "top", "end"),
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    errors = [error for error in report.errors if error.rule_id == "NODESET.CONFIG.UNKNOWN_NODE"]

    assert len(errors) == 1
    assert errors[0].object_id == "call"
    assert errors[0].details["nodeset"] == "ns0"
    assert errors[0].details["path"] == "missing.path"


def test_node_config_override_path_can_pass_through_loop_body() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.add_body",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the loop override health fixture."),
                    _node_call(
                        "loop_call",
                        "vibeflow.loop.while",
                        "Runs an add body with a node config override.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                        node_configs={"add": {"delta": 5}},
                        loop={
                            "body": "loop.add_body",
                            "max_iterations": 3,
                            "stop_after": 1,
                            "carry": [{"from": "value.in", "as": "value.in", "update": "value.out"}],
                            "outputs": [{"from": "value.out", "as": "value.out"}],
                        },
                    ),
                    _node_call("end", "test.out_end", "Ends after value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "loop_call", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {error.rule_id for error in report.errors}

    assert "NODESET.CONFIG.INVALID_PATH" not in rule_ids
    assert "NODESET.CONFIG.UNKNOWN_NODE" not in rule_ids
    assert "NODESET.CONFIG.INVALID" not in rule_ids


def test_node_config_override_path_still_rejects_traversing_plain_node() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "plain.body",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the invalid override fixture."),
                    _node_call(
                        "composite",
                        "plain.body",
                        "Calls a body with an invalid nested override path.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                        node_configs={"add.inner": {"delta": 5}},
                    ),
                    _node_call("end", "test.out_end", "Ends after value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    invalid = next(error for error in report.errors if error.rule_id == "NODESET.CONFIG.INVALID_PATH")

    assert invalid.object_id == "composite"
    assert invalid.details["path"] == "add.inner"
    assert invalid.details["node"] == "add"
    assert invalid.details["type_used"] == "test.add"
    assert invalid.details["composite_kind"] == "none"


def test_health_report_aggregates_duplicate_findings_but_not_different_direct_sources() -> None:
    class DuplicateFindingPlugin:
        name = "duplicate_finding"

        def validate_graph(self, graph, compiled):
            duplicate = HealthFinding(
                rule_id="PLUGIN.DUPLICATE",
                severity="warning",
                object_type="pipeline",
                object_id="pipeline",
                failure_layer="plugin",
                message="same plugin warning",
                suggested_fix_type="fix_config",
                details={"owner": "pipeline", "node": "seed"},
            )
            return [
                duplicate,
                duplicate,
                HealthFinding(
                    rule_id="GRAPH.DATA.MISSING_DIRECT_PROVIDER",
                    severity="error",
                    object_type="contract_key",
                    object_id="value.in",
                    failure_layer="topology",
                    message="simulated missing provider",
                    suggested_fix_type="fix_config",
                    details={"owner": "pipeline", "node": "join", "required_type": "value.in", "direct_sources": ["left"]},
                ),
                HealthFinding(
                    rule_id="GRAPH.DATA.MISSING_DIRECT_PROVIDER",
                    severity="error",
                    object_type="contract_key",
                    object_id="value.in",
                    failure_layer="topology",
                    message="simulated missing provider",
                    suggested_fix_type="fix_config",
                    details={"owner": "pipeline", "node": "join", "required_type": "value.in", "direct_sources": ["right"]},
                ),
            ]

    plugin_registry = PluginRegistry()
    plugin_registry.register(DuplicateFindingPlugin(), plugin_type="policy")
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})

    report = validate_graph_health(graph, registry=_registry(), plugin_registry=plugin_registry, purity_policy=PurityPolicy(max_source_lines=1000))
    duplicate = next(warning for warning in report.warnings if warning.rule_id == "PLUGIN.DUPLICATE")
    simulated_missing = [error for error in report.errors if error.rule_id == "GRAPH.DATA.MISSING_DIRECT_PROVIDER" and error.details.get("node") == "join"]

    assert duplicate.details["aggregated"] is True
    assert duplicate.details["occurrences"] == 2
    assert duplicate.details["suppressed_duplicates"] == 1
    assert len(simulated_missing) == 2

    from vibeflow.cli.reports import format_finding_text

    text = format_finding_text(duplicate)
    assert '"aggregated":true' in text
    assert '"occurrences":2' in text
    assert '"suppressed_duplicates":1' in text


def _nested_bad_leaf_graph(*, depth: int):
    nodesets = [_bad_leaf_nodeset("ns0")]
    for index in range(1, depth):
        nodesets.append(_wrapper_nodeset(f"ns{index}", f"ns{index - 1}"))
    return parse_graph_config(
        {
            "nodesets": nodesets,
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nested aggregation fixture."),
                    _node_call(
                        "top",
                        f"ns{depth - 1}",
                        "Calls the deepest wrapper.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                    ),
                    _node_call("end", "test.out_end", "Ends the nested aggregation fixture.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "top", "end"),
            },
        }
    )


def _bad_leaf_nodeset(name: str) -> dict:
    return _nodeset_config(
        name,
        requires=["value.in"],
        provides=["value.out"],
        exports=["value.out"],
        pipeline={
            "nodes": [
                _node_call("start", "test.start", "Starts the bad leaf."),
                {
                    "id": "bad",
                    "type_used": "test.add",
                    "requires": [REQ_SPEC("value.in")],
                    "provides": [PROV_SPEC("value.out")],
                },
                _node_call("end", "test.out_end", "Ends after value.out.", requires=[REQ_SPEC("value.out")]),
            ],
            "edges": [{"from": "start", "to": "end"}],
        },
    )


def _wrapper_nodeset(name: str, child: str) -> dict:
    return _nodeset_config(
        name,
        requires=["value.in"],
        provides=["value.out"],
        exports=["value.out"],
        pipeline={
            "inputs": [PROV_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", f"Starts wrapper {name}."),
                _node_call("call", f"{child}", f"Calls {child}.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                _node_call("end", "test.out_end", f"Ends wrapper {name}.", requires=[REQ_SPEC("value.out")]),
            ],
            "edges": _edge_chain("start", "call", "end"),
        },
    )


def _findings(findings, rule_id: str, **details):
    matches = [finding for finding in findings if finding.rule_id == rule_id]
    object_id = details.pop("object_id", None)
    if object_id is not None:
        matches = [finding for finding in matches if finding.object_id == object_id]
    for key, value in details.items():
        matches = [finding for finding in matches if finding.details.get(key) == value]
    return matches


def test_graph_health_suppresses_duplicate_logic_when_nodes_share_declared_base() -> None:
    registry = _registry()
    register_node(registry, "test.duplicate_one", DuplicateOneNode)
    register_node(registry, "test.duplicate_two", DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.seed", "Produces the shared base fixture value.", provides=[PROV_SPEC("value.in")]),
                    _node_call(
                        "left",
                        "test.duplicate_one",
                        "Produces the left duplicate fixture value.",
                        provides=[PROV_SPEC("dup.left")],
                        similar_to={"node": "base", "relationship": "variant", "reason": "Variant of the shared fixture base."},
                    ),
                    _node_call(
                        "right",
                        "test.duplicate_two",
                        "Produces the right duplicate fixture value.",
                        provides=[PROV_SPEC("dup.right")],
                        similar_to={"node": "base", "relationship": "variant", "reason": "Variant of the shared fixture base."},
                    ),
                ]
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert "GRAPH.SMELL.DUPLICATE_LOGIC" not in {warning.rule_id for warning in report.warnings}


def test_graph_health_keeps_unclaimed_duplicate_logic_pairs() -> None:
    registry = NodeRegistry()
    register_node(registry, "test.duplicate_one", DuplicateOneNode)
    register_node(registry, "test.duplicate_two", DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.duplicate_one", "Produces the base duplicate fixture value.", provides=[PROV_SPEC("dup.base")]),
                    _node_call(
                        "variant",
                        "test.duplicate_two",
                        "Produces an intentional variant duplicate fixture value.",
                        provides=[PROV_SPEC("dup.variant")],
                        similar_to={"node": "base", "relationship": "copy", "reason": "Copied implementation for a distinct contract."},
                    ),
                    _node_call("unclaimed", "test.duplicate_two", "Produces an undeclared duplicate fixture value.", provides=[PROV_SPEC("dup.unclaimed")]),
                ]
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    duplicate_object_ids = {warning.object_id for warning in report.warnings if warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC"}

    assert "base,variant" not in duplicate_object_ids
    assert {"base,unclaimed", "unclaimed,variant"} <= duplicate_object_ids


def test_graph_health_policy_can_exempt_findings() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the fixture flow."),
                    _node_call("BadName", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("end", "test.in_end", "Consumes value.in at the end.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "BadName", "end"),
            }
        }
    )
    policy = EffectivePolicy(
        {
            "rules": {
                "exemptions": [
                    {
                        "rule_id": "GRAPH.SMELL.CONFUSING_NODE_NAME",
                        "scope": {"object_id": "BadName"},
                        "reason": "legacy fixture",
                        "expires": "2026-12-31",
                    }
                ]
            }
        },
        ("test",),
    )

    report = validate_graph_health(
        graph,
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
        effective_policy=policy,
    )

    assert not any(warning.rule_id == "GRAPH.SMELL.CONFUSING_NODE_NAME" for warning in report.warnings)
    skipped = [finding for finding in report.skipped if finding.rule_id == "GRAPH.SMELL.CONFUSING_NODE_NAME"]
    assert skipped[0].details["policy_override"]["reason"] == "legacy fixture"


def test_graph_health_warns_for_duplicate_explicit_edges() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the fixture flow."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("end", "test.in_end", "Consumes value.in at the end.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "end"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert any(warning.rule_id == "GRAPH.EDGE.DUPLICATE" for warning in report.warnings)
    assert "GRAPH.EDGE.DUPLICATE" in report.info["rule_catalog"]


def test_graph_health_warns_for_overwide_nodeset() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "wide.flow",
                    provides=["wide.out"],
                    exports=["wide.out"],
                    pipeline={
                        "nodes": [
                            _node_call(f"n{index}", "test.seed", f"Produces wide.k{index}.", provides=[PROV_SPEC(f"wide.k{index}")])
                            for index in range(11)
                        ]
                    },
                )
            ],
            "pipeline": {"nodes": [_node_call("wide_flow", "wide.flow", "Calls the wide composite.", provides=[PROV_SPEC("wide.out")])]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(warning.rule_id == "NODESET.SMELL.TOO_WIDE" for warning in report.warnings)
    assert "wide.flow" in report.info["nodeset_findings"]

def test_nodeset_schema_requires_metadata_contract_and_purity() -> None:
    findings = collect_config_schema_findings(
        {
            "type_key": "bad.flow",
            "purity": "impure",
            "pipeline": {"nodes": [{"id": "seed", "type_used": "test.seed"}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.NODESET_METADATA" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_CONTRACT" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_FIELD_REMOVED" in rule_ids

def test_nodeset_health_accepts_valid_contract_and_groups_no_findings() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the composite fixture."),
                    _node_call("composite", "math.add_one", "Calls the add-one composite.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out at the end.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.errors == ()
    assert report.info["nodeset_findings"] == {}

def test_nodeset_health_rejects_direct_and_indirect_recursion() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.self",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={
                        "nodes": [_node_call("self", "loop.self", "Calls itself recursively.", provides=[PROV_SPEC("loop.out")])]
                    },
                ),
                _nodeset_config(
                    "loop.a",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [_node_call("to_b", "loop.b", "Calls loop.b.", provides=[PROV_SPEC("loop.out")])]},
                ),
                _nodeset_config(
                    "loop.b",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [_node_call("to_a", "loop.a", "Calls loop.a.", provides=[PROV_SPEC("loop.out")])]},
                ),
            ],
            "pipeline": {"nodes": [_node_call("use_self", "loop.self", "Calls the recursive composite.", provides=[PROV_SPEC("loop.out")])]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    recursion_errors = [error for error in report.errors if error.rule_id == "NODESET.RECURSION"]
    assert len(recursion_errors) == 2
    assert "loop.self" in report.info["nodeset_findings"]
    assert "loop.a" in report.info["nodeset_findings"]


def test_nodeset_health_treats_loop_body_as_recursion_reference() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.body",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={
                        "nodes": [
                            _node_call(
                                "again",
                                "vibeflow.loop.while",
                                "Calls the same loop body through a structured loop.",
                                provides=[PROV_SPEC("loop.out")],
                                loop={
                                    "body": "loop.body",
                                    "stop_after": 1,
                                    "outputs": [{"from": "loop.out", "as": "loop.out"}],
                                },
                            )
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call(
                        "outer",
                        "vibeflow.loop.while",
                        "Calls the recursive loop body.",
                        provides=[PROV_SPEC("loop.out")],
                        loop={
                            "body": "loop.body",
                            "stop_after": 1,
                            "outputs": [{"from": "loop.out", "as": "loop.out"}],
                        },
                    )
                ]
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    recursion_errors = [error for error in report.errors if error.rule_id == "NODESET.RECURSION"]

    assert len(recursion_errors) == 1
    assert recursion_errors[0].details["cycle"] == ("loop.body", "loop.body")


def test_nodeset_health_rejects_export_and_internal_key_leak() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                    _nodeset_config(
                        "bad.scope",
                        provides=["public.out", "missing.out"],
                        pipeline={
                        "nodes": [
                            _node_call("public", "test.seed", "Produces public output.", provides=[PROV_SPEC("public.out")]),
                            _node_call("tmp", "test.seed", "Produces internal temporary output.", provides=[PROV_SPEC("tmp.internal")]),
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("bad_scope", "bad.scope", "Calls a scope-violating composite.", provides=[PROV_SPEC("public.out"), PROV_SPEC("missing.out")])
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {error.rule_id for error in report.errors}
    assert "NODESET.PROVIDES.UNKNOWN_KEY" in rule_ids

def test_nodeset_health_and_runtime_reject_external_contract_mismatch() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the mismatch fixture."),
                    _node_call("bad_composite", "math.add_one", "Calls the composite with a wrong external contract.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("wrong.out")]),
                    _node_call("end", "test.start", "Ends the mismatch fixture."),
                ],
                "edges": _edge_chain("start", "bad_composite", "end"),
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(error.rule_id == "NODESET.CONTRACT.EXTERNAL_MISMATCH" for error in report.errors)
    with pytest.raises(PipelineRuntimeError, match="did not produce"):
        PipelineRuntime(graph, registry=_registry()).run({"value.in": 2})

def test_nodeset_health_rejects_nested_nodeset_contract_mismatch() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "inner.flow",
                    provides=["inner.out"],
                    exports=["inner.out"],
                    pipeline={"nodes": [_node_call("seed", "test.seed", "Produces inner output.", provides=[PROV_SPEC("inner.out")])]},
                ),
                _nodeset_config(
                    "outer.flow",
                    provides=["outer.out"],
                    exports=["outer.out"],
                    pipeline={"nodes": [_node_call("inner", "inner.flow", "Calls inner flow with a wrong contract.", provides=[PROV_SPEC("outer.out")])]},
                ),
            ],
            "pipeline": {"nodes": [_node_call("outer", "outer.flow", "Calls outer flow.", provides=[PROV_SPEC("outer.out")])]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(
        error.rule_id == "NODESET.CONTRACT.EXTERNAL_MISMATCH" and error.details.get("owner") == "nodeset:outer.flow"
        for error in report.errors
    )

def test_base_lib_scan_discovers_default_root_and_reports_metrics(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "math_tools.py").write_text(
        """
def add_one(value):
    return value + 1
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    payload = report.to_dict()
    assert payload["roots"] == [str(base_dir.resolve())]
    assert payload["modules"][0]["module"] == "base_lib.math_tools"
    assert payload["modules"][0]["function_count"] == 1
    assert payload["findings"] == []

def test_base_lib_scan_reports_size_complexity_imports_side_effects_and_globals(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "bad.py").write_text(
        """
import os
from pathlib import Path

CACHE = {}

def risky(value):
    path = Path("x.txt")
    if value:
        if value > 1:
            path.write_text("bad")
            (path / "child").open()
    return value
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(
        tmp_path,
        policy=PurityPolicy(
            max_source_lines=3,
            max_functions=0,
            max_branches=1,
            max_nesting_depth=1,
        ),
    )
    rule_ids = {finding.rule_id for finding in report.findings}
    assert "BASE_LIB.SOURCE.MAX_LINES" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_FUNCTIONS" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_BRANCHES" in rule_ids
    assert "BASE_LIB.COMPLEXITY.MAX_NESTING_DEPTH" in rule_ids
    assert "BASE_LIB.BANNED_IMPORT" in rule_ids
    assert "BASE_LIB.GLOBAL_STATE" in rule_ids
    assert "BASE_LIB.SIDE_EFFECT_CALL" in rule_ids

def test_base_lib_scan_reports_forbidden_project_import_and_dependency_closure(tmp_path) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "bad.py").write_text(
        """
from nodes.some_node import SomeNode
import plugins.policy

def value():
    return 1
""".strip(),
        encoding="utf-8",
    )
    (base_dir / "wrapper.py").write_text(
        """
import base_lib.bad

def wrapped():
    return base_lib.bad.value()
""".strip(),
        encoding="utf-8",
    )
    report = scan_base_lib(tmp_path, policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {finding.rule_id for finding in report.findings}
    assert ("base_lib.wrapper", "base_lib.bad") in report.dependency_edges
    assert "BASE_LIB.FORBIDDEN_PROJECT_IMPORT" in rule_ids
    assert "BASE_LIB.DEPENDENCY_CLOSURE_VIOLATION" in rule_ids

def test_node_importing_base_lib_requires_policy_declaration(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "good.py").write_text(
        """
def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.good import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source)
    assert code == 1
    assert any(error["details"].get("legacy_code") == "base_lib_undeclared" for error in payload["health"]["errors"])

    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.good"]}}',
        encoding="utf-8",
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert "base_lib.good" in {module["module"] for module in payload["base_lib"]["modules"]}

def test_node_importing_unhealthy_base_lib_reports_indirect_violation(tmp_path, capsys, monkeypatch) -> None:
    monkeypatch.syspath_prepend(str(tmp_path))
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "bad.py").write_text(
        """
import os

def helper():
    return 1
""".strip(),
        encoding="utf-8",
    )
    policy_path = tmp_path / "kernel_policy.jsonc"
    policy_path.write_text(
        '{"base_lib": {"allowed_paths": ["base_lib"], "allowed_modules": ["base_lib.bad"]}}',
        encoding="utf-8",
    )
    source = _valid_node_source(
        run_body="""
        from base_lib.bad import helper
        return {"demo.out": helper()}
""".rstrip()
    )
    code, payload = _inspect_node_source(tmp_path, capsys, source, extra_args=["--policy", str(policy_path)])
    assert code == 1
    rule_ids = {error["rule_id"] for error in payload["health"]["errors"]}
    assert "BASE_LIB.BANNED_IMPORT" in rule_ids
    assert "NODE.BASE_LIB.INDIRECT_VIOLATION" in rule_ids
