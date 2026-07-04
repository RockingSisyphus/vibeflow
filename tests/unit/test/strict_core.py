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
    assert any(item.code == "banned_call" for item in violations)

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
            provides=("external.out",),
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
            provides=("external.out",),
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
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"]},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
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
                    {"name": "start", "type": "test.start"},
                    {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    {"name": "route", "type": "test.two_route", "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("flow.route")]},
                    {"name": "end", "type": "test.start"},
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


def test_decision_non_loop_branch_must_reach_end_but_loop_branch_is_skipped() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    {"name": "route", "type": "test.two_route", "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("flow.route")]},
                    {"name": "copy", "type": "test.seed", "provides": [{"key": "value.in.copy", "type": "value.in"}]},
                    {"name": "dead", "type": "test.seed", "provides": [{"key": "value.in.dead", "type": "value.in"}]},
                    {"name": "end", "type": "test.start"},
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "route"},
                    {"from": "route", "to": "dead", "when": "flow.route == 'done'"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert any(item.rule_id == "GRAPH.DECISION.BRANCH_CANNOT_REACH_END" for item in report.errors)


def test_decision_cycle_exit_is_checked_per_scc_not_per_body_decision() -> None:
    registry = _registry()
    register_node(registry, "test.two_route", TwoRouteNode)
    register_node(registry, "test.body_route", BodyRouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    {"name": "controller", "type": "test.two_route", "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("flow.route")]},
                    {"name": "body_route", "type": "test.body_route", "requires": [REQ_SPEC("flow.route")], "provides": [PROV_SPEC("flow.inner")]},
                    {
                        "name": "left_continue",
                        "type": "test.seed",
                        "provides": [{"key": "value.in.left", "type": "value.in"}],
                    },
                    {
                        "name": "right_continue",
                        "type": "test.seed",
                        "provides": [{"key": "value.in.right", "type": "value.in"}],
                    },
                    {"name": "end", "type": "test.start"},
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

    assert not any(item.rule_id == "GRAPH.CYCLE.MISSING_DECISION_EXIT" for item in report.errors)


def test_planned_node_is_concern_not_unknown_type() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "future", "status": "planned", "flow_kind": "process"},
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
                            {"name": "future", "status": "planned", "flow_kind": "process"},
                        ]
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    {"name": "a", "type": "nodeset.a", "provides": ["value.out"]},
                ]
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert report.status == "FAIL"
    assert any(error.rule_id == "GRAPH.PLANNED.PARENT_HAS_PLANNED_CHILD" for error in report.errors)

def test_requires_provides_data_edges_are_diagnostic_and_explicit_flow_runs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                    {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "end"},
                ],
            }
        }
    )
    compiled = GraphCompiler().compile(graph)
    assert ("seed", "add") in [edge.pair for edge in compiled.data_edges]
    assert [edge.pair for edge in compiled.effective_edges] == [("start", "seed"), ("seed", "add"), ("add", "end")]
    context = PipelineRuntime(graph, registry=_registry()).run()
    assert context.get("value.out") == 7

def test_undeclared_cycle_is_rejected() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": ["value.in"],
                "nodes": [
                    {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"]},
                    {"name": "copy", "type": "test.copy", "requires": ["value.out"], "provides": ["value.copy"]},
                ],
                "edges": [{"from": "add", "to": "copy"}, {"from": "copy", "to": "add"}],
            }
        }
    )
    with pytest.raises(GraphCompileError, match="cycle requires decision"):
        GraphCompiler().compile(graph, registry=_registry())

def test_removed_loop_registration_and_edge_limits_are_rejected() -> None:
    with pytest.raises(GraphConfigError, match="pipeline.loops is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}],
                    "loops": [{"name": "counter_loop", "edges": [["seed", "seed"]]}],
                }
            }
        )

    with pytest.raises(GraphConfigError, match="max_executions is removed"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}],
                    "edges": [{"from": "seed", "to": "seed", "max_executions": 2}],
                }
            }
        )

def test_compiler_can_check_registry_node_types() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing"}]}})
    with pytest.raises(GraphCompileError, match="unknown type"):
        GraphCompiler().compile(graph, registry=_registry())

def test_boundary_config_is_removed() -> None:
    with pytest.raises(GraphConfigError, match="boundary is removed"):
        parse_graph_config(
            {
                "boundary": {"type": "test.boundary", "consumes": ["effects.request"], "provides": ["io.result"]},
                "pipeline": {"nodes": [{"name": "seed", "type": "test.seed", "provides": ["value.in"]}]},
            }
        )

def test_registry_namespace_mismatch_is_warning() -> None:
    registry = NodeRegistry()
    _register_fulltext_nodes(registry)
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "rank", "type": "literature.rank_records", "provides": ["value.in"]}]}})
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
            "pipeline": {"nodes": [{"name": "seed", "type": "test.seed"}]},
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
                        {"name": "start", "type": "test.start"},
                        {"name": "seed", "type": "test.seed", "provides": ["value.in"], "value": 4},
                        {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], "delta": 3},
                        {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
                    ],
                    "edges": [
                        {"from": "start", "to": "seed"},
                        {"from": "seed", "to": "add"},
                        {"from": "add", "to": "end"},
                    ],
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
    assert result.context.get("value.out") == 7
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
    assert [edge for edge in compiled["data_edges"] if edge == ["seed", "add"]]
    graph_mmd = (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    graph_txt = (result.run_dir / "graph.txt").read_text(encoding="utf-8")
    for edge in compiled["effective_edges"]:
        mermaid_to = "n_end" if edge["to"] == "end" else edge["to"]
        assert f'{edge["from"]} --> {mermaid_to}' in graph_mmd
        assert f'{edge["from"]} ----> {edge["to"]}' in graph_txt
    assert "provides: value.out" in graph_mmd
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
