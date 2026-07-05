from tests.unit.strict_support import *

def test_checked_run_refuses_failed_health_before_runtime(tmp_path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [_node_call("missing", "test.missing", "References an unknown node type.", provides=[PROV_SPEC("value.out")])]}}),
        encoding="utf-8",
    )
    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="bad_run")
    result = exc_info.value.result
    assert result.health.status == "FAIL"
    assert any(error.rule_id == "NODE.TYPE.UNKNOWN" for error in result.health.errors)
    assert (result.run_dir / "health_report.json").exists()
    assert (result.run_dir / "effective_policy.json").exists()
    assert not (result.run_dir / "boundary_trace.jsonl").exists()
    health_payload = json.loads((result.run_dir / "health_report.json").read_text(encoding="utf-8"))
    assert health_payload["errors"][0]["failure_layer"] == "topology"
    assert health_payload["effective_policy"]["sources"] == ["kernel.default_policy"]
    assert (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8") == ""


def test_node_registration_requires_config_spec() -> None:
    with pytest.raises(Exception, match="config_schema"):
        NodeRegistry().register("test.seed", SeedNode)


def test_node_config_defaults_and_call_overrides_are_passed_to_runtime() -> None:
    pipeline = _seed_add_pipeline(add={"config": {"delta": 4}})
    pipeline["outputs"] = [REQ_SPEC("value.in"), REQ_SPEC("value.out")]
    graph = parse_graph_config({"pipeline": pipeline})
    context = PipelineRuntime(graph, registry=_registry()).run({})
    assert context.get("value.in")["value"] == 1
    assert context.get("value.out")["value"] == 5


def test_execution_plan_binds_node_instance_and_params_once() -> None:
    CountingInitNode.instances = 0
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the counting fixture."),
                    _node_call("count", "test.counting_init", "Produces configured value.out.", provides=[PROV_SPEC("value.out")], config={"value": 9}),
                    _node_call("end", "test.start", "Ends the compiled branch fixture."),
                ],
                "edges": _edge_chain("start", "count", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())

    assert runtime._plan.frame("count").params["value"] == 9
    assert CountingInitNode.instances == 1
    assert runtime.run({}).get("value.out")["value"] == 9
    assert runtime.run({}).get("value.out")["value"] == 9
    assert CountingInitNode.instances == 1


def test_execution_plan_prebuilds_nodeset_subplan_with_overrides() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                        pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset override fixture."),
                    _node_call(
                        "composite",
                        "nodeset.math.add_one",
                        "Calls add-one with inner override.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                        node_configs={"add": {"delta": 6}},
                    ),
                    _node_call("end", "test.start", "Ends the compiled branch fixture."),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())
    frame = runtime._plan.frame("composite")

    assert frame.is_nodeset
    assert frame.subplan is not None
    assert frame.subplan.frame("add").params["delta"] == 6
    assert runtime.run({"value.in": 2}).get("value.out")["value"] == 8


def test_nodeset_runner_reuses_cached_subruntime() -> None:
    CountingInitNode.instances = 0
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "count.once",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("start", "test.start", "Starts the count nodeset."),
                            _node_call("count", "test.counting_init", "Produces configured value.out.", provides=[PROV_SPEC("value.out")], config={"value": 5}),
                            _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                        ],
                        "edges": _edge_chain("start", "count", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the cached nodeset fixture."),
                    _node_call("composite", "nodeset.count.once", "Calls count-once nodeset.", provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.start", "Ends the compiled branch fixture."),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    runtime = PipelineRuntime(graph, registry=_registry())
    assert CountingInitNode.instances == 1

    assert runtime.run({}).get("value.out")["value"] == 5
    nested = runtime._nodeset_runtimes["composite"]
    assert runtime.run({}).get("value.out")["value"] == 5
    assert runtime._nodeset_runtimes["composite"] is nested
    assert CountingInitNode.instances == 1


def test_nodeset_inputs_and_exports_preserve_object_reference() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "identity.object",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "inputs": [PROV_SPEC("value.in")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts the identity nodeset."),
                            _node_call("identity", "test.identity_object", "Passes value.in through.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                            _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                        ],
                        "edges": _edge_chain("start", "identity", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the object reference fixture."),
                    _node_call("composite", "nodeset.identity.object", "Calls identity nodeset.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    value = NoDeepcopyObject()
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": value})

    assert context.get("value.out")["value"] is value


def test_node_config_invalid_override_fails_health_before_runtime() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces invalid value.in.", provides=[PROV_SPEC("value.in")], value="bad"),
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert any(error.rule_id == "NODE.CONFIG.INVALID" for error in report.errors)


def test_checked_run_refuses_planned_architecture(tmp_path) -> None:
    config_path = tmp_path / "planned.json"
    config_path.write_text(
        json.dumps(
            {
                "nodesets": [
                    {
                        "name": "a",
                        "display_name": "A",
                        "category": "test",
                        "description": "Planned architecture nodeset.",
                        "version": "0.1.0",
                        "purity": "pure",
                        "status": "planned",
                    }
                ],
                "pipeline": {
                    "nodes": [
                        _node_call("a", "nodeset.a", "Calls planned architecture nodeset.", status="planned", flow_kind="predefined"),
                    ]
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CheckedRunError) as exc_info:
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="planned_run")

    result = exc_info.value.result
    assert result.health.status == "FAIL"
    assert any(error.rule_id == "GRAPH.PLANNED.NODE_IN_RUN" for error in result.health.errors)
    assert "planned" in (result.run_dir / "graph.mmd").read_text(encoding="utf-8")
    assert "PLANNED" in (result.run_dir / "graph.txt").read_text(encoding="utf-8")


def test_nodeset_call_can_override_inner_node_config_independently() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                )
            ],
            "pipeline": {
                    "inputs": [PROV_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the nodeset override fixture."),
                        _node_call(
                            "composite",
                            "nodeset.math.add_one",
                            "Calls add-one with an inner override.",
                            requires=[REQ_SPEC("value.in")],
                            provides=[PROV_SPEC("value.out")],
                            node_configs={"add": {"delta": 5}},
                        ),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": _edge_chain("start", "composite", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": 2})
    assert context.get("value.out")["value"] == 7


class NoDeepcopyObject:
    def __deepcopy__(self, memo):
        raise AssertionError("should not deepcopy runtime objects")


class LoopCopyNode:
    NODE_INFO = NodeInfo("test.loop_copy", "Loop Copy", "test", "Copies value.out into the next value.in slot.", "0.1.0", "process")
    CONTRACT = NodeContract(
        requires=(DataRequirement("value.out", "exactly_one"),),
        provides=(DataProvider("value.loop", "value.in"),),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.loop": ("next loop input",)},
        output_schema={"value.loop": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"value.loop": inputs["value.out"]["value"]}


def test_runtime_passes_non_deepcopy_object_by_reference() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the object reference fixture."),
                    _node_call("identity", "test.identity_object", "Passes value.in through.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "identity", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    value = NoDeepcopyObject()
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": value})
    assert context.get("value.out")["value"] is value


def test_checked_run_writes_runtime_failure_trace(tmp_path) -> None:
    config_path = tmp_path / "runtime_fail.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the runtime failure fixture."),
                        _node_call("bad", "test.runtime_fail", "Fails at runtime.", provides=[PROV_SPEC("value.out")], config={"fail": True}),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": _edge_chain("start", "bad", "end"),
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="boom"):
        run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="runtime_fail")
    trace_lines = [
        json.loads(line)
        for line in (tmp_path / "runs" / "runtime_fail" / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    failed = next(line for line in trace_lines if line["kind"] == "node_failed")
    assert "boom" in failed["failure"]
    assert trace_lines[-1]["kind"] == "runtime_summary"


def test_runtime_options_boundary_trace_records_only_boundaries() -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary"))

    context = runtime.run({})

    assert context.get("value.in")["value"] == 1
    assert [event["kind"] for event in runtime.trace.events] == ["run_start", "type_resolve", "run_end"]
    assert runtime.trace.exec_order == ["start", "seed", "end"]
    assert runtime.trace.current_node == "end"


def test_runtime_options_off_keeps_summary_without_events() -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="off"))

    context = runtime.run({})

    assert context.get("runtime.events") == []
    assert context.get("runtime.current_node") == "end"
    assert context.get("runtime.stop_reason") == "completed"
    assert context.get("runtime.exception") == ""


def test_runtime_options_block_executes_linear_plan() -> None:
    graph = parse_graph_config({"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})})

    context = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(execution="block")).run({})

    assert context.get("value.out")["value"] == 5
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "end"]


def test_runtime_options_compiled_executes_linear_block(monkeypatch) -> None:
    graph = parse_graph_config({"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})})

    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert runtime._plan.blocks == ()
    context = runtime.run({})

    assert context.get("value.out")["value"] == 5
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "end"]
    assert context.get("runtime.edge_executions") == {"start->seed": 1, "seed->add": 1, "add->end": 1}
    assert [event["kind"] for event in context.get("runtime.events")] == ["run_start", "type_resolve", "type_resolve", "run_end"]


def test_runtime_options_compiled_runs_generated_block_when_node_hooks_enabled(monkeypatch) -> None:
    graph = parse_graph_config({"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})})

    calls = []

    def before_node(self, name, node_type, input_summary):
        calls.append(("before", name))

    def after_node(self, name, node_type, output_summary):
        calls.append(("after", name))

    plugin = type("NodeHookPlugin", (), {"name": "node_hook", "before_node": before_node, "after_node": after_node})()
    plugin_registry = PluginRegistry()
    plugin_registry.register(plugin, plugin_type="runtime")
    context = PipelineRuntime(
        graph,
        registry=_registry(),
        plugin_registry=plugin_registry,
        runtime_options=RuntimeOptions(trace="boundary", node_hooks=True, execution="compiled"),
    ).run({})

    assert context.get("value.out")["value"] == 5
    assert [event["kind"] for event in context.get("runtime.events")] == ["run_start", "type_resolve", "type_resolve", "run_end"]
    assert calls == [
        ("before", "start"),
        ("after", "start"),
        ("before", "seed"),
        ("after", "seed"),
        ("before", "add"),
        ("after", "add"),
        ("before", "end"),
        ("after", "end"),
    ]


def test_runtime_options_compiled_full_trace_records_node_events(monkeypatch) -> None:
    graph = parse_graph_config({"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})})

    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="full", node_hooks=False, execution="compiled"))
    assert runtime._plan.blocks == ()
    context = runtime.run({})

    assert context.get("value.out")["value"] == 5
    event_kinds = [event["kind"] for event in context.get("runtime.events")]
    assert event_kinds == ["node", "node", "type_resolve", "node", "type_resolve", "node"]
    assert [event["node"] for event in context.get("runtime.events") if event["kind"] == "node"] == ["start", "seed", "add", "end"]
    assert context.get("runtime.edge_executions") == {"start->seed": 1, "seed->add": 1, "add->end": 1}


def test_runtime_options_compiled_failure_records_node_and_block_failed() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                        _node_call("start", "test.start", "Starts the compiled failure fixture."),
                        _node_call("bad", "test.runtime_fail", "Fails in a compiled block.", provides=[PROV_SPEC("value.out")], config={"fail": True}),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "bad", "end"),
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run({})

    assert runtime.trace.current_node == "bad"
    assert [event["kind"] for event in runtime.trace.events] == ["run_start", "node_failed"]
    assert "boom" in runtime.trace.events[1]["failure"]


def test_runtime_options_compiled_executes_decision_branch(monkeypatch) -> None:
    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the compiled branch fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.", provides=[PROV_SPEC("value.in")], config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Chooses the route.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.copy", "Copies value.out for a potential repeat branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy", "value.in")]),
                    _node_call("end", "test.start", "Ends the compiled branch fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "add"},
                    {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert runtime._plan.blocks == ()
    context = runtime.run({})

    assert context.get("value.out")["value"] == 2
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "route", "end"]
    assert context.get("runtime.edge_executions") == {
        "start->seed": 1,
        "seed->add": 1,
        "add->route": 1,
        "route->end": 1,
    }


def test_runtime_options_compiled_executes_decision_loop(monkeypatch) -> None:
    class DoneCheckNode:
        NODE_INFO = NodeInfo("test.done_check", "Done Check", "test", "Checks loop completion.", "0.1.0", "decision")
        CONTRACT = NodeContract(
            requires=(DataRequirement("value.out", "exactly_one"),),
            provides=(DataProvider("loop.done", "loop.done"), DataProvider("value.loop", "value.in")),
            output_schema={"loop.done": {"type": "boolean"}},
            params_schema={"target": {"type": "number"}},
        )

        def run_pure(self, inputs, params):
            value = inputs["value.out"]["value"]
            return {"loop.done": value >= params.get("target", 3), "value.loop": value}

    registry = _registry()
    register_node(registry, "test.done_check", DoneCheckNode, {"target": {"type": "number"}}, {"target": 3})
    graph = _decision_loop_graph(target=3)
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    context = runtime.run({})

    assert context.get("runtime.stop_reason") == "no_ready_nodes"
    assert list(context.get("runtime.exec_order")) == ["start", "seed"]
    assert context.get("runtime.edge_executions") == {"start->seed": 1, "seed->add": 1}


def test_runtime_options_compiled_decision_loop_respects_max_steps() -> None:
    class NeverDoneNode:
        NODE_INFO = NodeInfo("test.never_done", "Never Done", "test", "Never exits loop.", "0.1.0", "decision")
        CONTRACT = NodeContract(
            requires=(DataRequirement("value.out", "exactly_one"),),
            provides=(DataProvider("loop.done", "loop.done"), DataProvider("value.loop", "value.in")),
            output_schema={"loop.done": {"type": "boolean"}},
        )

        def run_pure(self, inputs, params):
            return {"loop.done": False, "value.loop": inputs["value.out"]["value"]}

    registry = _registry()
    register_node(registry, "test.done_check", NeverDoneNode, {"target": {"type": "number"}}, {"target": 3})
    graph = _decision_loop_graph(target=3, max_steps=1)
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))

    with pytest.raises(PipelineRuntimeError, match="max_steps=1"):
        runtime.run({})

    assert runtime.trace.stop_reason == "max_steps"
    assert runtime.trace.step_count == 1


def test_runtime_options_compiled_falls_back_around_async_barrier() -> None:
    class OutToNextNode:
        NODE_INFO = NodeInfo("test.out_to_next", "Out To Next", "test", "Copies value.out to value.next.", "0.1.0", "process")
        CONTRACT = NodeContract(
            requires=(DataRequirement("value.out", "exactly_one"),),
            provides=(DataProvider("value.next", "value.next"),),
        )

        def run_pure(self, inputs, params):
            return {"value.next": inputs["value.out"]["value"]}

    class NextEndNode:
        NODE_INFO = NodeInfo("test.next_end", "Next End", "test", "Ends after value.next.", "0.1.0", "terminal")
        CONTRACT = NodeContract(requires=(DataRequirement("value.next", "exactly_one"),))

        def run_pure(self, inputs, params):
            return {}

    registry = _registry()
    register_node(registry, "test.out_to_next", OutToNextNode)
    register_node(registry, "test.next_end", NextEndNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the async barrier fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], config={"value": 4}),
                    _node_call("async_add", "test.add", "Adds asynchronously.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], result_key="value.out", config={"delta": 3}, **{"async": "result_key"}),
                    _node_call("out_to_next", "test.out_to_next", "Copies value.out to value.next.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.next")]),
                    _node_call("end", "test.next_end", "Consumes value.next.", requires=[REQ_SPEC("value.next")]),
                ],
                "edges": _edge_chain("start", "seed", "async_add", "out_to_next", "end"),
                "outputs": [REQ_SPEC("value.next")],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert runtime._plan.blocks == ()
    interpreted_nodes = []
    original_run_node = PipelineRuntime._run_node

    def spy_run_node(self, node_name, context):
        interpreted_nodes.append(node_name)
        return original_run_node(self, node_name, context)

    PipelineRuntime._run_node = spy_run_node
    try:
        context = runtime.run({})
    finally:
        PipelineRuntime._run_node = original_run_node

    assert interpreted_nodes == ["start", "seed", "async_add", "out_to_next", "end"]
    assert context.get("value.next")["value"] == 7


def _decision_loop_graph(*, target: int, max_steps: int = 20):
    return parse_graph_config(
        {
            "pipeline": {
                "max_steps": max_steps,
                "nodes": [
                    _node_call("start", "test.start", "Starts the decision loop fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.", provides=[PROV_SPEC("value.in")], config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("done", "test.done_check", "Checks whether the loop is done.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("loop.done"), PROV_SPEC("value.loop", "value.in")], config={"target": target}),
                    _node_call("end", "test.start", "Ends the decision loop fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "done"},
                    {"from": "done", "to": "end", "when": "loop.done == true"},
                    {"from": "done", "to": "add", "when": "loop.done == false"},
                ],
            }
        }
    )


def test_runtime_options_block_executes_simple_conditional_route() -> None:
    registry = _registry()
    register_node(registry, "test.route", RouteNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the conditional route fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.", provides=[PROV_SPEC("value.in")], config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                    _node_call("route", "test.route", "Chooses the route.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                    _node_call("copy", "test.copy", "Copies value.out for a potential repeat branch.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.copy", "value.in")]),
                    _node_call("end", "test.start", "Ends the conditional route fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "seed", "to": "add"},
                    {"from": "add", "to": "route"},
                    {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                    {"from": "copy", "to": "add"},
                    {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(execution="block")).run({})

    assert context.get("value.out")["value"] == 2
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "route", "end"]


def test_runtime_options_rejects_unknown_execution() -> None:
    with pytest.raises(ValueError, match="runtime execution"):
        RuntimeOptions(execution="native")


def test_async_result_key_joins_when_required() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the async join fixture."),
                    _node_call("seed", "test.seed", "Produces value.in asynchronously.", provides=[PROV_SPEC("value.in")], result_key="value.in", config={"value": 4}, **{"async": "result_key"}),
                    _node_call("add", "test.add", "Adds delta to value.in.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], config={"delta": 3}),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "seed", "add", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=_registry()).run({})

    assert context.get("value.out")["value"] == 7
    assert "async_result_join" in [event["kind"] for event in context.get("runtime.events")]


def test_async_result_key_not_joined_when_unconsumed() -> None:
    class SlowResultNode:
        NODE_INFO = NodeInfo("test.slow_result", "Slow Result", "test", "Slow result-key async task.", "0.1.0", "process")
        CONTRACT = NodeContract(provides=(DataProvider("value.async", "value.async"),), examples=({"inputs": {}, "params": {}},))

        def run_pure(self, inputs, params):
            time.sleep(0.2)
            return {"value.async": 99}

    registry = _registry()
    register_node(registry, "test.slow_result", SlowResultNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the unconsumed async fixture."),
                    _node_call("slow", "test.slow_result", "Produces an unconsumed async result.", provides=[PROV_SPEC("value.async")], result_key="value.async", **{"async": "result_key"}),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], config={"value": 2}),
                    _node_call("end", "test.in_end", "Consumes value.in.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "slow", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary")).run({})

    assert context.get("value.in")["value"] == 2
    assert not context.exists("value.async")
    assert "async_result_join" not in [event["kind"] for event in context.get("runtime.events")]


def test_async_detached_failure_records_warning_and_completes() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the detached failure fixture."),
                    _node_call("metrics", "test.runtime_fail", "Fails in a detached task.", provides=[PROV_SPEC("value.out")], config={"fail": True}, **{"async": "detached"}),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], config={"value": 2}),
                    _node_call("end", "test.in_end", "Consumes value.in.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "metrics", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=_registry()).run({})

    assert context.get("runtime.stop_reason") == "completed"
    assert context.get("value.in")["value"] == 2
    events = context.get("runtime.events")
    assert any(event["kind"] == "async_detached_failed" and "boom" in event["failure"] for event in events)


def test_async_result_key_requires_declared_output() -> None:
    with pytest.raises(GraphConfigError, match="result_key must be declared"):
        parse_graph_config(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the bad async fixture."),
                        _node_call("seed", "test.seed", "Produces value.in with an invalid result key.", provides=[PROV_SPEC("value.in")], result_key="value.missing", **{"async": "result_key"}),
                        _node_call("end", "test.in_end", "Consumes value.in.", requires=[REQ_SPEC("value.in")]),
                    ],
                    "edges": _edge_chain("start", "seed", "end"),
                }
            }
        )


def test_config_schema_reports_async_result_key_not_in_provides() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces value.in with an invalid result key.", provides=[PROV_SPEC("value.in")], result_key="value.missing", **{"async": "result_key"})
                ]
            }
        }
    )

    assert any(finding.rule_id == "CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY" and "declared in provides" in finding.message for finding in findings)


def test_runtime_no_longer_has_json_snapshot_output_mode() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the NaN output fixture."),
                    _node_call("set", "test.nan_output", "Produces NaN value.out.", provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "set", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=_registry()).run({})
    assert str(context.get("value.out")["value"]) == "nan"


def test_async_nodeset_result_key_joins_when_required() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 2}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the async nodeset fixture."),
                    _node_call("composite", "nodeset.math.add_one", "Calls add-one asynchronously.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")], result_key="value.out", **{"async": "result_key"}),
                    _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": 5})

    assert context.get("value.out")["value"] == 7
    assert "async_result_join" in [event["kind"] for event in context.get("runtime.events")]
    assert "composite.add" in context.get("runtime.qualified_exec_order")


def test_async_detached_timeout_records_warning_and_does_not_block() -> None:
    class SlowNode:
        NODE_INFO = NodeInfo("test.slow", "Slow", "test", "Slow detached task.", "0.1.0", "process")
        CONTRACT = NodeContract(provides=(DataProvider("value.out", "value.out"),), examples=({"inputs": {}, "params": {}},))

        def run_pure(self, inputs, params):
            time.sleep(0.05)
            return {"value.out": 1}

    registry = _registry()
    register_node(registry, "test.slow", SlowNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the detached timeout fixture."),
                    _node_call("slow", "test.slow", "Runs a slow detached task.", provides=[PROV_SPEC("value.out")], **{"async": "detached"}),
                    _node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")], config={"value": 3}),
                    _node_call("end", "test.in_end", "Consumes value.in.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": _edge_chain("start", "slow", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(async_flush_timeout=0)).run({})

    assert context.get("value.in")["value"] == 3
    assert any(event["kind"] == "async_detached_timeout" for event in context.get("runtime.events"))


def test_runtime_options_node_hooks_false_skips_per_node_hooks(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "runtime_plugin.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
from vibeflow import PluginInfo
MARKER = Path({str(marker_path)!r})
def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")
class RuntimePlugin:
    PLUGIN_INFO = PluginInfo("runtime_hook", "runtime", "Runtime Hook", "test", "Records runtime hook calls.", "0.1.0")
    name = "runtime_hook"
    def before_run(self, state):
        record({{"hook": "before_run"}})
    def before_node(self, name, node_type, input_summary):
        record({{"hook": "before_node"}})
    def after_node(self, name, node_type, output_summary):
        record({{"hook": "after_node"}})
    def after_run(self, state, trace):
        record({{"hook": "after_run"}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "class": "RuntimePlugin", "type": "runtime"}],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )

    run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="node_hooks_off", runtime_options=RuntimeOptions(node_hooks=False))

    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert hooks == ["before_run", "after_run"]


def test_runtime_options_hook_granularity_controls_nodeset_and_block_hooks(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "runtime_plugin.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
from vibeflow import PluginInfo
MARKER = Path({str(marker_path)!r})
def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")
class RuntimePlugin:
    PLUGIN_INFO = PluginInfo("runtime_hook", "runtime", "Runtime Hook", "test", "Records runtime hook calls.", "0.1.0")
    name = "runtime_hook"
    def before_nodeset(self, name, node_type):
        record({{"hook": "before_nodeset"}})
    def after_nodeset(self, name, node_type):
        record({{"hook": "after_nodeset"}})
    def before_block(self, name, nodes):
        record({{"hook": "before_block"}})
    def after_block(self, name, nodes):
        record({{"hook": "after_block"}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [{"module": str(plugin_path), "class": "RuntimePlugin", "type": "runtime"}],
                "pipeline": _seed_add_pipeline(add={"config": {"delta": 4}}),
            }
        ),
        encoding="utf-8",
    )

    run_checked(
        config_path,
        registry=_registry(),
        run_root=tmp_path / "runs",
        run_id="block_hooks",
        runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, nodeset_hooks=False, block_hooks=True, execution="compiled"),
    )

    assert not marker_path.exists()

def test_checked_run_trace_records_nodeset_enter_exit(tmp_path) -> None:
    config_path = tmp_path / "nodeset_workflow.json"
    config_path.write_text(
        json.dumps(
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
                        _node_call("start", "test.start", "Starts the nodeset trace fixture."),
                        _node_call("composite", "nodeset.math.add_one", "Calls add-one nodeset.", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                        _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                    ],
                    "edges": _edge_chain("start", "composite", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
        }
        ),
        encoding="utf-8",
    )
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value.in": 2},
        run_root=tmp_path / "runs",
        run_id="nodeset_run",
    )
    assert result.context.get("value.out")["value"] == 3
    trace_lines = [json.loads(line) for line in (result.run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    trace_kinds = [line["kind"] for line in trace_lines]
    assert "nodeset_enter" in trace_kinds
    assert "nodeset_exit" in trace_kinds
    assert "composite.add" in trace_lines[-1]["qualified_exec_order"]
    assert trace_lines[-1]["step_count"] == 3
    assert trace_lines[-1]["total_step_count"] == 6


def test_runtime_trace_records_nested_nodeset_qualified_paths() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "inner.flow",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_seed_add_pipeline(),
                ),
                _nodeset_config(
                    "outer.flow",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("start", "test.start", "Starts outer flow."),
                            _node_call("inner_call", "nodeset.inner.flow", "Calls inner flow.", provides=[PROV_SPEC("value.out")]),
                            _node_call("end", "test.out_end", "Consumes outer value.out.", requires=[REQ_SPEC("value.out")]),
                        ],
                        "edges": _edge_chain("start", "inner_call", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                ),
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts nested trace fixture."),
                    _node_call("outer_call", "nodeset.outer.flow", "Calls outer flow.", provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes final value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "outer_call", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="full")).run({})

    assert context.get("value.out")["value"] == 2
    assert "outer_call.inner_call.add" in context.get("runtime.qualified_exec_order")
    node_events = [event for event in context.get("runtime.events") if event["kind"] == "node"]
    inner_add = next(event for event in node_events if event["qualified_node"] == "outer_call.inner_call.add")
    assert inner_add["path"] == ["outer_call", "inner_call", "add"]
    assert inner_add["depth"] == 2


def test_runtime_trace_counts_nodeset_internal_loop_steps() -> None:
    class ThresholdRouteNode:
        NODE_INFO = NodeInfo("test.threshold_route", "Threshold Route", "test", "Routes until a threshold.", "0.1.0", "decision")
        CONTRACT = NodeContract(
            requires=(DataRequirement("value.out", "exactly_one"),),
            provides=(DataProvider("flow.route", "flow.route"),),
            output_schema={"flow.route": {"type": "string"}},
        )

        def run_pure(self, inputs, params):
            value = inputs["value.out"]["value"]
            return {"flow.route": "done" if value >= 3 else "again"}

    class LoopCopyNode:
        NODE_INFO = NodeInfo("test.loop_copy", "Loop Copy", "test", "Copies value.out back to loop input.", "0.1.0", "process")
        CONTRACT = NodeContract(
            requires=(DataRequirement("value.out", "exactly_one"),),
            provides=(DataProvider("value.loop", "value.in"),),
            output_schema={"value.loop": {"type": "number"}},
        )

        def run_pure(self, inputs, params):
            return {"value.loop": inputs["value.out"]["value"]}

    registry = _registry()
    register_node(registry, "test.threshold_route", ThresholdRouteNode)
    register_node(registry, "test.loop_copy", LoopCopyNode)
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.flow",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "max_steps": 10,
                        "nodes": [
                            _node_call("start", "test.start", "Starts inner loop."),
                            _node_call("seed", "test.seed", "Produces loop seed.", provides=[PROV_SPEC("value.in")], config={"value": 1}),
                            _node_call(
                                "add",
                                "test.add",
                                "Increments the loop value.",
                                requires=[REQ_SPEC("value.in")],
                                provides=[PROV_SPEC("value.out")],
                            ),
                            _node_call("route", "test.threshold_route", "Routes the loop.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("flow.route")]),
                            _node_call("copy", "test.loop_copy", "Copies value.out back to value.in.", requires=[REQ_SPEC("value.out")], provides=[PROV_SPEC("value.loop", "value.in")]),
                            _node_call("end", "test.start", "Ends the inner loop."),
                        ],
                        "edges": [
                            {"from": "start", "to": "seed"},
                            {"from": "seed", "to": "add"},
                            {"from": "add", "to": "route"},
                            {"from": "add", "to": "copy"},
                            {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                            {"from": "copy", "to": "add"},
                            {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                        ],
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts loop trace fixture."),
                    _node_call("loop_call", "nodeset.loop.flow", "Calls loop flow.", provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes final value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "loop_call", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="full")).run({})

    assert context.get("value.out")["value"] == 3
    assert context.get("runtime.step_count") == 3
    assert context.get("runtime.total_step_count") == 11
    assert context.get("runtime.qualified_node_runs")["loop_call.add"] == 2
    assert context.get("runtime.qualified_exec_order").count("loop_call.add") == 2


def test_runtime_trace_preserves_nested_failure_path() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "fail.flow",
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "nodes": [
                            _node_call("start", "test.start", "Starts failing nodeset."),
                            _node_call("bad", "test.runtime_fail", "Fails inside nodeset.", provides=[PROV_SPEC("value.out")], config={"fail": True}),
                            _node_call("end", "test.out_end", "Consumes value.out.", requires=[REQ_SPEC("value.out")]),
                        ],
                        "edges": _edge_chain("start", "bad", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts nested failure fixture."),
                    _node_call("composite", "nodeset.fail.flow", "Calls failing nodeset.", provides=[PROV_SPEC("value.out")]),
                    _node_call("end", "test.out_end", "Consumes final value.out.", requires=[REQ_SPEC("value.out")]),
                ],
                "edges": _edge_chain("start", "composite", "end"),
            },
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="full"))

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run({})

    failed = [event for event in runtime.trace.events if event["kind"] == "node_failed" and event["node"] == "bad"]
    assert failed[0]["path"] == ["composite", "bad"]
    assert failed[0]["qualified_node"] == "composite.bad"
    assert any(event["kind"] == "nodeset_failed" and event["path"] == ["composite"] for event in runtime.trace.events)


def test_cli_train_profile_sets_async_flush_timeout_and_allows_override() -> None:
    import argparse
    from vibeflow.cli import _add_runtime_options, _runtime_options_from_args

    parser = argparse.ArgumentParser()
    _add_runtime_options(parser)

    train_options = _runtime_options_from_args(parser.parse_args(["--runtime-profile", "train"]))
    override_options = _runtime_options_from_args(parser.parse_args(["--runtime-profile", "train", "--async-flush-timeout", "1.5"]))

    assert train_options.async_flush_timeout == 30.0
    assert override_options.async_flush_timeout == 1.5


def test_cli_run_uses_checked_run_and_refuses_without_registered_nodes(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.", provides=[PROV_SPEC("value.in")])]}}),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "run",
            "--config",
            str(config_path),
            "--run-root",
            str(tmp_path / "runs"),
            "--run-id",
            "cli_run",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "FAIL"
    run_dir = Path(payload["run_dir"])
    assert (run_dir / "health_report.json").exists()
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.TYPE.UNKNOWN"

def test_cli_run_succeeds_with_global_registry_and_writes_artifacts(tmp_path, capsys) -> None:
    from vibeflow.registry import GLOBAL_NODE_REGISTRY

    original = dict(getattr(GLOBAL_NODE_REGISTRY, "_registry"))
    original_config_specs = dict(getattr(GLOBAL_NODE_REGISTRY, "_config_specs"))
    register_node(GLOBAL_NODE_REGISTRY, "test.start", StartNode, overwrite=True)
    register_node(GLOBAL_NODE_REGISTRY, "test.in_end", InEndNode, overwrite=True)
    register_node(GLOBAL_NODE_REGISTRY, "test.seed", SeedNode, {"value": {"type": "number"}}, {"value": 1}, overwrite=True)
    try:
        config_path = tmp_path / "workflow.json"
        input_path = tmp_path / "input.json"
        config_path.write_text(
            json.dumps({"pipeline": _seed_only_pipeline(seed={"value": 9})}),
            encoding="utf-8",
        )
        input_path.write_text("{}", encoding="utf-8")
        code = cli_main(
            [
                "run",
                "--config",
                str(config_path),
                "--input",
                str(input_path),
                "--run-root",
                str(tmp_path / "runs"),
                "--run-id",
                "cli_ok",
                "--runtime-profile",
                "train",
            ]
        )
        payload = json.loads(capsys.readouterr().out)
        plan_code = cli_main(
            [
                "run",
                "--config",
                str(config_path),
                "--input",
                str(input_path),
                "--run-root",
                str(tmp_path / "runs"),
                "--run-id",
                "cli_plan_override",
                "--runtime-profile",
                "train",
                "--execution",
                "plan",
            ]
        )
        plan_payload = json.loads(capsys.readouterr().out)
    finally:
        getattr(GLOBAL_NODE_REGISTRY, "_registry").clear()
        getattr(GLOBAL_NODE_REGISTRY, "_registry").update(original)
        getattr(GLOBAL_NODE_REGISTRY, "_config_specs").clear()
        getattr(GLOBAL_NODE_REGISTRY, "_config_specs").update(original_config_specs)
    assert code == 0
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    for name in ("compiled_graph.json", "health_report.json", "graph.txt", "graph.mmd", "runtime_trace.jsonl", "output_summary.json"):
        assert (run_dir / name).exists()
    trace_kinds = [json.loads(line)["kind"] for line in (run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert trace_kinds == ["run_start", "type_resolve", "run_end", "runtime_summary"]
    assert plan_code == 0
    assert plan_payload["status"] in {"PASS", "CONCERNS"}
    plan_run_dir = Path(plan_payload["run_dir"])
    plan_trace_kinds = [json.loads(line)["kind"] for line in (plan_run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert plan_trace_kinds == ["run_start", "type_resolve", "run_end", "runtime_summary"]
    if is_mermaid_svg_renderer_available():
        assert (run_dir / "graph.svg").exists()


def test_distribution_kernel_manifest_allows_root_guides_to_be_customized(tmp_path) -> None:
    import subprocess
    import sys

    from build_distribution import build_distribution

    output = tmp_path / "distribution"
    build_distribution(output)
    manifest = (output / "kernel" / "MANIFEST.sha256").read_text(encoding="utf-8")
    manifest_paths = {line.split("  ", 1)[1] for line in manifest.splitlines() if line.strip()}

    assert "AGENTS.md" not in manifest_paths
    assert "README.md" not in manifest_paths
    assert {"run.py", "kernel/README.md", "kernel/vibeflow-kernel.zip"} <= manifest_paths

    (output / "AGENTS.md").write_text("# Custom project agent guide\n", encoding="utf-8")
    (output / "README.md").write_text("# Custom project readme\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "run.py", "verify-kernel"],
        cwd=output,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stderr
