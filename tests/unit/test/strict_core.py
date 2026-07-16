from tests.unit.strict_support import *


class ProviderPlanningBoundary(DemoBoundary):
    def _select_http_provider(self, providers):
        return providers[0] if providers else ""

    def after_run(self, outputs, run_config):
        self._select_http_provider(["http"])
        return {}


class TwoRouteNode:
    NODE_INFO = NodeInfo("test.two_route", "Two Route", "test", "Routes flow.", "0.1.0", "decision")
    CONTRACT = NodeContract(
        requires=(DataRequirement("value.in", "exactly_one"),),
        provides=(DataProvider("flow.route", "flow.route"),),
        input_semantics={"value.in": ("input",)},
        output_semantics={"flow.route": ("route",)},
        output_schema={"flow.route": {"type": "string", "enum": ["again", "done"]}},
        examples=({"inputs": {"value.in": 1}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


class BodyRouteNode:
    NODE_INFO = NodeInfo("test.body_route", "Body Route", "test", "Routes inside a loop body.", "0.1.0", "decision")
    CONTRACT = NodeContract(
        requires=(DataRequirement("flow.route", "exactly_one"),),
        provides=(DataProvider("flow.inner", "flow.inner"),),
        input_semantics={"flow.route": ("outer loop route",)},
        output_semantics={"flow.inner": ("body branch route",)},
        output_schema={"flow.inner": {"type": "string", "enum": ["left", "right"]}},
        examples=({"inputs": {"flow.route": "again"}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"flow.inner": "left"}


def _register_fulltext_nodes(registry: NodeRegistry) -> None:
    registry.register("literature.rank_records", SeedNode, config_schema={"value": {"type": "number"}}, config_defaults={"value": 1})

def test_pure_node_metadata_and_static_check() -> None:
    assert validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1000)) == []
    violations = validate_node_class(BadIoNode, policy=PurityPolicy(max_source_lines=1000))
    assert any(item.code == "effect_call" and item.rule_id == "NODE.EFFECT.CALL_FORBIDDEN" for item in violations)

def test_source_size_limit_is_enforced() -> None:
    violations = validate_node_class(SeedNode, policy=PurityPolicy(max_source_lines=1))
    assert any(item.code == "source_too_large" for item in violations)


def test_flow_kind_rule_ids_are_strict() -> None:
    class MissingFlowKindNode(SeedNode):
        NODE_INFO = NodeInfo("bad.missing_flow", "Bad", "test", "Bad node.", "0.1.0", "")

    class InvalidFlowKindNode(SeedNode):
        NODE_INFO = NodeInfo("bad.invalid_flow", "Bad", "test", "Bad node.", "0.1.0", "branch")

    assert any(item.rule_id == "NODE.FLOW_KIND.MISSING" for item in validate_node_class(MissingFlowKindNode, policy=PurityPolicy(max_source_lines=1000)))
    assert any(item.rule_id == "NODE.FLOW_KIND.INVALID" for item in validate_node_class(InvalidFlowKindNode, policy=PurityPolicy(max_source_lines=1000)))


def test_external_flag_keeps_contract_but_skips_source_quality() -> None:
    class ExternalNode:
        NODE_INFO = NodeInfo("test.external", "External", "test", "Calls external package.", "0.1.0", "process", external=True)
        CONTRACT = NodeContract(
            provides=(DataProvider("external.out", "external.out"),),
            output_semantics={"external.out": ("external output",)},
            output_schema={"external.out": {"type": "string"}},
            examples=({"inputs": {}, "params": {}},),
        )

        def run_pure(self, inputs, params):
            import os

            return {"external.out": "ok" if os.name else "ok"}

    class InvalidExternalFlagNode(ExternalNode):
        NODE_INFO = NodeInfo("test.external_invalid", "External", "test", "Calls external package.", "0.1.0", "process", external="yes")

    external_violations = validate_node_class(ExternalNode, policy=PurityPolicy(max_source_lines=1, max_functions=0))
    assert not any(item.code in {"banned_import", "source_too_large", "complexity_max_functions"} for item in external_violations)
    assert any(item.rule_id == "NODE.EXTERNAL.INVALID" for item in validate_node_class(InvalidExternalFlagNode, policy=PurityPolicy(max_source_lines=1000)))


def test_external_flag_does_not_require_route_output() -> None:
    class ExternalProcessNode:
        NODE_INFO = NodeInfo("test.external_ok", "External", "test", "Calls external package.", "0.1.0", "process", external=True)
        CONTRACT = NodeContract(
            provides=(DataProvider("external.out", "external.out"),),
            output_semantics={"external.out": ("external output",)},
            output_schema={"external.out": {"type": "number"}},
            examples=({"inputs": {}, "params": {}},),
        )

        def run_pure(self, inputs, params):
            return {"external.out": 1}

    assert validate_node_class(ExternalProcessNode, policy=PurityPolicy(max_source_lines=1000)) == []


def test_edge_when_syntax_is_static_config_error() -> None:
    with pytest.raises(GraphConfigError, match="literal must be true, false, or quoted string"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                        _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    ],
                    "edges": [{"from": "seed", "to": "add", "when": "route == ok"}],
                }
            }
        )


def test_decision_branch_value_must_match_output_schema() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the branch fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("route", "test.two_route", "Chooses the route.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("end", "test.start", "Ends the branch fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "route"},
                    {"from": "route", "to": "end", "when": "flow.route == 'typo'"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(item.rule_id == "GRAPH.DECISION.UNKNOWN_BRANCH_VALUE" for item in report.errors)


def test_decision_branch_must_reach_end_in_acyclic_graph() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the branch reachability fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("route", "test.two_route", "Chooses the route.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.seed", "Produces loop continuation data.", provides=[PROV_SPEC("value.in.copy", "value.in")]),
                    _node_call("dead", "test.seed", "Produces dead-end data.", provides=[PROV_SPEC("value.in.dead", "value.in")]),
                    _node_call("end", "test.start", "Ends the branch reachability fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "end"},
                    {"from": "route", "to": "dead", "when": "flow.route == 'done'"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(item.rule_id == "GRAPH.DECISION.BRANCH_CANNOT_REACH_END" for item in report.errors)


def test_decision_cycle_is_forbidden_even_with_exit() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    register_node(registry, "test.body_route", BodyRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the SCC fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("controller", "test.two_route", "Controls the outer route.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("body_route", "test.body_route", "Controls the body route.", requires=[REQ_SPEC("flow.route")], provides=[PROV_SPEC("flow.inner")]),
                    _node_call("left_continue", "test.seed", "Produces left continuation data.", provides=[PROV_SPEC("value.in.left", "value.in")]),
                    _node_call("right_continue", "test.seed", "Produces right continuation data.", provides=[PROV_SPEC("value.in.right", "value.in")]),
                    _node_call("end", "test.start", "Ends the SCC fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "controller"},
                    {"from": "controller", "to": "body_route", "when": "flow.route == 'again'"},
                    {"from": "controller", "to": "end", "when": "flow.route == 'done'"},
                    {"from": "body_route", "to": "left_continue", "when": "flow.inner == 'left'"},
                    {"from": "body_route", "to": "right_continue", "when": "flow.inner == 'right'"},
                    {"from": "left_continue", "to": "controller"},
                    {"from": "right_continue", "to": "controller"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert any(item.rule_id == "GRAPH.CYCLE.FORBIDDEN" for item in report.errors)


def test_planned_node_is_concern_not_unknown_type() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("future", "planned.future", "Represents future work.", status="planned", flow_kind="process"),
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "CONCERNS"
    assert any(warning.rule_id == "GRAPH.PLANNED.NODE" for warning in report.warnings)
    assert not any(error.rule_id == "NODE.TYPE.UNKNOWN" for error in report.errors)


def test_implemented_nodeset_cannot_contain_planned_child() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "a",
                    requires=[],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("future", "planned.future", "Represents a planned child.", status="planned", flow_kind="process"),
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("a", "a", "Calls nodeset a.", provides=[PROV_SPEC("value.out")]),
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "FAIL"
    assert any(error.rule_id == "GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD" for error in report.errors)

def test_requires_provides_do_not_create_data_edges_and_explicit_flow_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the explicit edge fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], value=4),
                    _node_call("add", "test.add", "Adds delta to value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], delta=3),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "end"},
                ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert [edge.pair for edge in compiled.data_edges] == []
    assert [edge.pair for edge in compiled.effective_edges] == [("start", "seed"), ("seed", "add"), ("add", "end")]
    context = PipelineRuntime(graph, registry=_registry()).run()
    assert context.get("value.out")["value"] == 7


def test_explicit_shortcut_edge_is_data_bypass_and_does_not_trigger_target() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the data bypass fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], value=4),
                    _node_call("add", "test.add", "Runs the mainline timing step.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], delta=3),
                    _node_call("end", "test.in_end", "Consumes the bypassed seed value after add has run.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "end"},
                    {"from": "seed", "to": "end"},
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph, registry=_registry())

    assert [edge.pair for edge in compiled.mainline_edges] == [("start", "seed"), ("seed", "add"), ("add", "end")]
    assert [edge.pair for edge in compiled.data_bypass_edges] == [("seed", "end")]
    result = PipelineRuntime(graph, registry=_registry()).run()
    assert result.get("runtime.exec_order") == ("start", "seed", "add", "end")


def test_mainline_data_bypass_without_trigger_has_actionable_details() -> None:
    registry = _registry()
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the bypass trigger fixture."),
                    _node_call("end", "test.start", "Ends the only reachable mainline."),
                    _node_call("source", "test.seed", "Disconnected bypass source.", provides=[PROV_SPEC("value.in")]),
                    _node_call("middle", "test.copy", "Disconnected intermediate node.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.copy", "value.in")]),
                    _node_call("target", "test.in_end", "Disconnected bypass target.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": [
                    {"from": "start", "to": "end"},
                    {"from": "source", "to": "middle"},
                    {"from": "middle", "to": "target"},
                    {"from": "source", "to": "target"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    warning = next(item for item in report.warnings if item.rule_id == "GRAPH.MAINLINE.DATA_BYPASS_WITHOUT_MAINLINE_TRIGGER")

    assert warning.details["owner"] == "pipeline"
    assert warning.details["source"] == "source"
    assert warning.details["target"] == "target"
    assert warning.details["edge"] == {"from": "source", "to": "target"}
    assert warning.details["branch_nodes"] == ["target"]
    assert warning.details["suggested_fixes"]


def test_mainline_unexpected_sync_fanout_warning_has_actionable_details() -> None:
    registry = _registry()
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the fanout fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("source", "test.add", "Branches without decision semantics.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("side", "test.copy", "Side synchronous branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy", "value.in")]),
                    _node_call("end", "test.out_end", "Ends the fanout fixture.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "source"},
                    {"from": "source", "to": "side"},
                    {"from": "source", "to": "end"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    warning = next(item for item in report.warnings if item.rule_id == "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT")

    assert warning.details["owner"] == "pipeline"
    assert warning.details["source"] == "source"
    assert warning.details["branch_nodes"] == ["end", "side"]
    assert {"from": "source", "to": "side"} in warning.details["branch_edges"]
    assert {"from": "source", "to": "end"} in warning.details["branch_edges"]
    assert warning.details["suggested_fixes"]


def test_mainline_sync_fanout_with_explicit_all_join_is_allowed() -> None:
    registry = _registry()
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the explicit join fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("left", "test.copy", "Left joined branch.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.left", "value.left")]),
                    _node_call("right", "test.copy", "Right joined branch.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.right", "value.right")]),
                    _node_call(
                        "join",
                        "test.copy",
                        "Explicitly waits for both branches.",
                        requires=[REQ_SPEC("value.left"), REQ_SPEC("value.right")],
                        provides=[PROV_SPEC("value.join", "value.out")],
                        join_policy="all",
                    ),
                    _node_call("end", "test.out_end", "Ends after joined value.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "left"},
                    {"from": "seed", "to": "right"},
                    {"from": "left", "to": "join"},
                    {"from": "right", "to": "join"},
                    {"from": "join", "to": "end"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))

    assert not any(item.rule_id == "GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT" for item in (*report.errors, *report.warnings))


def test_mainline_decision_dead_end_warning_has_actionable_details() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the decision mainline fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")]),
                    _node_call("route", "test.two_route", "Chooses the branch.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("dead", "test.copy", "Dead branch node.", provides=[PROV_SPEC("value.dead", "value.in")]),
                    _node_call("sink", "test.copy", "Dead branch sink.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.sink", "value.out")]),
                    _node_call("end", "test.start", "Valid terminal end."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "route"},
                    {"from": "route", "to": "dead", "when": "flow.route == 'again'"},
                    {"from": "dead", "to": "sink"},
                    {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    warning = next(item for item in report.warnings if item.rule_id == "GRAPH.MAINLINE.DECISION_BRANCH_DEAD_END")

    assert warning.details["owner"] == "pipeline"
    assert warning.details["source"] == "route"
    assert warning.details["target"] == "dead"
    assert warning.details["edge"] == {"from": "route", "to": "dead", "when": "flow.route == 'again'"}
    assert warning.details["branch_nodes"] == ["dead", "sink"]
    assert warning.details["suggested_fixes"]

def test_undeclared_cycle_is_rejected() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("copy", "test.copy", "Copies value.out back to value.in.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy", "value.in")]),
                ],
                "edges": [{"from": "add", "to": "copy"}, {"from": "copy", "to": "add"}],
            }
        }
    )
    with pytest.raises(GraphCompileError, match="explicit flow cycle is forbidden") as exc_info:
        GraphCompiler().compile(graph, registry=_registry())
    assert exc_info.value.rule_id == "GRAPH.CYCLE.FORBIDDEN"

def test_removed_loop_registration_and_edge_limits_are_rejected() -> None:
    with pytest.raises(GraphConfigError, match="pipeline.loops is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])],
                    "loops": [{"id": "counter_loop", "edges": [["seed", "seed"]]}],
                }
            }
        )

    with pytest.raises(GraphConfigError, match="max_executions is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])],
                    "edges": [{"from": "seed", "to": "seed", "max_executions": 2}],
                }
            }
        )

def test_compiler_can_check_registry_node_types() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"id": "missing", "type_used": "test.missing", "display_name": "Missing", "description": "Missing fixture."}]}})
    with pytest.raises(GraphCompileError, match="unknown type"):
        GraphCompiler().compile(graph, registry=_registry())

def test_boundary_config_is_removed() -> None:
    with pytest.raises(GraphConfigError, match="boundary is removed"):
        parse_graph_config(
            {
                "boundary": {"type": "test.boundary", "consumes": ["effects.request"], "provides": ["io.result"]},
                "pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])]},
            }
        )

def test_registry_namespace_mismatch_is_warning() -> None:
    registry = NodeRegistry()
    _register_fulltext_nodes(registry)
    graph = parse_graph_config({"pipeline": {"nodes": [_node_call("rank", "literature.rank_records", "Ranks records.", provides=[PROV_SPEC("value.in")])]}})
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    warnings = [warning for warning in report.warnings if warning.rule_id == "REGISTRY.SMELL.NAMESPACE_MISMATCH"]
    assert len(warnings) == 1
    assert warnings[0].details["expected_namespace"] == "fulltext"

def test_boundary_schema_and_node_registry_isolation() -> None:
    findings = collect_config_schema_findings(
        {
            "boundary": {
                "type": "test.boundary",
                "config": [],
                "consumes": ["bad.request"],
                "provides": ["bad.result"],
                "allowed_paths": "runs",
            },
            "pipeline": {"nodes": [{"id": "seed", "type_used": "test.seed", "display_name": "Seed", "description": "Seed fixture."}]},
        }
    )
    rule_ids = {finding.rule_id for finding in findings}
    assert "CONFIG.BOUNDARY.REMOVED" in rule_ids
    with pytest.raises(Exception, match="boundary class cannot be registered as a node"):
        NodeRegistry().register("test.boundary", DemoBoundary, config_schema={}, config_defaults={})

def test_checked_run_writes_reproducible_artifacts_without_raw_inputs(tmp_path) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the artifact fixture."),
                        _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], value=4),
                        _node_call("add", "test.add", "Adds delta to value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], delta=3),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": [
                        {"from": "start", "to": "seed"},
                        {"from": "seed", "to": "add"},
                        {"from": "add", "to": "end"},
                    ],
                    "outputs": [REQ_SPEC("value.out")],
                }
            }
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"secret": "top-secret-value"},
        run_root=tmp_path / "runs",
        run_id="run_001",
    )
    assert result.run_id == "run_001"
    assert result.context.get("value.out")["value"] == 7
    expected_files = {
        "input_summary.json",
        "effective_policy.json",
            "compiled_graph.json",
            "health_report.json",
            "graph.txt",
            "graph.mmd",
            "runtime_trace.jsonl",
            "output_summary.json",
        }
    assert expected_files <= {path.name for path in result.run_dir.iterdir()}
    input_summary = json.loads((result.run_dir / "input_summary.json").read_text(encoding="utf-8"))
    assert input_summary["secret"] == {"size": 16, "type": "str"}
    assert "top-secret-value" not in (result.run_dir / "input_summary.json").read_text(encoding="utf-8")
    compiled = json.loads((result.run_dir / "compiled_graph.json").read_text(encoding="utf-8"))
    assert compiled["data_edges"] == []
    assert compiled["mainline_edges"] == [["start", "seed"], ["seed", "add"], ["add", "end"]]
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    graph_txt = (result.run_dir / "graph.txt").read_text(encoding="utf-8")
    for edge in compiled["effective_edges"]:
        mermaid_to = "n_end" if edge["to"] == "end" else edge["to"]
        assert any(line.strip().startswith(f'{edge["from"]} -->') and line.strip().endswith(f" {mermaid_to}") for line in graph_mmd.splitlines())
        assert f'{edge["from"]} ----> {edge["to"]}' in graph_txt
    assert "---------- data ----------" in graph_mmd
    assert "data: Value Out" in graph_mmd
    assert "TOPOLOGY FLOWCHART" in graph_txt
    assert "provides=value.out" in graph_txt
    if is_mermaid_svg_renderer_available():
        graph_svg = (result.run_dir / "graph.svg").read_text(encoding="utf-8")
        assert "<svg" in graph_svg
        assert "graph.svg.error.txt" not in {path.name for path in result.run_dir.iterdir()}
    trace_lines = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [event["node"] for event in trace_lines if event["kind"] == "node"] == ["start", "seed", "add", "end"]
    assert trace_lines[-1]["kind"] == "runtime_summary"
    assert "top-secret-value" not in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8")
    assert not (result.run_dir / "boundary_trace.jsonl").exists()
