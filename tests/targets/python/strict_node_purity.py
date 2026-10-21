from tests.fixtures.support.declarations import native_registry
from tests.fixtures.support.strict_support_runtime_implementations import DuplicateThreeNode
from tests.fixtures.support.declarations import node_declaration, configured_declaration
from tests.fixtures.support.strict_support import *

from vibeflow.targets.python.project.policy import EffectivePolicy
from tests.fixtures.support.rule_inspection import _inspect_node_source, _valid_node_source, node_document
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health as _validate_graph_health
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def validate_graph_health(graph, *, registry=None, **kwargs):
    if registry is not None:
        kwargs.setdefault("source_context", collect_workflow_source_context(registry, graph))
    return _validate_graph_health(graph, registry=registry, **kwargs)





DuplicateThreeNode_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='test.duplicate_three', display_name='Duplicate Three', description='Duplicates output for an unclaimed comparison.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(provides=(DataProvider('dup.three', 'dup.three', display_name='Duplicate Three'),), output_semantics={'dup.three': ('third duplicate fixture value',)}), rulesets=("vibeflow.process",))


def test_architecture_smells_warn_for_mismatched_metadata_and_unstable_keys(tmp_path, capsys) -> None:
    descriptor = node_document(contract={"provides":[PROV_SPEC("Tmp Key")],
        "output_semantics":{"Tmp Key":["scratch debug value"]},"examples":[{"inputs":{},"params":{}}]})
    source = _valid_node_source(run_body='        return {"Tmp Key": 1}')
    code, payload = _inspect_node_source(tmp_path, capsys, source, descriptor=descriptor)
    assert code == 0
    warnings = {warning["code"] for warning in payload["health"]["warnings"]}
    assert "NODE.MAINTAINABILITY.TEMPORARY_KEY" in warnings
    assert "NODE.MAINTAINABILITY.CONFUSING_KEY_NAME" in warnings


def test_graph_health_reports_node_metrics_duplicate_logic_and_confusing_node_names() -> None:
    registry = native_registry()
    register_node(registry, DuplicateOneNode_DECLARATION, DuplicateOneNode)
    register_node(registry, DuplicateTwoNode_DECLARATION, DuplicateTwoNode)
    register_node(registry, DuplicateThreeNode_DECLARATION, DuplicateThreeNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("DuplicateOne", "test.duplicate_one", "Produces the first duplicate fixture value."),
                    _node_call("duplicate_two", "test.duplicate_two", "Produces the second duplicate fixture value."),
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
    assert duplicate["details"]["call_definitions"] == {"DuplicateOne": "test.duplicate_one", "duplicate_two": "test.duplicate_two"}
    assert duplicate["details"]["fingerprint"]
    assert duplicate["details"]["duplicate_group"] == ["DuplicateOne", "duplicate_two"]
    assert "similar_to" in duplicate["details"]["suppression_hint"]
    from vibeflow.tooling.application.python.reports import format_finding_text

    text = format_finding_text(next(warning for warning in report.warnings if warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC"))
    assert "\n  details:" in text
    assert '"nodes":["DuplicateOne","duplicate_two"]' in text


def test_graph_health_suppresses_declared_similar_duplicate_logic_pairs() -> None:
    registry = native_registry()
    register_node(registry, DuplicateOneNode_DECLARATION, DuplicateOneNode)
    register_node(registry, DuplicateTwoNode_DECLARATION, DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.duplicate_one", "Produces the base duplicate fixture value."),
                    _node_call(
                        "variant",
                        "test.duplicate_two",
                        "Produces an intentional variant duplicate fixture value.",

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
            "nodeset_types": [
                _nodeset_config(
                    "inner.flow",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("start", "test.start", "Starts the nested flow."),
                            _node_call("add", "test.add", "Adds a missing nested input."),
                            _node_call("end", "test.out_end", "Ends after nested value.out."),
                        ],
                        "edges": [{"from": "start", "to": "end"}],
                    },
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the top-level flow."),
                    _node_call(
                        "composite",
                        "inner.flow",
                        "Runs the nested flow.",

                    ),
                    _node_call("end", "test.out_end", "Ends after composite output."),
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
    from tests.fixtures.support.rule_inspection import depth_ruleset
    from dataclasses import replace
    graph=replace(graph,rulesets=("test.depth",))
    checked_registry=_registry()
    from types import SimpleNamespace
    checked_registry.rule_catalogs=(*checked_registry.rule_catalogs,SimpleNamespace(rules=(),rulesets=(depth_ruleset(8),)))

    report = validate_graph_health(
        graph,
        registry=checked_registry,
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    findings = [*report.errors, *report.warnings]

    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:ns0", node="bad", required_type="value.in")) == 1
    assert len(_findings(findings, "GRAPH.DATA.UNCONSUMED_PROVIDER", owner="nodeset:ns0", node="bad", provider_key="value.out")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.UNREACHABLE_FROM_START", owner="nodeset:ns0", node="bad")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.CANNOT_REACH_END", owner="nodeset:ns0", node="bad")) == 1
    assert len(_findings(findings, "GRAPH.FLOW.ORPHAN_NODE", owner="nodeset:ns0", node="bad")) == 1
    assert not _findings(findings, "GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME", owner="nodeset:ns0", object_id="bad")
    assert not _findings(findings, "GRAPH.SMELL.MISSING_NODE_DESCRIPTION", owner="nodeset:ns0", object_id="bad")


def test_graph_health_keeps_same_node_problem_separate_by_owner() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                {**_bad_leaf_nodeset("left.leaf"), "provides":[]},
                {**_bad_leaf_nodeset("right.leaf"), "provides":[]},
            ],
            "pipeline": {
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the owner aggregation fixture."),
                        _node_call("left", "left.leaf", "Exercises the first declared bad leaf."),
                        _node_call("right", "right.leaf", "Exercises the second declared bad leaf."),
                        _node_call("end", "test.start", "Ends the owner aggregation fixture."),
                    ],
                    "edges": _edge_chain("start","left","right","end"),
            },
        }
    )

    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    findings = [*report.errors, *report.warnings]

    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", node="bad", required_type="value.in")) == 2
    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:left.leaf", node="bad", required_type="value.in")) == 1
    assert len(_findings(findings, "GRAPH.DATA.MISSING_DIRECT_PROVIDER", owner="nodeset:right.leaf", node="bad", required_type="value.in")) == 1


def test_nodeset_override_path_errors_are_not_repeated_by_nested_definition_expansion() -> None:
    nodeset_types = [_bad_leaf_nodeset("ns0")]
    first_wrapper = _wrapper_nodeset("ns1", "ns0")
    first_wrapper["pipeline"]["nodes"][1]["node_configs"] = {"missing.path": {"delta": 1}}
    nodeset_types.append(first_wrapper)
    for index in range(2, 6):
        nodeset_types.append(_wrapper_nodeset(f"ns{index}", f"ns{index - 1}"))
    graph = parse_graph_config(
        {
            "nodeset_types": nodeset_types,
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the override aggregation fixture."),
                    _node_call("top", "ns5", "Calls the deepest wrapper."),
                    _node_call("end", "test.out_end", "Ends the override aggregation fixture."),
                ],
                "edges": _edge_chain("start", "top", "end"),
            },
        }
    )

    report = validate_graph_health(
        graph,
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    errors = [error for error in report.errors if error.rule_id == "NODESET.CONFIG.UNKNOWN_NODE"]

    assert len(errors) == 1
    assert errors[0].object_id == "call"
    assert errors[0].details["nodeset"] == "ns0"
    assert errors[0].details["path"] == "missing.path"


def test_node_config_override_path_can_pass_through_loop_body() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "loop.add_body",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
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
                    _node_call("end", "test.out_end", "Ends after value.out."),
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
            "nodeset_types": [
                _nodeset_config(
                    "plain.body",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the invalid override fixture."),
                    _node_call(
                        "composite",
                        "plain.body",
                        "Calls a body with an invalid nested override path.",

                        node_configs={"add.inner": {"delta": 5}},
                    ),
                    _node_call("end", "test.out_end", "Ends after value.out."),
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
    assert invalid.details["definition_id"] == "test.add"
    assert invalid.details["composite_kind"] == "none"


def test_health_report_aggregates_duplicate_findings_but_not_different_direct_sources() -> None:
    from types import SimpleNamespace
    from dataclasses import replace
    from vibeflow.core.rules import RuleDescriptor, RuleCall, RulesetDescriptor, RuleResult
    def duplicates(context, inputs, params):
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
        return RuleResult(findings=(
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
        ))

    registry = _registry()
    rule = RuleDescriptor("test.duplicates", level="graph")
    ruleset = RulesetDescriptor("test.duplicates",calls=(RuleCall("check",rule_id=rule.id),))
    registry.rule_catalogs = (*registry.rule_catalogs, SimpleNamespace(rules=(rule,),rulesets=(ruleset,)),)
    defaults = registry.rule_handler_loader
    registry.rule_handler_loader = lambda plan: {**defaults(plan), rule.id:duplicates}
    graph = replace(parse_graph_config({"pipeline":_seed_only_pipeline()}),rulesets=("test.duplicates",))
    report = validate_graph_health(graph,registry=registry,purity_policy=PurityPolicy(max_source_lines=1000))
    duplicate = next(warning for warning in report.warnings if warning.rule_id == "PLUGIN.DUPLICATE")
    simulated_missing = [error for error in report.errors if error.rule_id == "GRAPH.DATA.MISSING_DIRECT_PROVIDER" and error.details.get("node") == "join"]

    assert duplicate.details["aggregated"] is True
    assert duplicate.details["occurrences"] == 2
    assert duplicate.details["suppressed_duplicates"] == 1
    assert len(simulated_missing) == 2

    from vibeflow.tooling.application.python.reports import format_finding_text

    text = format_finding_text(duplicate)
    assert '"aggregated":true' in text
    assert '"occurrences":2' in text
    assert '"suppressed_duplicates":1' in text


def _nested_bad_leaf_graph(*, depth: int):
    nodeset_types = [_bad_leaf_nodeset("ns0")]
    for index in range(1, depth):
        nodeset_types.append(_wrapper_nodeset(f"ns{index}", f"ns{index - 1}"))
    return parse_graph_config(
        {
            "nodeset_types": nodeset_types,
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nested aggregation fixture."),
                    _node_call(
                        "top",
                        f"ns{depth - 1}",
                        "Calls the deepest wrapper.",

                    ),
                    _node_call("end", "test.out_end", "Ends the nested aggregation fixture."),
                ],
                "edges": _edge_chain("start", "top", "end"),
            },
        }
    )


def _nodeset_depth_graph(
    depth: int,
    *,
    loop_layer: int | None = None,
    loop_layers: set[int] | None = None,
    branch: bool = False,
    pipeline_uses_chain: bool = True,
    planned: bool = False,
):
    nodeset_types = [
        _nodeset_config(
            "depth.0",
            provides=["value.out"],
            pipeline={
                "nodes": [
                    _node_call("leaf", "test.seed", "Produces the depth fixture output.")
                ]
            },
        )
    ]
    for index in range(1, depth):
        child = f"depth.{index - 1}"
        if index == loop_layer or index in (loop_layers or set()):
            call = _node_call(
                "call",
                "vibeflow.loop.while",
                f"Calls {child} as a loop body.",
                provides=[PROV_SPEC("value.out")],
                loop={
                    "body": child,
                    "max_iterations": 10,
                    "stop_after": 1,
                    "outputs": [{"from": "value.out", "as": "value.out"}],
                },
            )
        else:
            call = _node_call("call", child, f"Calls {child}.")
        calls = [call]
        if branch and index == depth - 1:
            calls.append(_node_call("branch", "depth.0", "Calls a shallow branch."))
        nodeset_types.append(
            _nodeset_config(
                f"depth.{index}",
                provides=["value.out"],
                pipeline={"nodes": calls},
            )
        )
    if planned:
        for nodeset in nodeset_types:
            nodeset["status"] = "planned"
    pipeline_node = (
        _node_call("top", f"depth.{depth - 1}", "Calls the depth fixture.")
        if pipeline_uses_chain
        else _node_call("seed", "test.seed", "Leaves the depth fixture unused.")
    )
    return parse_graph_config({"nodeset_types": nodeset_types, "pipeline": {"nodes": [pipeline_node]}})


def _bad_leaf_nodeset(name: str) -> dict:
    return _nodeset_config(
        name,
        requires=["value.in"],
        provides=["value.out"],
        exports=["value.out"],
        pipeline={
            "nodes": [
                _node_call("start", "test.start", "Starts the bad leaf."),
                {'id': 'bad', 'definition_id': 'test.add', 'display_name': 'Bad', 'description': 'Exercises bad in the graph-health fixture.'},
                _node_call("end", "test.out_end", "Ends after value.out."),
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
            "inputs": [INPUT_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", f"Starts wrapper {name}."),
                _node_call("call", f"{child}", f"Calls {child}."),
                _node_call("end", "test.out_end", f"Ends wrapper {name}."),
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
    register_node(registry, DuplicateOneNode_DECLARATION, DuplicateOneNode)
    register_node(registry, DuplicateTwoNode_DECLARATION, DuplicateTwoNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.seed", "Produces the shared base fixture value."),
                    _node_call(
                        "left",
                        "test.duplicate_one",
                        "Produces the left duplicate fixture value.",

                        similar_to={"node": "base", "relationship": "variant", "reason": "Variant of the shared fixture base."},
                    ),
                    _node_call(
                        "right",
                        "test.duplicate_two",
                        "Produces the right duplicate fixture value.",

                        similar_to={"node": "base", "relationship": "variant", "reason": "Variant of the shared fixture base."},
                    ),
                ]
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert "GRAPH.SMELL.DUPLICATE_LOGIC" not in {warning.rule_id for warning in report.warnings}


def test_graph_health_keeps_unclaimed_duplicate_logic_pairs() -> None:
    registry = native_registry()
    register_node(registry, DuplicateOneNode_DECLARATION, DuplicateOneNode)
    register_node(registry, DuplicateTwoNode_DECLARATION, DuplicateTwoNode)
    register_node(registry, DuplicateThreeNode_DECLARATION, DuplicateThreeNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("base", "test.duplicate_one", "Produces the base duplicate fixture value."),
                    _node_call(
                        "variant",
                        "test.duplicate_two",
                        "Produces an intentional variant duplicate fixture value.",

                        similar_to={"node": "base", "relationship": "copy", "reason": "Copied implementation for a distinct contract."},
                    ),
                    _node_call("unclaimed", "test.duplicate_three", "Produces an undeclared duplicate fixture value."),
                ]
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    duplicate_object_ids = {warning.object_id for warning in report.warnings if warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC"}

    assert "base,variant" not in duplicate_object_ids
    assert {"base,unclaimed", "unclaimed,variant"} <= duplicate_object_ids


def test_graph_health_explicit_empty_ruleset_omits_review() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the fixture flow."),
                    _node_call("BadName", "test.seed", "Produces value.in."),
                    _node_call("end", "test.in_end", "Consumes value.in at the end."),
                ],
                "edges": _edge_chain("start", "BadName", "end"),
            }
        }
    )
    from dataclasses import replace
    baseline = validate_graph_health(graph, registry=_registry())
    assert any(warning.rule_id == "GRAPH.SMELL.CONFUSING_NODE_NAME" for warning in baseline.warnings)
    report = validate_graph_health(replace(graph,rulesets=()),registry=_registry())
    assert not any(warning.rule_id == "GRAPH.SMELL.CONFUSING_NODE_NAME" for warning in report.warnings)
    assert report.info["workflow_rulesets"] == []
    assert report.skipped == ()


def test_graph_health_warns_for_duplicate_explicit_edges() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the fixture flow."),
                    _node_call("seed", "test.seed", "Produces value.in."),
                    _node_call("end", "test.in_end", "Consumes value.in at the end."),
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
    assert any(call["rule_id"] == "vibeflow.workflow" for execution in report.info["rule_executions"] for call in execution["plan"]["calls"])


def test_graph_health_warns_for_overwide_nodeset() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "wide.flow",
                    provides=["wide.out"],
                    exports=["wide.out"],
                    pipeline={
                        "nodes": [
                            _node_call(f"n{index}", "test.seed", f"Produces wide.k{index}.")
                            for index in range(11)
                        ]
                    },
                )
            ],
            "pipeline": {"nodes": [_node_call("wide_flow", "wide.flow", "Calls the wide composite.")]},
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
            "pipeline": {"nodes": [{"id": "seed", "definition_id": "test.seed"}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.SCHEMA.NODESET_METADATA" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_CONTRACT" in rule_ids
    assert "CONFIG.SCHEMA.NODESET_FIELD_REMOVED" in rule_ids

def test_nodeset_health_accepts_valid_contract_and_groups_no_findings() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the composite fixture."),
                    _node_call("composite", "math.add_one", "Calls the add-one composite."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
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
            "nodeset_types": [
                _nodeset_config(
                    "loop.self",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={
                        "nodes": [_node_call("self", "loop.self", "Calls itself recursively.")]
                    },
                ),
                _nodeset_config(
                    "loop.a",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [_node_call("to_b", "loop.b", "Calls loop.b.")]},
                ),
                _nodeset_config(
                    "loop.b",
                    provides=["loop.out"],
                    exports=["loop.out"],
                    pipeline={"nodes": [_node_call("to_a", "loop.a", "Calls loop.a.")]},
                ),
            ],
            "pipeline": {"nodes": [_node_call("use_self", "loop.self", "Calls the recursive composite.")]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    recursion_errors = [error for error in report.errors if error.rule_id == "NODESET.RECURSION"]
    assert len(recursion_errors) == 2
    assert "NODESET.NESTING.DEPTH_EXCEEDED" not in {error.rule_id for error in report.errors}
    assert "loop.self" in report.info["nodeset_findings"]
    assert "loop.a" in report.info["nodeset_findings"]


def test_nodeset_health_treats_loop_body_as_recursion_reference() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
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
    assert "NODESET.NESTING.DEPTH_EXCEEDED" not in {error.rule_id for error in report.errors}


def _depth_registry():
    registry=_registry()
    return registry


def test_nodeset_depth_limit_accepts_four_and_rejects_five_mixed_layers() -> None:
    accepted = validate_graph_health(
        _nodeset_depth_graph(4, loop_layer=2, branch=True),
        registry=_depth_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    rejected = validate_graph_health(
        _nodeset_depth_graph(5, loop_layer=2, branch=True),
        registry=_depth_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )

    assert "NODESET.NESTING.DEPTH_EXCEEDED" not in {error.rule_id for error in accepted.errors}
    depth_error = next(error for error in rejected.errors if error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED")
    assert depth_error.details["limit"] == 4
    assert depth_error.details["actual_depth"] == 5
    assert depth_error.details["chain"] == ("depth.4", "depth.3", "depth.2", "depth.1", "depth.0")
    assert [call["kind"] for call in depth_error.details["calls"]] == ["nodeset", "nodeset", "nodeset", "loop_body", "nodeset"]


def test_nodeset_depth_limit_counts_nested_while_bodies() -> None:
    accepted = validate_graph_health(
        _nodeset_depth_graph(4, loop_layers={1, 2, 3}),
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )
    rejected = validate_graph_health(
        _nodeset_depth_graph(5, loop_layers={1, 2, 3, 4}),
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )

    assert "NODESET.NESTING.DEPTH_EXCEEDED" not in {error.rule_id for error in accepted.errors}
    depth_error = next(error for error in rejected.errors if error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED")
    assert depth_error.details["actual_depth"] == 5
    assert [call["kind"] for call in depth_error.details["calls"]] == ["nodeset", "loop_body", "loop_body", "loop_body", "loop_body"]


def test_nodeset_depth_limit_checks_unused_planned_definitions() -> None:
    report = validate_graph_health(
        _nodeset_depth_graph(5, pipeline_uses_chain=False, planned=True),
        registry=_registry(),
        purity_policy=PurityPolicy(max_source_lines=1000),
    )

    depth_error = next(error for error in report.errors if error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED")
    assert depth_error.details["owner"] == "nodeset:depth.4"
    assert depth_error.details["actual_depth"] == 5
    assert depth_error.details["chain"][0] == "depth.4"


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "4"])
def test_graph_health_rejects_invalid_nodeset_max_depth(value) -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})

    from dataclasses import replace
    from tests.fixtures.support.rule_inspection import depth_ruleset
    graph=replace(graph,rulesets=("test.depth",))
    checked_registry=_registry()
    from types import SimpleNamespace
    checked_registry.rule_catalogs=(*checked_registry.rule_catalogs,SimpleNamespace(rules=(),rulesets=(depth_ruleset(value),)))
    report = validate_graph_health(graph, registry=checked_registry)
    assert any(item.failure_layer == "rule" for item in report.errors)


def test_nodeset_health_rejects_export_and_internal_key_leak() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                    _nodeset_config(
                        "bad.scope",
                        provides=["public.out", "missing.out"],
                        pipeline={
                        "nodes": [
                            _node_call("public", "test.seed", "Produces public output."),
                            _node_call("tmp", "test.seed", "Produces internal temporary output."),
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("bad_scope", "bad.scope", "Calls a scope-violating composite.")
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    rule_ids = {error.rule_id for error in report.errors}
    assert "NODESET.PROVIDES.UNKNOWN_KEY" in rule_ids

def test_nodeset_call_rejects_duplicate_external_contract() -> None:
    config = {
            "nodeset_types": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the mismatch fixture."),
                    {
                        "id": "bad_composite",
                        "definition_id": "math.add_one",
                        "display_name": "Bad Composite",
                        "description": "Attempts to redefine a nodeset contract at its call site.",
                        "requires": [REQ_SPEC("value.in")],
                        "provides": [PROV_SPEC("wrong.out")],
                    },
                    _node_call("end", "test.start", "Ends the mismatch fixture."),
                ],
                "edges": _edge_chain("start", "bad_composite", "end"),
            },
        }
    with pytest.raises(GraphConfigError, match="derived from definition_id"):
        parse_graph_config(config)

def test_nodeset_health_rejects_nested_nodeset_unknown_exports() -> None:
    graph = parse_graph_config(
        {
            "nodeset_types": [
                _nodeset_config(
                    "inner.flow",
                    provides=["inner.out"],
                    exports=["inner.out"],
                    pipeline={"nodes": [_node_call("seed", "test.seed", "Produces inner output.")]},
                ),
                _nodeset_config(
                    "outer.flow",
                    provides=["outer.out"],
                    exports=["outer.out"],
                    pipeline={"nodes": [_node_call("inner", "inner.flow", "Calls inner flow with a wrong contract.")]},
                ),
            ],
            "pipeline": {"nodes": [_node_call("outer", "outer.flow", "Calls outer flow.")]},
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(
        error.rule_id == "NODESET.PROVIDES.UNKNOWN_KEY" and error.details.get("nodeset") == "outer.flow"
        for error in report.errors
    )
