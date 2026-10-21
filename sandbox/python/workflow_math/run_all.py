"""Nested integer addition, loop stopping positions and execution/trace matrix."""
from collections import Counter
import json
import re
from pathlib import Path
import sys
sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
sys.path[:0] = [str(FIXTURE.parents[2]), str(FIXTURE.parents[2] / "src")]
from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.preview import preview_directory, preview_architecture
from tests.fixtures.support.addition_sandboxes import main, workspace, value, events, assert_artifacts
from vibeflow.core.findings import HealthReport
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.runtime.planning import build_execution_plan
from vibeflow.tooling.application.python.project.core import build_workspace_environment
from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph, run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


class Hooks:
    """An external test observer; the business Plugin remains an SDK resource."""
    def __init__(self):
        self.calls = []
    def before_node(self, *args):
        self.calls.append("before_node")
    def after_node(self, *args):
        self.calls.append("after_node")
    def after_run(self, *args):
        self.calls.append("after_run")


ROOT_ORDER = {
    "retry": ["start", "retry_loop", "end"],
    "wrapped_retry": ["start", "wrapper", "end"],
    "outer_fixed": ["start", "seed", "outer_loop", "end"],
    "outer_condition": ["start", "seed", "outer_loop", "end"],
    "nested": ["start", "arithmetic", "use_scaled", "finalize", "end"],
}


def check_summary(summary, name):
    order = ROOT_ORDER[name]
    assert summary["exec_order"] == order, summary
    assert summary["current_node"] == "end", summary
    assert summary["step_count"] == len(order), summary
    assert summary["node_runs"] == {node: 1 for node in order}, summary
    assert summary["edge_executions"] == {
        f"{a}->{b}": 1 for a, b in zip(order, order[1:])}, summary


def check(context, trace, row):
    for key, expected in row["expected_outputs"].items():
        assert value(context, key) == expected, (key, value(context, key), expected)
    summary = trace[-1]
    check_summary(summary, row["config"])
    assert list(value(context, "runtime.exec_order")) == ROOT_ORDER[row["config"]]
    assert summary["stop_reason"] == "completed" and not summary["exception"], summary
    for key, expected in row.get("expected_trace_summary", {}).items():
        if key == "edge_executions":
            assert all(summary[key].get(k) == v for k, v in expected.items()), summary
        else:
            assert summary[key] == expected, summary
    counts = Counter(event["kind"] for event in trace)
    for kind, count in row.get("expected_trace_kind_counts", {}).items():
        assert counts[kind] == count, (kind, counts)
    if "expected_runtime_exec_order" in row:
        assert list(value(context, "runtime.exec_order")) == row["expected_runtime_exec_order"]
    assert all(path in summary["qualified_exec_order"] for path in row.get("expected_qualified_exec_contains", []))


def run(work, *, toolchain=None):
    loaded = load_workspace_config(workspace(FIXTURE, work))
    output = artifact_directory(work)
    rows = json.loads((FIXTURE / "expectations.json").read_text())
    # The same nested formula (4+6)*2+5=25 observes all execution/trace settings.
    for execution in ("plan", "block", "compiled"):
        for trace in ("full", "boundary", "off"):
            rows.append(dict(config="nested", initial={"calc.a":4,"calc.b":6},
                expected_outputs={"calc.scaled":20,"calc.branch":20,"calc.final":25},
                runtime_options=dict(execution=execution,trace=trace,node_hooks=trace != "full")))
    prepared_cases, observations = {}, []
    for index, row in enumerate(rows):
        name = row["config"]
        if name not in prepared_cases:
            config = work / "project/configs" / (name + ".jsonc")
            checked = run_workspace_checked(config, workspace=loaded, initial=row["initial"],
                run_root=output / "checked", run_id=name, runtime_options=RuntimeOptions(trace="full"))
            for key, expected in row["expected_outputs"].items():
                assert value(checked.context,key) == expected
            assert_artifacts(checked.run_dir)
            facts=preview_architecture(checked.run_dir)
            visible=json.dumps(facts,ensure_ascii=False)
            for text in row.get("expected_architecture_text_contains",[]):
                assert text in visible, text
            env = build_workspace_environment(loaded, config_path=config)
            prepared = _prepare_workspace_graph(config, workspace=loaded, env=env)
            assert not isinstance(prepared, HealthReport), prepared
            prepared_cases[name] = env, prepared
        env, prepared = prepared_cases[name]
        options = RuntimeOptions(**row.get("runtime_options", {}))
        plan = build_execution_plan(prepared.graph, prepared.compilation.compiled_graph,
            registry=env.registry, runtime_options=options)
        if name == "nested":
            frame = plan.frame("arithmetic")
            assert list(frame.subplan.order) == ["start","add_pair","scale","end"]
            assert frame.subplan.frame("scale").params["factor"] == 2
            assert [p.key for p in frame.exports] == ["calc.scaled"]
        if "expected_blocks" in row:
            assert [list(b.nodes) for b in plan.blocks] == row["expected_blocks"]
        if options.execution in {"block","compiled"}:
            assert plan.blocks
            for block_index, block in enumerate(plan.blocks):
                path = work / f"source-{index}-{block_index}.py"
                path.write_text(block.source)
                if block.kind == "graph":
                    assert "return run_graph_block(runtime, state," in path.read_text()
                    assert "_run_node(" not in path.read_text()
        hooks = Hooks()
        plugins = PluginRegistry()
        plugins.register(hooks, plugin_type="runtime")
        run_dir = output / "runtime" / str(index)
        context = PipelineRuntime(prepared.graph, registry=env.registry, plugin_registry=plugins,
            runtime_options=options, run_dir=run_dir).run(dict(row["initial"]))
        trace = events(run_dir / "runtime_trace.jsonl")
        check(context, trace, row)
        assert "after_run" in hooks.calls
        assert ("before_node" in hooks.calls) == options.node_hooks
        assert ("after_node" in hooks.calls) == options.node_hooks
        if name == "nested":
            kinds = [event["kind"] for event in trace]
            if options.trace == "off":
                assert kinds == ["runtime_summary"]
            elif options.trace == "boundary":
                assert "node" not in kinds
                if options.execution == "plan":
                    assert [kind for kind in kinds if kind != "type_resolve"] == ["run_start","nodeset_enter","run_start","run_end","nodeset_exit","run_end","runtime_summary"], kinds
            else:
                assert kinds.count("node") == 8, kinds
            if options.execution == "compiled" and options.trace != "off":
                assert kinds.count("block_enter") == kinds.count("block_exit") == 2
        checks = {k:"PASS" for k in ("numbers", "order_and_stop", "trace_and_paths", "hooks", "artifacts")}
        if name == "nested":
            checks["plan_binding_and_exports"] = "PASS"
        if options.execution in {"block","compiled"}:
            checks["compiled_sources"] = "PASS"
        observations.append(dict(config=name, options=dict(execution=options.execution,trace=options.trace,
            node_hooks=options.node_hooks), outputs=row["expected_outputs"],
            summary=trace[-1], checks=checks))
    return dict(status="PASS", observations=observations)


if __name__ == "__main__":
    main(run, "Python workflow math")
