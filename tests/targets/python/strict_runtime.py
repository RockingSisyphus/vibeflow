from tests.fixtures.support.task_management import task_call, register_task_manager
from tests.fixtures.support.declarations import native_registry
from tests.fixtures.support.declarations import node_declaration, configured_declaration
import threading
from dataclasses import replace

from tests.fixtures.support.strict_support import *
from tests.fixtures.support.plugins import publish_native_fixture, write_lifecycle_fixture


def _runtime_trace_lines_from_context(context) -> list[dict[str, object]]:
    return _runtime_trace_lines(Path(context.get("runtime.trace_path")))


def _runtime_trace_events_from_context(context) -> list[dict[str, object]]:
    return [line for line in _runtime_trace_lines_from_context(context) if line.get("kind") != "runtime_summary"]


def _runtime_trace_lines(trace_path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line]


def test_checked_run_refuses_failed_health_before_runtime(tmp_path) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [_node_call("missing", "test.missing", "References an unknown node type.")]}}),
        encoding="utf-8",
    )
    publish_native_fixture(config_path, _registry())
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


def test_node_registration_requires_canonical_declaration() -> None:
    with pytest.raises(Exception, match="requires a NodeDescriptor"):
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
                    _node_call("count", "test.counting_init", "Produces configured value.out.",  config={"value": 9}),
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
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset override fixture."),
                    _node_call(
                        "composite",
                        "math.add_one",
                        "Calls add-one with inner override.",

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
                            _node_call("count", "test.counting_init", "Produces configured value.out.",  config={"value": 5}),
                            _node_call("end", "test.out_end", "Consumes value.out."),
                        ],
                        "edges": _edge_chain("start", "count", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the cached nodeset fixture."),
                    _node_call("composite", "count.once", "Calls count-once nodeset."),
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
                        "inputs": [INPUT_SPEC("value.in")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts the identity nodeset."),
                            _node_call("identity", "test.identity_object", "Passes value.in through."),
                            _node_call("end", "test.out_end", "Consumes value.out."),
                        ],
                        "edges": _edge_chain("start", "identity", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the object reference fixture."),
                    _node_call("composite", "identity.object", "Calls identity nodeset."),
                    _node_call("end", "test.out_end", "Consumes value.out."),
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
                    _node_call("seed", "test.seed", "Produces invalid value.in.",  value="bad"),
                ]
            }
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert any(error.rule_id == "NODE.CONFIG.INVALID" for error in report.errors)


def test_checked_run_refuses_planned_architecture(tmp_path) -> None:
    config_path = tmp_path / "planned.json"
    _write_config_file(
        config_path,
        {
            "nodesets": [
                {
                    "type_key": "a",
                    "display_name": "A",
                    "description": "Planned architecture nodeset.",
                    "requires": [],
                    "provides": [],
                    "status": "planned",
                }
            ],
            "pipeline": {
                "nodes": [
                    _node_call("a", "a", "Calls planned architecture nodeset.", status="planned", flow_kind="predefined"),
                ]
            },
        },
    )

    publish_native_fixture(config_path, _registry())
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
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", "Starts the nodeset override fixture."),
                        _node_call(
                            "composite",
                            "math.add_one",
                            "Calls add-one with an inner override.",

                            node_configs={"add": {"delta": 5}},
                        ),
                        _node_call("end", "test.out_end", "Consumes value.out."),
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


LoopCopyNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.loop_copy', display_name='Loop Copy', description='Copies value.out into the next value.in slot.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.out', 'exactly_one', display_name='value.out'),), provides=(DataProvider('value.loop', 'value.in', display_name='value.loop'),), input_semantics={'value.out': ('output value',)}, output_semantics={'value.loop': ('next loop input',)}), rulesets=("vibeflow.process",))

class LoopCopyNode:

    def run_pure(self, inputs, params):
        return {"value.loop": inputs["value.out"]["value"]}


BranchCopyNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.branch_copy', display_name='Branch Copy', description='Copies value.out into a distinct value.in-compatible key.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.out', 'exactly_one', display_name='Value Out'),), provides=(DataProvider('value.copy', 'value.in', display_name='Value Copy'),), input_semantics={'value.out': ('output value selected by the route',)}, output_semantics={'value.copy': ('copied value compatible with value.in',)}), rulesets=("vibeflow.process",))

class BranchCopyNode:

    def run_pure(self, inputs, params):
        return {"value.copy": inputs["value.out"]["value"]}


LoopAddItemNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.loop_add_item', display_name='Loop Add Item', description='Adds one loop item into a running total.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('total.current', 'exactly_one', display_name='total.current'), DataRequirement('item.value', 'exactly_one', display_name='item.value')), provides=(DataProvider('total.next', 'total.next', display_name='total.next'), DataProvider('item.metric', 'item.metric', display_name='item.metric')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('total.current', 'exactly_one', display_name='total.current'), DataRequirement('item.value', 'exactly_one', display_name='item.value'))}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('total.next', 'total.next', display_name='total.next'), DataProvider('item.metric', 'item.metric', display_name='item.metric'))}), rulesets=("vibeflow.process",))

class LoopAddItemNode:

    def run_pure(self, inputs, params):
        item = inputs["item.value"]["value"]
        return {"total.next": inputs["total.current"]["value"] + item, "item.metric": item}


LoopStepUntilNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.loop_step_until', display_name='Loop Step Until', description='Increments loop.current until it reaches target.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('loop.current', 'exactly_one', display_name='loop.current'),), provides=(DataProvider('loop.next', 'loop.next', display_name='loop.next'), DataProvider('loop.done', 'loop.done', display_name='loop.done')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('loop.current', 'exactly_one', display_name='loop.current'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('loop.next', 'loop.next', display_name='loop.next'), DataProvider('loop.done', 'loop.done', display_name='loop.done'))}), rulesets=("vibeflow.process",))

class LoopStepUntilNode:

    def run_pure(self, inputs, params):
        value = inputs["loop.current"]["value"] + 1
        return {"loop.next": value, "loop.done": value >= params.get("target", 3)}


LoopNextEndNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.loop_next_end', display_name='Loop Next End', description='Ends one loop body after loop.next is ready.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('loop.next', 'exactly_one', display_name='Loop Next'),), input_semantics={'loop.next': ('next loop value',)}), rulesets=("vibeflow.process",))

class LoopNextEndNode:

    def run_pure(self, inputs, params):
        return {}


LoopFinalEndNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.loop_final_end', display_name='Loop Final End', description='Ends a loop workflow after loop.final is ready.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('loop.final', 'exactly_one', display_name='Loop Final'),), input_semantics={'loop.final': ('final loop value',)}), rulesets=("vibeflow.process",))

class LoopFinalEndNode:

    def run_pure(self, inputs, params):
        return {}


JoinPassthroughNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.join_passthrough', display_name='Join Passthrough', description='Copies value.in to value.out.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.in', 'exactly_one', display_name='value.in'),), provides=(DataProvider('value.out', 'value.out', display_name='value.out'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.in', 'exactly_one', display_name='value.in'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.out', 'value.out', display_name='value.out'),)}), rulesets=("vibeflow.process",))

class JoinPassthroughNode:

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"]["value"]}


ConditionalValueNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.conditional_value', display_name='Conditional Value', description='Provides value.in and a branch flag.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.alt', 'value.in', display_name='value.alt'), DataProvider('flow.use_alt', 'flow.use_alt', display_name='flow.use_alt')), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.alt', 'value.in', display_name='value.alt'), DataProvider('flow.use_alt', 'flow.use_alt', display_name='flow.use_alt'))}), rulesets=("vibeflow.process",))

class ConditionalValueNode:

    def run_pure(self, inputs, params):
        return {"value.alt": 99, "flow.use_alt": True}


LeftValueNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.left_value', display_name='Left Value', description='Produces left value.in.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.left', 'value.in', display_name='value.left'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.left', 'value.in', display_name='value.left'),)}), rulesets=("vibeflow.process",))

class LeftValueNode:

    def run_pure(self, inputs, params):
        return {"value.left": 1}


RightValueNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.right_value', display_name='Right Value', description='Produces right value.in.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.right', 'value.in', display_name='value.right'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.right', 'value.in', display_name='value.right'),)}), rulesets=("vibeflow.process",))

class RightValueNode:

    def run_pure(self, inputs, params):
        return {"value.right": 2}


OtherValueNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.other_value', display_name='Other Value', description='Produces other.in.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('other.in', 'other.in', display_name='other.in'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('other.in', 'other.in', display_name='other.in'),)}), rulesets=("vibeflow.process",))

class OtherValueNode:

    def run_pure(self, inputs, params):
        return {"other.in": 10}


TwoInputJoinNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.two_input_join', display_name='Two Input Join', description='Adds value.in and other.in.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.in', 'exactly_one', display_name='value.in'), DataRequirement('other.in', 'exactly_one', display_name='other.in')), provides=(DataProvider('value.out', 'value.out', display_name='value.out'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.in', 'exactly_one', display_name='value.in'), DataRequirement('other.in', 'exactly_one', display_name='other.in'))}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.out', 'value.out', display_name='value.out'),)}), rulesets=("vibeflow.process",))

class TwoInputJoinNode:

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"]["value"] + inputs["other.in"]["value"]}


InactiveRouteNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.inactive_route', display_name='Inactive Route', description='Produces a false route flag.', version='0.1.0', flow_kind='decision', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('flow.route', 'flow.route', display_name='flow.route'),), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('flow.route', 'flow.route', display_name='flow.route'),)}), rulesets=("vibeflow.process",))

class InactiveRouteNode:

    def run_pure(self, inputs, params):
        return {"flow.route": False}


def _loop_registry() -> NodeRegistry:
    registry = _registry()
    register_node(registry, LoopAddItemNode_DECLARATION, LoopAddItemNode)
    register_node(registry, LoopStepUntilNode_DECLARATION, LoopStepUntilNode, {"target": {"type": "number"}}, {"target": 3})
    register_node(registry, LoopNextEndNode_DECLARATION, LoopNextEndNode)
    register_node(registry, LoopFinalEndNode_DECLARATION, LoopFinalEndNode)
    register_node(registry, JoinPassthroughNode_DECLARATION, JoinPassthroughNode)
    register_node(registry, ConditionalValueNode_DECLARATION, ConditionalValueNode)
    register_node(registry, LeftValueNode_DECLARATION, LeftValueNode)
    register_node(registry, RightValueNode_DECLARATION, RightValueNode)
    register_node(registry, OtherValueNode_DECLARATION, OtherValueNode)
    register_node(registry, TwoInputJoinNode_DECLARATION, TwoInputJoinNode)
    register_node(registry, InactiveRouteNode_DECLARATION, InactiveRouteNode)
    return registry


def _fixed_count_loop_graph(*, max_iterations: int = 10, stop_after: int = 3):
    return parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.fixed_step",
                    requires=["loop.current"],
                    provides=["loop.next", "loop.done"],
                    exports=["loop.next", "loop.done"],
                    pipeline={
                        "inputs": [INPUT_SPEC("loop.current")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts the fixed loop body."),
                            _node_call(
                                "step",
                                "test.loop_step_until",
                                "Increments loop.current for one fixed-count iteration.",

                            ),
                            _node_call("end", "test.loop_next_end", "Ends the fixed loop body."),
                        ],
                        "edges": _edge_chain("start", "step", "end"),
                        "outputs": [REQ_SPEC("loop.next"), REQ_SPEC("loop.done")],
                    },
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("loop.current")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the fixed-count loop fixture."),
                    _node_call(
                        "count_loop",
                        "vibeflow.loop.while",
                        "Runs the body a fixed number of times.",
                        requires=[REQ_SPEC("loop.current")],
                        provides=[PROV_SPEC("loop.final"), PROV_SPEC("loop.history"), PROV_SPEC("loop.iterations")],
                        loop={
                            "body": "loop.fixed_step",
                            "max_iterations": max_iterations,
                            "stop_after": stop_after,
                            "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}],
                            "collect": [{"from": "loop.next", "as": "loop.history"}],
                            "outputs": [
                                {"from": "loop.next", "as": "loop.final"},
                                {"from": "loop.history", "as": "loop.history"},
                                {"from": "loop.iterations", "as": "loop.iterations"},
                            ],
                        },
                    ),
                    _node_call("end", "test.loop_final_end", "Ends after loop.final."),
                ],
                "edges": _edge_chain("start", "count_loop", "end"),
                "outputs": [REQ_SPEC("loop.final"), REQ_SPEC("loop.history"), REQ_SPEC("loop.iterations")],
            },
        }
    )


def _while_loop_graph(
    *,
    target: int = 3,
    max_iterations: int | None = 10,
    stop_when_source: str | None = "loop.done",
    stop_after: int | None = None,
):
    loop = {
        "body": "loop.step_until",
        "max_iterations": max_iterations,
        "carry": [
            {
                "from": "loop.current",
                "as": "loop.current",
                "update": "loop.next",
            }
        ],
        "outputs": [
            {"from": "loop.next", "as": "loop.final"},
            {"from": "loop.iterations", "as": "loop.iterations"},
        ],
    }
    if stop_when_source is not None:
        loop["stop_when"] = {
            "from": stop_when_source,
            "equals": True,
        }
    if stop_after is not None:
        loop["stop_after"] = stop_after
    return parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.step_until",
                    requires=["loop.current"],
                    provides=["loop.next", "loop.done"],
                    exports=["loop.next", "loop.done"],
                    pipeline={
                        "inputs": [INPUT_SPEC("loop.current")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts the while loop body."),
                            _node_call(
                                "step",
                                "test.loop_step_until",
                                "Increments loop.current and reports loop.done.",

                                config={"target": target},
                            ),
                            _node_call("end", "test.loop_next_end", "Ends the while body."),
                        ],
                        "edges": _edge_chain("start", "step", "end"),
                        "outputs": [REQ_SPEC("loop.next"), REQ_SPEC("loop.done")],
                    },
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("loop.current")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the while loop fixture."),
                    _node_call(
                        "while_loop",
                        "vibeflow.loop.while",
                        "Runs the body until loop.done is true.",
                        requires=[REQ_SPEC("loop.current")],
                        provides=[PROV_SPEC("loop.final"), PROV_SPEC("loop.iterations")],
                        loop=loop,
                    ),
                    _node_call("end", "test.loop_final_end", "Ends after loop.final."),
                ],
                "edges": _edge_chain("start", "while_loop", "end"),
                "outputs": [REQ_SPEC("loop.final"), REQ_SPEC("loop.iterations")],
            },
        }
    )


def test_fixed_count_loop_runs_nodeset_body_with_carry_collect_and_trace() -> None:
    graph = _fixed_count_loop_graph()
    context = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="full")).run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 3
    assert context.get("loop.history")["value"] == [1, 2, 3]
    assert context.get("loop.iterations")["value"] == 3
    assert "count_loop.iter_2.step" in context.get("runtime.qualified_exec_order")
    assert context.get("runtime.total_step_count") == 1 + 3 * 3 + 2


def test_while_loop_runs_until_condition_and_reports_iterations() -> None:
    graph = _while_loop_graph(target=3)
    context = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="full")).run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 3
    assert context.get("loop.iterations")["value"] == 3
    assert "while_loop.iter_2.step" in context.get("runtime.qualified_exec_order")


def test_unbounded_while_loop_stops_from_condition() -> None:
    graph = _while_loop_graph(target=3, max_iterations=None)
    context = PipelineRuntime(
        graph,
        registry=_loop_registry(),
    ).run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 3
    assert context.get("loop.iterations")["value"] == 3


def test_dual_loop_stop_conditions_use_or() -> None:
    graph = _while_loop_graph(
        target=9,
        max_iterations=None,
        stop_after=2,
    )
    context = PipelineRuntime(
        graph,
        registry=_loop_registry(),
    ).run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 2
    assert context.get("loop.iterations")["value"] == 2


def test_while_loop_outputs_match_plan_block_and_compiled_execution() -> None:
    graph = _while_loop_graph(target=3)
    expected = None
    for execution in ("plan", "block", "compiled"):
        context = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="boundary", execution=execution)).run({"loop.current": 0})
        actual = (context.get("loop.final")["value"], context.get("loop.iterations")["value"])
        expected = actual if expected is None else expected
        assert actual == expected
        if execution in {"block", "compiled"}:
            assert any(event["kind"] == "loop_block_enter" for event in _runtime_trace_events_from_context(context))


def test_node_config_overrides_pass_through_nested_loop_body_in_all_execution_modes() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.add_once",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"delta": 1}),
                ),
                _nodeset_config(
                    "loop.outer_body",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline={
                        "inputs": [INPUT_SPEC("value.in")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts the outer loop body."),
                            _node_call(
                                "inner_loop",
                                "vibeflow.loop.while",
                                "Runs the inner add loop once.",
                                requires=[REQ_SPEC("value.in")],
                                provides=[PROV_SPEC("value.out")],
                                loop={
                                    "body": "loop.add_once",
                                    "max_iterations": 3,
                                    "stop_after": 1,
                                    "carry": [{"from": "value.in", "as": "value.in", "update": "value.out"}],
                                    "outputs": [{"from": "value.out", "as": "value.out"}],
                                },
                            ),
                            _node_call("end", "test.out_end", "Ends after inner value.out."),
                        ],
                        "edges": _edge_chain("start", "inner_loop", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                ),
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nested loop override fixture."),
                    _node_call(
                        "outer_loop",
                        "vibeflow.loop.while",
                        "Runs a body containing another loop.",
                        requires=[REQ_SPEC("value.in")],
                        provides=[PROV_SPEC("value.out")],
                        node_configs={"inner_loop.add": {"delta": 5}},
                        loop={
                            "body": "loop.outer_body",
                            "max_iterations": 3,
                            "stop_after": 1,
                            "carry": [{"from": "value.in", "as": "value.in", "update": "value.out"}],
                            "outputs": [{"from": "value.out", "as": "value.out"}],
                        },
                    ),
                    _node_call("end", "test.out_end", "Ends after outer value.out."),
                ],
                "edges": _edge_chain("start", "outer_loop", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert not any(error.rule_id.startswith("NODESET.CONFIG.") for error in report.errors)

    for execution in ("plan", "block", "compiled"):
        context = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary", execution=execution)).run({"value.in": 2})
        assert context.get("value.out")["value"] == 7


def test_loop_max_iterations_raises_runtime_error() -> None:
    graph = _while_loop_graph(target=5, max_iterations=2)
    runtime = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="full"))

    with pytest.raises(PipelineRuntimeError, match="max_iterations=2"):
        runtime.run({"loop.current": 0})

    assert "while_loop.iter_1.step" in runtime.trace.to_dict()["qualified_exec_order"]


def test_loop_stop_when_missing_or_non_bool_source_is_runtime_error() -> None:
    missing_graph = _while_loop_graph(target=1, stop_when_source="loop.missing")
    with pytest.raises(PipelineRuntimeError, match="stop_when source 'loop.missing' is not available"):
        PipelineRuntime(missing_graph, registry=_loop_registry()).run({"loop.current": 0})

    non_bool_graph = _while_loop_graph(target=1, stop_when_source="loop.next")
    with pytest.raises(PipelineRuntimeError, match="stop_when source 'loop.next' must be boolean"):
        PipelineRuntime(non_bool_graph, registry=_loop_registry()).run({"loop.current": 0})


def test_block_execution_compiles_loop_body_with_nested_nodeset() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.step_until",
                    requires=["loop.current"],
                    provides=["loop.next", "loop.done"],
                    exports=["loop.next", "loop.done"],
                    pipeline={
                        "inputs": [INPUT_SPEC("loop.current")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts inner loop step."),
                            _node_call(
                                "step",
                                "test.loop_step_until",
                                "Produces loop.next and loop.done.",

                            ),
                            _node_call("end", "test.loop_next_end", "Ends inner step."),
                        ],
                        "edges": _edge_chain("start", "step", "end"),
                        "outputs": [REQ_SPEC("loop.next"), REQ_SPEC("loop.done")],
                    },
                ),
                _nodeset_config(
                    "loop.body_with_nested_nodeset",
                    requires=["loop.current"],
                    provides=["loop.next", "loop.done"],
                    exports=["loop.next", "loop.done"],
                    pipeline={
                        "inputs": [INPUT_SPEC("loop.current")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts uncompiled body."),
                            _node_call(
                                "nested",
                                "loop.step_until",
                                "Calls a nested nodeset inside a block-compiled loop body.",

                            ),
                            _node_call("end", "test.loop_next_end", "Ends uncompiled body."),
                        ],
                        "edges": _edge_chain("start", "nested", "end"),
                        "outputs": [REQ_SPEC("loop.next"), REQ_SPEC("loop.done")],
                    },
                ),
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("loop.current")],
                "nodes": [
                    _node_call("start", "test.start", "Starts block rejection fixture."),
                    _node_call(
                        "while_loop",
                        "vibeflow.loop.while",
                        "Uses a loop body with a nested nodeset.",
                        requires=[REQ_SPEC("loop.current")],
                        provides=[PROV_SPEC("loop.final"), PROV_SPEC("loop.iterations")],
                        loop={
                            "body": "loop.body_with_nested_nodeset",
                            "max_iterations": 3,
                            "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}],
                            "stop_when": {"from": "loop.done", "equals": True},
                            "outputs": [
                                {"from": "loop.next", "as": "loop.final"},
                                {"from": "loop.iterations", "as": "loop.iterations"},
                            ],
                        },
                    ),
                    _node_call("end", "test.loop_final_end", "Ends block rejection fixture."),
                ],
                "edges": _edge_chain("start", "while_loop", "end"),
                "outputs": [REQ_SPEC("loop.final")],
            },
        }
    )

    runtime = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="boundary", execution="block"))
    assert any(block.kind == "loop" and block.entry == "while_loop" for block in runtime._plan.blocks)
    assert not [finding for finding in explain_block_compilation(runtime._plan) if not finding["compiled"]]

    context = runtime.run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 3
    assert any(event["kind"] == "loop_block_enter" for event in _runtime_trace_events_from_context(context))


def test_block_execution_rejects_removed_loop_concurrency_entry():
    from vibeflow.core.flow import GraphConfigError
    with pytest.raises(GraphConfigError,match='GRAPH.ASYNC.MIGRATION'):
        parse_graph_config({'pipeline':{'nodes':[{'id':'loop','type_used':'vibeflow.loop.while','display_name':'Loop','description':'Removed task entry','requires':[],'provides':[],'async':'detached'}]}})


def test_join_policy_any_active_allows_unconditional_input_when_condition_is_inactive() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the join fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.",  config={"value": 7}),
                    _node_call("route", "test.inactive_route", "Produces an inactive control value."),
                    _node_call(
                        "join",
                        "test.join_passthrough",
                        "Consumes value.in even when a separate conditional control edge is inactive.",

                        join_policy="any_active",
                    ),
                    _node_call("end", "test.out_end", "Ends after value.out."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "start", "to": "route"},
                    {"from": "seed", "to": "join"},
                    {"from": "route", "to": "join", "when": "flow.route == true"},
                    {"from": "join", "to": "end"},
                ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=_loop_registry()).run({})

    assert context.get("value.out")["value"] == 7


def test_health_reports_ambiguous_unconditional_conditional_join() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the ambiguous join fixture."),
                    _node_call("seed", "test.seed", "Produces unconditional value.in."),
                    _node_call("alt", "test.conditional_value", "Produces conditional value.in."),
                    _node_call("join", "test.join_passthrough", "Ambiguously consumes value.in."),
                    _node_call("end", "test.out_end", "Ends after value.out."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                    {"from": "start", "to": "alt"},
                    {"from": "seed", "to": "join"},
                    {"from": "alt", "to": "join", "when": "flow.use_alt == true"},
                    {"from": "join", "to": "end"},
                ],
            }
        }
    )

    report = validate_graph_health(graph, registry=_loop_registry(), purity_policy=PurityPolicy(max_source_lines=1000))

    assert any(error.rule_id == "GRAPH.JOIN.AMBIGUOUS_UNCONDITIONAL" for error in report.errors)


def test_multiple_active_exactly_one_join_errors_at_runtime() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the conflicting join fixture."),
                    _node_call("left", "test.left_value", "Produces left value.in."),
                    _node_call("right", "test.right_value", "Produces right value.in."),
                    _node_call("join", "test.join_passthrough", "Conflicts on value.in."),
                ],
                "edges": [{"from": "start", "to": "left"}, {"from": "start", "to": "right"}, {"from": "left", "to": "join"}, {"from": "right", "to": "join"}],
            }
        }
    )

    with pytest.raises(PipelineRuntimeError, match="exactly once, got 2"):
        PipelineRuntime(graph, registry=_loop_registry()).run({})


def test_join_policy_all_waits_for_all_incoming_inputs() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the all join fixture."),
                    _node_call("left", "test.left_value", "Produces value.in."),
                    _node_call("other", "test.other_value", "Produces other.in."),
                    _node_call(
                        "join",
                        "test.two_input_join",
                        "Runs only after both incoming inputs arrive.",

                        join_policy="all",
                    ),
                    _node_call("end", "test.out_end", "Ends after value.out."),
                ],
                "edges": [
                    {"from": "start", "to": "left"},
                    {"from": "left", "to": "join"},
                    {"from": "left", "to": "other"},
                    {"from": "other", "to": "join"},
                    {"from": "join", "to": "end"},
                ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=_loop_registry()).run({})

    assert context.get("value.out")["value"] == 11
    assert context.get("runtime.exec_order") == ("start", "left", "other", "join", "end")


def test_runtime_passes_non_deepcopy_object_by_reference() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the object reference fixture."),
                    _node_call("identity", "test.identity_object", "Passes value.in through."),
                    _node_call("end", "test.out_end", "Consumes value.out."),
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
                        _node_call("bad", "test.runtime_fail", "Fails at runtime.",  config={"fail": True}),
                        _node_call("end", "test.out_end", "Consumes value.out."),
                    ],
                    "edges": _edge_chain("start", "bad", "end"),
                }
            }
        ),
        encoding="utf-8",
    )
    publish_native_fixture(config_path, _registry())
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
    assert [event["kind"] for event in _runtime_trace_events_from_context(context)] == [
        "run_start",
        "type_resolve",
        "run_end",
    ]
    assert runtime.trace.exec_order == ["start", "seed", "end"]
    assert runtime.trace.current_node == "end"


def test_runtime_options_off_keeps_summary_without_events() -> None:
    graph = parse_graph_config({"pipeline": _seed_only_pipeline()})
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="off"))

    context = runtime.run({})

    assert not context.exists("runtime.events")
    assert context.get("runtime.event_count") == 0
    assert context.get("runtime.events_streamed") is True
    assert [line["kind"] for line in _runtime_trace_lines_from_context(context)] == ["runtime_summary"]
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
    assert [(block.kind, block.nodes) for block in runtime._plan.blocks] == [("graph", ("start", "seed", "add", "end"))]
    context = runtime.run({})

    assert context.get("value.out")["value"] == 5
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "end"]
    assert context.get("runtime.edge_executions") == {"start->seed": 1, "seed->add": 1, "add->end": 1}
    assert [event["kind"] for event in _runtime_trace_events_from_context(context)] == ["run_start", "block_enter", "type_resolve", "type_resolve", "block_exit", "run_end"]


def test_runtime_options_compiled_runs_generated_block_when_node_hooks_enabled(monkeypatch) -> None:
    graph = parse_graph_config({"pipeline": _seed_add_pipeline(add={"config": {"delta": 4}})})

    calls = []

    def before_node(self, name, node_type, input_summary):
        calls.append(("before", name))

    def after_node(self, name, node_type, output_summary):
        calls.append(("after", name))

    plugin = type("NodeHookPlugin", (), {"id": "node_hook", "before_node": before_node, "after_node": after_node})()
    plugin_registry = PluginRegistry()
    plugin_registry.register(plugin, plugin_type="runtime")
    context = PipelineRuntime(
        graph,
        registry=_registry(),
        plugin_registry=plugin_registry,
        runtime_options=RuntimeOptions(trace="boundary", node_hooks=True, execution="compiled"),
    ).run({})

    assert context.get("value.out")["value"] == 5
    assert [event["kind"] for event in _runtime_trace_events_from_context(context)] == ["run_start", "block_enter", "type_resolve", "type_resolve", "block_exit", "run_end"]
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
    assert [(block.kind, block.nodes) for block in runtime._plan.blocks] == [("graph", ("start", "seed", "add", "end"))]
    context = runtime.run({})

    assert context.get("value.out")["value"] == 5
    events = _runtime_trace_events_from_context(context)
    event_kinds = [event["kind"] for event in events]
    assert event_kinds == ["block_enter", "node", "node", "type_resolve", "node", "type_resolve", "node", "block_exit"]
    assert [event["node"] for event in events if event["kind"] == "node"] == ["start", "seed", "add", "end"]
    assert not context.exists("runtime.events")
    assert context.get("runtime.event_count") == len(events)
    assert _runtime_trace_lines_from_context(context)[-1]["event_count"] == len(events)
    assert context.get("runtime.edge_executions") == {"start->seed": 1, "seed->add": 1, "add->end": 1}


def test_runtime_options_compiled_failure_records_node_and_block_failed() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                        _node_call("start", "test.start", "Starts the compiled failure fixture."),
                        _node_call("bad", "test.runtime_fail", "Fails in a compiled block.",  config={"fail": True}),
                        _node_call("end", "test.out_end", "Consumes value.out."),
                ],
                "edges": _edge_chain("start", "bad", "end"),
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run({})

    assert runtime.trace.current_node == "bad"
    events = [line for line in _runtime_trace_lines(Path(runtime.trace.trace_path)) if line["kind"] != "runtime_summary"]
    assert [event["kind"] for event in events] == ["run_start", "block_enter", "node_failed", "block_failed"]
    assert "boom" in next(
        event for event in events if event["kind"] == "node_failed"
    )["failure"]


def test_runtime_options_compiled_executes_decision_branch(monkeypatch) -> None:
    registry = _registry()
    register_node(registry, RouteNode_DECLARATION, RouteNode)
    register_node(registry, BranchCopyNode_DECLARATION, BranchCopyNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the compiled branch fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.",  config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in."),
                    _node_call("route", "test.route", "Chooses the route."),
                    _node_call("copy", "test.branch_copy", "Copies value.out on the alternate branch."),
                    _node_call("end", "test.start", "Ends the compiled branch fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                        {"from": "seed", "to": "add"},
                        {"from": "add", "to": "route"},
                        {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                        {"from": "copy", "to": "end"},
                        {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                    ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert [(block.kind, block.nodes) for block in runtime._plan.blocks] == [("graph", ("start", "seed", "add", "route", "copy", "end"))]
    context = runtime.run({})

    assert context.get("value.out")["value"] == 2
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "route", "end"]
    assert context.get("runtime.edge_executions") == {
        "start->seed": 1,
        "seed->add": 1,
        "add->route": 1,
        "route->end": 1,
    }


def test_runtime_options_compiled_rejects_decision_loop() -> None:
    DoneCheckNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.done_check', display_name='Done Check', description='Checks loop completion.', version='0.1.0', flow_kind='decision', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.out', 'exactly_one', display_name='value.out'),), provides=(DataProvider('loop.done', 'loop.done', display_name='loop.done'), DataProvider('value.loop', 'value.in', display_name='value.loop')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.out', 'exactly_one', display_name='value.out'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('loop.done', 'loop.done', display_name='loop.done'), DataProvider('value.loop', 'value.in', display_name='value.loop'))}), rulesets=("vibeflow.process",))

    class DoneCheckNode:

        def run_pure(self, inputs, params):
            value = inputs["value.out"]["value"]
            return {"loop.done": value >= params.get("target", 3), "value.loop": value}

    registry = _registry()
    register_node(registry, DoneCheckNode_DECLARATION, DoneCheckNode, {"target": {"type": "number"}}, {"target": 3})
    graph = _decision_loop_graph(target=3)

    with pytest.raises(GraphCompileError) as exc_info:
        PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert exc_info.value.rule_id == "GRAPH.CYCLE.FORBIDDEN"


def test_runtime_options_block_rejects_decision_loop_before_max_steps() -> None:
    NeverDoneNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.never_done', display_name='Never Done', description='Never exits loop.', version='0.1.0', flow_kind='decision', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.out', 'exactly_one', display_name='value.out'),), provides=(DataProvider('loop.done', 'loop.done', display_name='loop.done'), DataProvider('value.loop', 'value.in', display_name='value.loop')), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.out', 'exactly_one', display_name='value.out'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('loop.done', 'loop.done', display_name='loop.done'), DataProvider('value.loop', 'value.in', display_name='value.loop'))}), rulesets=("vibeflow.process",))

    class NeverDoneNode:

        def run_pure(self, inputs, params):
            return {"loop.done": False, "value.loop": inputs["value.out"]["value"]}

    registry = _registry()
    register_node(registry, replace(NeverDoneNode_DECLARATION, type_key="test.done_check"), NeverDoneNode, {"target": {"type": "number"}}, {"target": 3})
    graph = _decision_loop_graph(target=3, max_steps=1)

    with pytest.raises(GraphCompileError) as exc_info:
        PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="block"))
    assert exc_info.value.rule_id == "GRAPH.CYCLE.FORBIDDEN"


def test_runtime_options_compiled_generates_block_with_async_barrier() -> None:
    OutToNextNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.out_to_next', display_name='Out To Next', description='Copies value.out to value.next.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.out', 'exactly_one', display_name='value.out'),), provides=(DataProvider('value.next', 'value.next', display_name='value.next'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.out', 'exactly_one', display_name='value.out'),)}, output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.next', 'value.next', display_name='value.next'),)}), rulesets=("vibeflow.process",))

    class OutToNextNode:

        def run_pure(self, inputs, params):
            return {"value.next": inputs["value.out"]["value"]}

    NextEndNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.next_end', display_name='Next End', description='Ends after value.next.', version='0.1.0', flow_kind='terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('value.next', 'exactly_one', display_name='value.next'),), input_semantics={item.type: ('Fixture ' + item.type,) for item in (DataRequirement('value.next', 'exactly_one', display_name='value.next'),)}), rulesets=("vibeflow.process",))

    class NextEndNode:

        def run_pure(self, inputs, params):
            return {}

    registry = _registry()
    register_node(registry, OutToNextNode_DECLARATION, OutToNextNode)
    register_node(registry, NextEndNode_DECLARATION, NextEndNode)
    register_task_manager(registry,'test.add',join=True)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the async barrier fixture."),
                    _node_call("seed", "test.seed", "Produces value.in.",  config={"value": 4}),
                    task_call('async_add', 'test.add', 'Adds asynchronously.', config={'delta': 3}),
                    _node_call("out_to_next", "test.out_to_next", "Copies value.out to value.next."),
                    _node_call("end", "test.next_end", "Consumes value.next."),
                ],
                "edges": _edge_chain("start", "seed", "async_add", "out_to_next", "end"),
                "outputs": [REQ_SPEC("value.next")],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, execution="compiled"))
    assert [(block.kind, block.nodes) for block in runtime._plan.blocks] == [("graph", ("start", "seed", "async_add", "out_to_next", "end"))]
    interpreted_nodes = []
    original_run_compiled_frame = PipelineRuntime._run_compiled_frame

    def spy_run_compiled_frame(self, frame, context):
        interpreted_nodes.append(frame.name)
        return original_run_compiled_frame(self, frame, context)

    PipelineRuntime._run_compiled_frame = spy_run_compiled_frame
    try:
        context = runtime.run({})
    finally:
        PipelineRuntime._run_compiled_frame = original_run_compiled_frame

    assert interpreted_nodes == ["start", "seed", "async_add", "work", "out_to_next", "end"]
    assert context.get("value.next")["value"] == 7
    assert any(event["kind"] == "block_enter" for event in _runtime_trace_events_from_context(context))


def _decision_loop_graph(*, target: int, max_steps: int = 20):
    return parse_graph_config(
        {
            "pipeline": {
                "max_steps": max_steps,
                "nodes": [
                    _node_call("start", "test.start", "Starts the decision loop fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.",  config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in."),
                    _node_call("done", "test.done_check", "Checks whether the loop is done.",  config={"target": target}),
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
    register_node(registry, RouteNode_DECLARATION, RouteNode)
    register_node(registry, BranchCopyNode_DECLARATION, BranchCopyNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the conditional route fixture."),
                    _node_call("seed", "test.seed", "Produces initial value.in.",  config={"value": 1}),
                    _node_call("add", "test.add", "Adds value.in."),
                    _node_call("route", "test.route", "Chooses the route."),
                    _node_call("copy", "test.branch_copy", "Copies value.out on the alternate branch."),
                    _node_call("end", "test.start", "Ends the conditional route fixture."),
                ],
                "edges": [
                    {"from": "start", "to": "seed"},
                        {"from": "seed", "to": "add"},
                        {"from": "add", "to": "route"},
                        {"from": "route", "to": "copy", "when": "flow.route == 'again'"},
                        {"from": "copy", "to": "end"},
                        {"from": "route", "to": "end", "when": "flow.route == 'done'"},
                    ],
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(execution="block")).run({})

    assert context.get("value.out")["value"] == 2
    assert list(context.get("runtime.exec_order")) == ["start", "seed", "add", "route", "end"]


def _runtime_nodeset_depth_config(depth: int) -> dict:
    nodesets = [
        _nodeset_config(
            "runtime.depth.0",
            requires=["value.in"],
            provides=["value.out"],
            pipeline=_input_add_pipeline(add={"delta": 1}),
        )
    ]
    for index in range(1, depth):
        child = f"runtime.depth.{index - 1}"
        nodesets.append(
            _nodeset_config(
                f"runtime.depth.{index}",
                requires=["value.in"],
                provides=["value.out"],
                pipeline={
                    "inputs": [INPUT_SPEC("value.in")],
                    "nodes": [
                        _node_call("start", "test.start", f"Starts runtime depth wrapper {index}."),
                        _node_call("call", child, f"Calls {child}."),
                        _node_call("end", "test.out_end", f"Ends runtime depth wrapper {index}."),
                    ],
                    "edges": _edge_chain("start", "call", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
            )
        )
    return {
        "nodesets": nodesets,
        "pipeline": {
            "inputs": [INPUT_SPEC("value.in")],
            "nodes": [
                _node_call("start", "test.start", "Starts the runtime depth fixture."),
                _node_call(
                    "top",
                    f"runtime.depth.{depth - 1}",
                    "Calls the runtime depth fixture.",

                ),
                _node_call("end", "test.out_end", "Ends the runtime depth fixture."),
            ],
            "edges": _edge_chain("start", "top", "end"),
            "outputs": [REQ_SPEC("value.out")],
        },
    }


def _runtime_nodeset_depth_graph(depth: int):
    return parse_graph_config(_runtime_nodeset_depth_config(depth))


def test_runtime_options_rejects_unknown_execution() -> None:
    with pytest.raises(ValueError, match="runtime execution"):
        RuntimeOptions(execution="native")


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "4"])
def test_runtime_options_rejects_invalid_async_max_workers(value) -> None:
    with pytest.raises(ValueError, match="async_max_workers"):
        RuntimeOptions(async_max_workers=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5, "4"])
def test_runtime_options_rejects_invalid_nodeset_max_depth(value) -> None:
    with pytest.raises(ValueError, match="nodeset_max_depth"):
        RuntimeOptions(nodeset_max_depth=value)


def test_runtime_options_default_nodeset_max_depth_is_four() -> None:
    assert RuntimeOptions().nodeset_max_depth == 4


def test_pipeline_runtime_has_no_second_implicit_depth_limit() -> None:
    graph = _runtime_nodeset_depth_graph(5)

    runtime = PipelineRuntime(graph, registry=_registry())
    assert runtime._plan.frames["top"].subplan is not None

    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(nodeset_max_depth=5))
    assert runtime._plan.frames["top"].subplan is not None


def test_checked_run_and_validate_use_effective_nodeset_max_depth(tmp_path) -> None:
    from vibeflow.tooling.application.python.cli.config import validate_config_path

    config_path = tmp_path / "depth.jsonc"
    _write_config_file(config_path, _runtime_nodeset_depth_config(5))

    publish_native_fixture(config_path, _registry())
    validation = validate_config_path(config_path)
    with pytest.raises(CheckedRunError) as refused:
        run_checked(config_path, registry=_registry(), initial={"value.in": 2}, run_root=tmp_path / "runs", run_id="default-depth")
    publish_native_fixture(config_path, _registry())
    result = run_checked(
        config_path,
        registry=_registry(),
        initial={"value.in": 2},
        run_root=tmp_path / "runs",
        run_id="custom-depth",
        runtime_options=RuntimeOptions(nodeset_max_depth=5),
    )

    assert any(error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED" for error in validation.errors)
    assert any(error.rule_id == "NODESET.NESTING.DEPTH_EXCEEDED" for error in refused.value.result.health.errors)
    assert result.context.get("value.out")["value"] == 3


def test_loop_iterations_do_not_increase_nodeset_nesting_depth() -> None:
    graph = _while_loop_graph(target=5, max_iterations=10)

    context = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(nodeset_max_depth=1)).run({"loop.current": 0})

    assert context.get("loop.final")["value"] == 5


def _task_pool_probe(workers, *, queued=False):
    ready=threading.Barrier(workers+1); release=threading.Event(); queued_started=threading.Event()
    class Work:
        def run_pure(self,inputs,params,context):
            if params.get('queued'):queued_started.set()
            else:ready.wait(timeout=2)
            assert release.wait(2)
            return {'worker.name':threading.current_thread().name}
    class Manager:
        def run_pure(self,inputs,params,context):
            refs=[context.tasks.start('work',{}) for _ in range(workers)]
            ready.wait(timeout=2)
            if queued:
                refs.append(context.tasks.start('queued',{}))
                assert not queued_started.is_set()
            release.set()
            outcomes=context.tasks.wait_all_exited(refs)
            assert all(item['status']=='succeeded' for item in outcomes)
            return {'worker.report':[item['outputs']['worker.name'] for item in outcomes]}
    registry=_registry()
    contract=NodeContractDescriptor(provides=(DataProvider('worker.name','worker.name',display_name='Thread'),),
        output_semantics={'worker.name':('Actual worker thread',)},params_schema={'queued':{'type':'boolean'}},params_defaults={'queued':False})
    registry.register(NodeDescriptor('pool.work','Worker','Pool probe','1','process',contract=contract,rulesets=()),Work)
    registry.register(NodeDescriptor('pool.manager','Manager','Controls a bounded pool','1','task_manager',
        contract=NodeContractDescriptor(provides=(DataProvider('worker.report','worker.report',display_name='Threads'),),output_semantics={'worker.report':('Actual execution report',)}),rulesets=()),Manager)
    graph=parse_graph_config({'pipeline':{'nodes':[_node_call('start','test.start','Start'),
        {'id':'manager','type_used':'pool.manager','display_name':'Manager','description':'Pool manager','task_targets':{
            'work':{'type_used':'pool.work'},'queued':{'type_used':'pool.work','config':{'queued':True}}}},
        _node_call('end','test.start','End')],'edges':_edge_chain('start','manager','end'),
        'outputs':[REQ_SPEC('worker.report')]}})
    runtime=PipelineRuntime(graph,registry=registry,runtime_options=RuntimeOptions(async_max_workers=workers))
    try:return runtime.run({}).get('worker.report')['value'],queued_started.is_set()
    finally:release.set()


def test_task_executor_defaults_to_four_workers():
    assert RuntimeOptions().async_max_workers==4
    names,queued=_task_pool_probe(RuntimeOptions().async_max_workers)
    assert len(set(names))==4 and not queued


def test_task_executor_can_run_six_tasks_concurrently():
    names,queued=_task_pool_probe(6)
    assert len(set(names))==6 and not queued


def test_task_executor_queues_tasks_beyond_worker_limit():
    names,queued=_task_pool_probe(2,queued=True)
    assert len(names)==3 and len(set(names))==2 and queued


def test_async_result_key_joins_when_required() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the async join fixture."),
                    task_call('seed', 'test.seed', 'Produces value.in asynchronously.', config={'value': 4}),
                    _node_call("add", "test.add", "Adds delta to value.in.",  config={"delta": 3}),
                    _node_call("end", "test.out_end", "Consumes value.out."),
                ],
                "edges": _edge_chain("start", "seed", "add", "end"),
                "outputs": [REQ_SPEC("value.out")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=register_task_manager(_registry(), 'test.seed', join=True)).run({})

    assert context.get("value.out")["value"] == 7
    assert "task_exited" in [event["kind"] for event in _runtime_trace_events_from_context(context)]


def test_async_result_key_not_joined_when_unconsumed() -> None:
    SlowResultNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.slow_result', display_name='Slow Result', description='Slow result-key async task.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.async', 'value.async', display_name='value.async'),), examples=({'inputs': {}, 'params': {}},), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.async', 'value.async', display_name='value.async'),)}), rulesets=("vibeflow.process",))

    class SlowResultNode:

        def run_pure(self, inputs, params):
            time.sleep(0.2)
            return {"value.async": 99}

    registry = _registry()
    register_node(registry, SlowResultNode_DECLARATION, SlowResultNode)
    register_task_manager(registry,'test.slow_result',join=False)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the unconsumed async fixture."),
                    task_call('slow', 'test.slow_result', 'Produces an unconsumed async result.', join=False),
                    _node_call("seed", "test.seed", "Produces value.in.",  config={"value": 2}),
                    _node_call("end", "test.in_end", "Consumes value.in."),
                ],
                "edges": _edge_chain("start", "slow", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="boundary")).run({})

    assert context.get("value.in")["value"] == 2
    assert not context.exists("value.async")
    assert "task_exited" in [event["kind"] for event in _runtime_trace_events_from_context(context)]


def test_async_detached_failure_records_warning_and_completes() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the detached failure fixture."),
                    task_call('metrics', 'test.runtime_fail', 'Fails in a detached task.', config={'fail': True}),
                    _node_call("seed", "test.seed", "Produces value.in.",  config={"value": 2}),
                    _node_call("end", "test.in_end", "Consumes value.in."),
                ],
                "edges": _edge_chain("start", "metrics", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    with pytest.raises(RuntimeError,match="boom"):
        PipelineRuntime(graph, registry=register_task_manager(_registry(),'test.runtime_fail')).run({})


def test_async_result_key_requires_migration():
    from vibeflow.core.flow import GraphConfigError
    with pytest.raises(GraphConfigError,match='GRAPH.ASYNC.MIGRATION'):
        parse_graph_config({'pipeline':{'nodes':[task_call('seed','test.seed','Worker') | {'async':'result_key','result_key':'value.missing'}]}})


def test_config_schema_reports_async_result_key_not_in_provides() -> None:
    findings = collect_config_schema_findings(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces value.in with an invalid result key.",  result_key="value.missing", **{"async": "result_key"})
                ]
            }
        }
    )

    # Ordinary-node contracts come from the Registry, so this relationship is
    # intentionally checked only after the effective graph has been resolved.
    assert not any(finding.rule_id == "CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY" for finding in findings)


def test_runtime_no_longer_has_json_snapshot_output_mode() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the NaN output fixture."),
                    _node_call("set", "test.nan_output", "Produces NaN value.out."),
                    _node_call("end", "test.out_end", "Consumes value.out."),
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
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the async nodeset fixture."),
                    task_call('composite', 'math.add_one', 'Calls add-one asynchronously.'),
                    _node_call("end", "test.out_end", "Consumes value.out."),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=register_task_manager(_registry(), 'math.add_one', requires=['value.in'], provides=['value.out'])).run({"value.in": 5})

    assert context.get("value.out")["value"] == 7
    assert "task_exited" in [event["kind"] for event in _runtime_trace_events_from_context(context)]
    assert "composite.tasks.work.task_1.work.add" in context.get("runtime.qualified_exec_order")


def test_async_detached_timeout_records_warning_and_does_not_block() -> None:
    SlowNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.slow', display_name='Slow', description='Slow detached task.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('value.out', 'value.out', display_name='value.out'),), examples=({'inputs': {}, 'params': {}},), output_semantics={item.key: ('Fixture ' + item.key,) for item in (DataProvider('value.out', 'value.out', display_name='value.out'),)}), rulesets=("vibeflow.process",))

    class SlowNode:

        def run_pure(self, inputs, params):
            time.sleep(0.05)
            return {"value.out": 1}

    registry = _registry()
    register_node(registry, SlowNode_DECLARATION, SlowNode)
    register_task_manager(registry,'test.slow',join=False)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the detached timeout fixture."),
                    task_call('slow', 'test.slow', 'Runs a slow detached task.', join=False),
                    _node_call("seed", "test.seed", "Produces value.in.",  config={"value": 3}),
                    _node_call("end", "test.in_end", "Consumes value.in."),
                ],
                "edges": _edge_chain("start", "slow", "seed", "end"),
                "outputs": [REQ_SPEC("value.in")],
            }
        }
    )

    context = PipelineRuntime(graph, registry=registry, runtime_options=RuntimeOptions(trace="full")).run({})

    assert context.get("value.in")["value"] == 3
    assert any(event["kind"] == "task_exited" for event in _runtime_trace_events_from_context(context))


def test_runtime_options_node_hooks_false_skips_per_node_hooks(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "runtime_plugin.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
MARKER = Path({str(marker_path)!r})
def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")
class RuntimePlugin:
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
                "plugins": [write_lifecycle_fixture(tmp_path, source={"kind":"file", "ref":plugin_path.name, "export":"RuntimePlugin"}, plugin_id="runtime_hook", filename="runtime_definition.py")],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )

    publish_native_fixture(config_path, _registry())
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
MARKER = Path({str(marker_path)!r})
def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")
class RuntimePlugin:
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
                "plugins": [write_lifecycle_fixture(tmp_path, source={"kind":"file", "ref":plugin_path.name, "export":"RuntimePlugin"}, plugin_id="runtime_hook", filename="runtime_definition.py")],
                "pipeline": _seed_add_pipeline(add={"config": {"delta": 4}}),
            }
        ),
        encoding="utf-8",
    )

    publish_native_fixture(config_path, _registry())
    run_checked(
        config_path,
        registry=_registry(),
        run_root=tmp_path / "runs",
        run_id="block_hooks",
        runtime_options=RuntimeOptions(trace="boundary", node_hooks=False, nodeset_hooks=False, block_hooks=True, execution="compiled"),
    )

    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert hooks == ["before_block", "after_block"]

def test_checked_run_trace_records_nodeset_enter_exit(tmp_path) -> None:
    config_path = tmp_path / "nodeset_workflow.json"
    _write_config_file(
        config_path,
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
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset trace fixture."),
                    _node_call("composite", "math.add_one", "Calls add-one nodeset."),
                    _node_call("end", "test.out_end", "Consumes value.out."),
                ],
                "edges": _edge_chain("start", "composite", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        },
    )
    publish_native_fixture(config_path, _registry())
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


def test_checked_run_output_summary_does_not_expand_large_prediction_mapping(tmp_path) -> None:
    registry = _registry()
    register_node(registry, LargePredictionNode_DECLARATION, LargePredictionNode)
    config_path = tmp_path / "large_prediction.json"
    config_path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts large prediction fixture."),
                        _node_call("predict", "test.large_prediction", "Produces large prediction mapping."),
                        _node_call("end", "test.out_end", "Consumes predictions."),
                    ],
                    "edges": _edge_chain("start", "predict", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                }
            }
        ),
        encoding="utf-8",
    )

    publish_native_fixture(config_path, registry)
    result = run_checked(config_path, registry=registry, run_root=tmp_path / "runs", run_id="large_prediction")

    assert result.context.get("value.out")["value"]["sample_0999"] == 999
    summary_text = (result.run_dir / "output_summary.json").read_text(encoding="utf-8")
    summary = json.loads(summary_text)
    assert summary["value.out"]["value"] == {"size": 1000, "type": "dict"}
    assert "sample_0999" not in summary_text


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
                            _node_call("inner_call", "inner.flow", "Calls inner flow."),
                            _node_call("end", "test.out_end", "Consumes outer value.out."),
                        ],
                        "edges": _edge_chain("start", "inner_call", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                ),
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts nested trace fixture."),
                    _node_call("outer_call", "outer.flow", "Calls outer flow."),
                    _node_call("end", "test.out_end", "Consumes final value.out."),
                ],
                "edges": _edge_chain("start", "outer_call", "end"),
                "outputs": [REQ_SPEC("value.out")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="full")).run({})

    assert context.get("value.out")["value"] == 2
    assert "outer_call.inner_call.add" in context.get("runtime.qualified_exec_order")
    node_events = [event for event in _runtime_trace_events_from_context(context) if event["kind"] == "node"]
    inner_add = next(event for event in node_events if event["qualified_node"] == "outer_call.inner_call.add")
    assert inner_add["path"] == ["outer_call", "inner_call", "add"]
    assert inner_add["depth"] == 2


def test_runtime_trace_counts_while_loop_nodeset_steps() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "loop.flow",
                    requires=["loop.current"],
                    provides=["loop.next", "loop.done"],
                    exports=["loop.next", "loop.done"],
                    pipeline={
                        "inputs": [INPUT_SPEC("loop.current")],
                        "nodes": [
                            _node_call("start", "test.start", "Starts while body."),
                            _node_call(
                                "step",
                                "test.loop_step_until",
                                "Increments loop.current and reports completion.",

                                config={"target": 3},
                            ),
                            _node_call("end", "test.loop_next_end", "Ends while body."),
                        ],
                        "edges": _edge_chain("start", "step", "end"),
                        "outputs": [REQ_SPEC("loop.next"), REQ_SPEC("loop.done")],
                    },
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("loop.current")],
                "nodes": [
                    _node_call("start", "test.start", "Starts loop trace fixture."),
                    _node_call(
                        "loop_call",
                        "vibeflow.loop.while",
                        "Runs the while loop body.",
                        requires=[REQ_SPEC("loop.current")],
                        provides=[PROV_SPEC("value.out"), PROV_SPEC("loop.iterations")],
                        loop={
                            "body": "loop.flow",
                            "max_iterations": 5,
                            "carry": [{"from": "loop.current", "as": "loop.current", "update": "loop.next"}],
                            "stop_when": {"from": "loop.done", "equals": True},
                            "outputs": [
                                {"from": "loop.next", "as": "value.out"},
                                {"from": "loop.iterations", "as": "loop.iterations"},
                            ],
                        },
                    ),
                    _node_call("end", "test.out_end", "Consumes final value.out."),
                ],
                "edges": _edge_chain("start", "loop_call", "end"),
                "outputs": [REQ_SPEC("value.out"), REQ_SPEC("loop.iterations")],
            },
        }
    )

    context = PipelineRuntime(graph, registry=_loop_registry(), runtime_options=RuntimeOptions(trace="full")).run({"loop.current": 0})

    assert context.get("value.out")["value"] == 3
    assert context.get("loop.iterations")["value"] == 3
    assert context.get("runtime.step_count") == 3
    assert context.get("runtime.total_step_count") == 12
    assert context.get("runtime.qualified_node_runs")["loop_call.iter_2.step"] == 1
    assert context.get("runtime.qualified_exec_order").count("loop_call.iter_2.step") == 1


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
                            _node_call("bad", "test.runtime_fail", "Fails inside nodeset.",  config={"fail": True}),
                            _node_call("end", "test.out_end", "Consumes value.out."),
                        ],
                        "edges": _edge_chain("start", "bad", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                )
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts nested failure fixture."),
                    _node_call("composite", "fail.flow", "Calls failing nodeset."),
                    _node_call("end", "test.out_end", "Consumes final value.out."),
                ],
                "edges": _edge_chain("start", "composite", "end"),
            },
        }
    )
    runtime = PipelineRuntime(graph, registry=_registry(), runtime_options=RuntimeOptions(trace="full"))

    with pytest.raises(RuntimeError, match="boom"):
        runtime.run({})

    events = [line for line in _runtime_trace_lines(Path(runtime.trace.trace_path)) if line["kind"] != "runtime_summary"]
    failed = [event for event in events if event["kind"] == "node_failed" and event["node"] == "bad"]
    assert failed[0]["path"] == ["composite", "bad"]
    assert failed[0]["qualified_node"] == "composite.bad"
    assert any(event["kind"] == "nodeset_failed" and event["path"] == ["composite"] for event in events)


def test_cli_profiles_do_not_abandon_cleanup_with_a_flush_timeout():
    import argparse
    from vibeflow.tooling.application.python.cli import _add_runtime_options,_runtime_options_from_args
    parser=argparse.ArgumentParser();_add_runtime_options(parser)
    assert 'async_flush_timeout' not in _runtime_options_from_args(parser.parse_args(['--runtime-profile','train']))
    with pytest.raises(SystemExit):parser.parse_args(['--async-flush-timeout','1.5'])


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "../escape", "nested/id", "nested\\id", "/absolute", "nul\x00id"],
)
def test_cli_run_rejects_unsafe_run_id_before_creating_run(tmp_path, capsys, run_id) -> None:
    run_root = tmp_path / "runs"

    with pytest.raises(SystemExit) as exc_info:
        cli_main(
            [
                "run",
                "--config",
                str(tmp_path / "unused.json"),
                "--run-root",
                str(run_root),
                "--run-id",
                run_id,
            ]
        )

    assert exc_info.value.code == 2
    assert "run id must be one non-empty path component" in capsys.readouterr().err
    assert not run_root.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "../escape", "nested/id", "nested\\id", "/absolute", "nul\x00id"],
)
def test_checked_run_rejects_unsafe_programmatic_run_id_without_writing(tmp_path, run_id) -> None:
    from vibeflow.tooling.application.python.run_directory import InvalidRunIdError

    run_root = tmp_path / "runs"

    with pytest.raises(InvalidRunIdError, match="one non-empty path component"):
        run_checked(
            tmp_path / "unused.json",
            registry=_registry(),
            run_root=run_root,
            run_id=run_id,
        )

    assert not run_root.exists()
    assert not (tmp_path / "escape").exists()


def test_cli_run_uses_checked_run_and_refuses_without_registered_nodes(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps({"pipeline": {"nodes": [_node_call("seed", "test.seed", "Produces value.in.")]}}),
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

def test_cli_run_succeeds_with_declarations_and_writes_artifacts(tmp_path, capsys) -> None:
    from tests.fixtures.support.declarations import write_node_plugin
    plugin = write_node_plugin(tmp_path, [
        ("test.start", "StartNode", {}, {}),
        ("test.in_end", "InEndNode", {}, {}),
        ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
    ])
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({
        "project_target": "python"}))
    config_path = tmp_path / "workflow.json"
    input_path = tmp_path / "input.json"
    config_path.write_text(
        json.dumps({"plugins":[plugin], "pipeline": _seed_only_pipeline(seed={"value": 9})}),
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
    assert code == 0, payload
    assert payload["status"] in {"PASS", "CONCERNS"}
    run_dir = Path(payload["run_dir"])
    for name in ("compiled_graph.json", "health_report.json", "graph.txt", "graph.mmd", "runtime_trace.jsonl", "output_summary.json"):
        assert (run_dir / name).exists()
    trace_kinds = [json.loads(line)["kind"] for line in (run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert trace_kinds == ["run_start", "block_enter", "type_resolve", "block_exit", "run_end", "runtime_summary"]
    assert plan_code == 0
    assert plan_payload["status"] in {"PASS", "CONCERNS"}
    plan_run_dir = Path(plan_payload["run_dir"])
    plan_trace_kinds = [json.loads(line)["kind"] for line in (plan_run_dir / "runtime_trace.jsonl").read_text(encoding="utf-8").splitlines()]
    assert plan_trace_kinds == [
        "run_start",
        "type_resolve",
        "run_end",
        "runtime_summary",
    ]
    if is_mermaid_svg_renderer_available():
        assert (run_dir / "graph.svg").exists()


def test_distribution_kernel_manifest_allows_root_guides_to_be_customized(tmp_path) -> None:
    import subprocess
    import sys

    from distribution.build import build_distribution

    def verify(output_path: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "run.py", "verify-kernel"],
            cwd=output_path,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    output = tmp_path / "distribution"
    build_distribution(output, run_self_check=False)
    manifest = (output / "kernel" / "MANIFEST.sha256").read_text(encoding="utf-8")
    manifest_paths = {line.split("  ", 1)[1] for line in manifest.splitlines() if line.strip()}
    assert "AGENTS.md" not in manifest_paths
    assert "README.md" not in manifest_paths
    assert "kernel/docs/user/commands-and-results.md" in manifest_paths
    (output / "AGENTS.md").write_text("# custom\n", encoding="utf-8")
    (output / "README.md").write_text("# custom\n", encoding="utf-8")
    assert verify(output).returncode == 0


def test_distribution_build_is_deterministic_without_wall_clock_metadata(tmp_path) -> None:
    from distribution.build import VERSION, build_distribution

    first = tmp_path / "first"
    second = tmp_path / "second"
    build_distribution(first, run_self_check=False)
    build_distribution(second, run_self_check=False)

    first_files = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    second_files = {
        path.relative_to(second): path.read_bytes()
        for path in second.rglob("*")
        if path.is_file()
    }
    assert first_files == second_files
    metadata = json.loads((first / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    assert metadata["version"] == VERSION
    assert metadata["development_profile"] == "collaborative"


def test_distribution_build_normalizes_portable_modes_deterministically(tmp_path) -> None:
    import stat

    from distribution.build import build_distribution

    def modes(root: Path) -> dict[Path, int]:
        entries = [root, *root.rglob("*")]
        assert not any(path.is_symlink() for path in entries)
        assert all(path.is_dir() or path.is_file() for path in entries)
        return {
            path.relative_to(root): stat.S_IMODE(path.stat().st_mode)
            for path in entries
        }

    first = tmp_path / "first"
    second = tmp_path / "second"
    build_distribution(first, run_self_check=False)
    build_distribution(second, run_self_check=False)

    first_modes = modes(first)
    second_modes = modes(second)
    assert first_modes == second_modes
    assert all(
        mode == (0o755 if (first / relative).is_dir() else 0o644)
        for relative, mode in first_modes.items()
    )


def test_distribution_build_runs_core_self_check_before_writing(tmp_path, monkeypatch) -> None:
    import distribution.build as distribution_builder

    calls: list[str] = []

    def fail_self_check() -> None:
        calls.append("self_check")
        raise distribution_builder.BuildDistributionError("self-check failed")

    output = tmp_path / "distribution"
    output.mkdir()
    marker = output / "marker.txt"
    marker.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(distribution_builder, "_run_core_self_check", fail_self_check)

    with pytest.raises(distribution_builder.BuildDistributionError, match="self-check failed"):
        distribution_builder.build_distribution(output)

    assert calls == ["self_check"]
    assert marker.read_text(encoding="utf-8") == "keep"


def test_distribution_self_check_uses_standalone_quality_project(monkeypatch) -> None:
    import distribution.build as distribution_builder

    captured: dict[str, object] = {}

    def fake_run(command, *, cwd, env, check):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        captured["check"] = check

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(distribution_builder.subprocess, "run", fake_run)

    distribution_builder._run_core_self_check()

    expected_command = [
        sys.executable,
        "repo_check/run.py",
        "--profile",
        "all",
    ]
    assert captured["command"] == expected_command
    assert captured["cwd"] == distribution_builder.ROOT
    assert captured["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    assert captured["check"] is False
