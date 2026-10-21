"""Reuse one tiny Nodeset while preserving opaque objects and loop reports."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
sys.path[:0] = [str(FIXTURE.parents[2]), str(FIXTURE.parents[2] / "src")]
from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.addition_sandboxes import events, main, value, workspace, assert_artifacts
from vibeflow.core.findings import HealthReport
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.runtime.planning import build_execution_plan
from vibeflow.tooling.application.python.project.core import build_workspace_environment
from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph, run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


class Box:
    def __init__(self):
        self.value = 2


class Counter:
    def __init__(self):
        self.steps = 0


def assert_result(context, box, counter, expected, steps):
    assert value(context, "object.box_after") is box
    assert value(context, "object.counter_after") is counter
    assert box.value == expected and counter.steps == steps
    assert value(context, "object.snapshot") == {"value": expected, "steps": steps}
    metadata = value(context, "object.metadata")
    assert metadata["box"] is box and metadata["tags"] == {"sandbox", "add"}
    assert metadata["unstable"] != metadata["unstable"]
    assert value(context, "object.done") is (steps >= 2)


def run(work, *, toolchain=None):
    workspace_path = workspace(FIXTURE, work)
    output = artifact_directory(work)
    loaded = load_workspace_config(workspace_path)
    observations = []
    cases = [("single", "plan", 5, 1, None), ("override", "plan", 10, 1, None),
        ("fixed", "plan", 14, 4, [5, 8, 11, 14]), ("fixed", "block", 14, 4, [5, 8, 11, 14]),
        ("fixed", "compiled", 14, 4, [5, 8, 11, 14]), ("conditional", "plan", 8, 2, [5, 8])]
    prepared_cases = {}
    for name, execution, expected, steps, history in cases:
        config = work / "project/configs" / (name + ".jsonc")
        if name not in prepared_cases:
            box, counter = Box(), Counter()
            checked = run_workspace_checked(config, workspace=loaded, run_root=output / "checked", run_id=name,
                initial={"object.box": box, "object.counter": counter}, runtime_options=RuntimeOptions(trace="full"))
            assert_result(checked.context, box, counter, expected, steps)
            assert_artifacts(checked.run_dir)
            environment = build_workspace_environment(loaded, config_path=config)
            prepared = _prepare_workspace_graph(config, workspace=loaded, env=environment)
            assert not isinstance(prepared, HealthReport), prepared
            prepared_cases[name] = environment, prepared
        environment, prepared = prepared_cases[name]
        options = RuntimeOptions(trace="full", execution=execution)
        plan = build_execution_plan(prepared.graph, prepared.compilation.compiled_graph, registry=environment.registry, runtime_options=options)
        frame = plan.frame("step" if history is None else "loop")
        if name == "conditional":
            frame = frame.subplan.frame("step")
        assert list(frame.subplan.order) == ["start", "add", "report", "end"]
        assert frame.subplan.frame("add").params["delta"] == (8 if name == "override" else 3)
        if history is None or name == "conditional":
            assert [provider.key for provider in frame.exports] == ["object.box_after", "object.counter_after", "object.snapshot", "object.metadata", "object.value", "object.done"]
        box, counter = Box(), Counter()
        run_dir = output / "runtime" / (name + "-" + execution)
        runtime = PipelineRuntime(prepared.graph, registry=environment.registry, runtime_options=options, run_dir=run_dir)
        context = runtime.run({"object.box": box, "object.counter": counter})
        assert_result(context, box, counter, expected, steps)
        trace = events(run_dir / "runtime_trace.jsonl")
        summary = trace[-1]
        assert summary["stop_reason"] == "completed" and summary["current_node"] == "end"
        assert summary["exec_order"] == ["start", "step" if history is None else "loop", "end"]
        if history is not None:
            assert value(context, "object.history") == history
            assert value(context, "loop.iterations") == steps
            reports = value(context, "object.metadata_history")
            assert len(reports) == steps and all(item["box"] is box and item["tags"] == {"sandbox", "add"} and item["unstable"] != item["unstable"] for item in reports)
            kinds = [event["kind"] for event in trace]
            assert kinds.count("loop_iteration") == steps
            kind = "loop" if execution == "plan" else "loop_block"
            assert kinds.count(kind + "_enter") == kinds.count(kind + "_exit") == 1
            paths = summary["qualified_exec_order"]
            for index in range(steps):
                prefix = f"loop.iter_{index}." + ("step." if name == "conditional" else "")
                assert paths.count(prefix + "add") == paths.count(prefix + "report") == 1
            if name == "conditional":
                assert kinds.count("nodeset_enter") == kinds.count("nodeset_exit") == 2
            if execution == "plan":
                assert summary["node_runs"] == {"start": 1, "loop": 1, "end": 1}
                assert summary["step_count"] == 3 and summary["total_step_count"] == (17 if name == "conditional" else 19), summary
        checks = {condition:"PASS" for condition in ("object_identity", "attributes_and_reports", "non_json_records",
            "subplan_order_and_binding", "run_summary", "artifacts")}
        if history is None or name == "conditional":
            checks["nodeset_exports"] = "PASS"
        if history is not None:
            checks.update({condition:"PASS" for condition in ("loop_carry_collect", "stop_signal", "iteration_events", "qualified_paths")})
        observations.append({"case": name, "execution": execution, "result": expected, "steps": steps, "history": history, "identity": "preserved", "qualified_node_runs": summary["qualified_node_runs"], "checks": checks})
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "Python object addition")
