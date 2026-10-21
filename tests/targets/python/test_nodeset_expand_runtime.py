"""Collapsed definitions execute the same native Nodeset and Loop plans."""

from dataclasses import replace

import pytest

from tests.targets.python.strict_runtime import _loop_registry, _while_loop_graph
from vibeflow.core.contracts import PipelineOutputSpec
from vibeflow.core.flow import LoopSpec
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
@pytest.mark.parametrize("kind", ["nodeset", "loop"])
def test_expand_false_preserves_outputs_trace_and_workflow_execution_abi(tmp_path, execution, kind):
    original = _while_loop_graph(target=3)
    if kind == "nodeset":
        original = replace(original, nodes=(original.nodes[0],
            replace(original.nodes[1], definition_id="loop.step_until", provides=original.nodeset_types["loop.step_until"].provides,
                loop=LoopSpec()),
            replace(original.nodes[2], definition_id="test.loop_next_end")),
            outputs=(PipelineOutputSpec("loop.next", "exactly_one"), PipelineOutputSpec("loop.done", "exactly_one")))
    outputs, portable, orders = [], [], []
    for expand in (True, False):
        graph = replace(original, nodeset_types={key: replace(item, expand=expand) for key, item in original.nodeset_types.items()})
        runtime = PipelineRuntime(graph, registry=_loop_registry(), run_dir=tmp_path / str(expand),
            runtime_options=RuntimeOptions(execution=execution, trace="full"))
        portable.append(runtime._plan.to_workflow_plan(workflow_id="display-metadata").to_json())
        result = runtime.run({"loop.current": 0})
        keys = ("loop.next", "loop.done") if kind == "nodeset" else ("loop.final", "loop.iterations")
        outputs.append(tuple(result.get(key)["value"] for key in keys))
        orders.append(result.get("runtime.qualified_exec_order"))
        assert graph.nodeset_types["loop.step_until"].graph.nodes
    expected = (1, False) if kind == "nodeset" else (3, 3)
    assert outputs == [expected, expected]
    assert portable[0] == portable[1]
    assert orders[0] == orders[1]
    assert any("step" in item for item in orders[1])
