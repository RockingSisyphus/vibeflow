"""Small integer arithmetic with linear, split, joined and data bypass graphs."""
from collections import Counter
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
sys.path[:0] = [str(FIXTURE.parents[2]), str(FIXTURE.parents[2] / "src")]
from tests.fixtures.support.addition_sandboxes import assert_artifacts, events, main, value, workspace
from vibeflow.core.findings import HealthReport
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.runtime.planning import build_execution_plan
from vibeflow.tooling.application.python.project.core import build_workspace_environment
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph, run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config

# Hand-written expected values: (a,b,c,d), u, v, branch, w, result.
INPUTS = [
    ((2, 3, 1, 2), 5, 3, "left", 6, 11),
    ((1, 1, 2, 3), 2, 5, "right", 4, 6),
    ((1, 2, 1, 2), 3, 3, "left", 4, 7),
]
MODES = [("plan", "full", True), ("compiled", "boundary", False), ("compiled", "full", False)]


def assert_result(context, topology, case):
    numbers, u, v, branch, w, result = case
    assert value(context, "u") == u
    if topology == "linear":
        assert value(context, "selected_w") == 6 and value(context, "copied") == 6
        assert value(context, "result") == 5
    else:
        assert value(context, "selected_w") == w
        selected = context.get("selected_w")
        assert (selected["key"] if isinstance(selected, dict) else selected.key) == branch + ".w"
        if topology in {"split", "join"}:
            assert value(context, "v") == v and value(context, "route") == branch
            inactive = "right" if branch == "left" else "left"
            if topology == "split":
                assert value(context, branch + ".result") == result
                assert not context.exists(inactive + ".result")
        if topology != "split":
            assert value(context, "result") == result
            assert value(context, "selected.key") == branch + ".w"


def expected_order(topology, branch):
    if topology == "linear":
        return ["start", "u", "left", "copy", "finish", "end"]
    if topology == "bypass":
        return ["start", "u", "left", "finish", "end"]
    prefix = ["start", "u", "v", "compare", branch]
    return prefix + ([branch + "_end"] if topology == "split" else ["finish", "end"])


def run(work, *, toolchain=None):
    loaded = load_workspace_config(workspace(FIXTURE, work))
    observations = []
    for topology in ("linear", "split", "join", "bypass"):
        config = work / "project/configs" / (topology + ".jsonc")
        cases = INPUTS if topology in {"split", "join"} else INPUTS[:1]
        input_keys = ("a", "b", "c", "d") if topology in {"split", "join"} else ("a", "b")
        initial = dict(zip(input_keys, cases[0][0]))
        checked = run_workspace_checked(config, workspace=loaded, run_root=work / "checked", run_id=topology,
            initial=initial, runtime_options=RuntimeOptions(trace="full"))
        assert_result(checked.context, topology, cases[0])
        assert_artifacts(checked.run_dir)
        environment = build_workspace_environment(loaded, config_path=config)
        prepared = _prepare_workspace_graph(config, workspace=loaded, env=environment)
        assert not isinstance(prepared, HealthReport), prepared
        declaration = json.loads(config.read_text())["pipeline"]
        declared_nodes = [node["id"] for node in declaration["nodes"]]
        if topology == "bypass":
            assert declaration["edges"][4] == {"from": "u", "to": "finish"}
            marker = "linkStyle 4 stroke-dasharray:6 4,stroke-width:2px;"
            exported = export_mermaid(prepared.graph, registry=environment.registry,
                compiled=prepared.compilation.compiled_graph, resources=prepared.resources, health_report=checked.health)
            (work / "bypass-export.mmd").write_text(exported)
            assert marker in exported and marker in (checked.run_dir / "graph.mmd").read_text()
        for execution, trace_level, hooks in MODES:
            options = RuntimeOptions(execution=execution, trace=trace_level, node_hooks=hooks)
            plan = build_execution_plan(prepared.graph, prepared.compilation.compiled_graph,
                registry=environment.registry, runtime_options=options)
            sources = []
            if execution == "compiled":
                assert [list(block.nodes) for block in plan.blocks] == [declared_nodes]
                for block in plan.blocks:
                    source_path = work / "compiled_sources" / f"{topology}-{trace_level}-{block.entry}.py"
                    source_path.parent.mkdir(exist_ok=True)
                    source_path.write_text(block.source)
                    source = source_path.read_text()
                    assert "runtime._run_compiled_frame" in source and "_run_node(" not in source
                    sources.append(str(source_path.relative_to(work)))
            for case_index, case in enumerate(cases):
                numbers, u, v, branch, w, result = case
                initial = dict(zip(input_keys, numbers))
                run_dir = work / "runtime" / f"{topology}-{execution}-{trace_level}-{case_index}"
                runtime = PipelineRuntime(prepared.graph, registry=environment.registry,
                    runtime_options=options, run_dir=run_dir)
                context = runtime.run(initial)
                assert_result(context, topology, case)
                trace = events(run_dir / "runtime_trace.jsonl")
                summary = trace[-1]
                order = expected_order(topology, branch)
                assert list(value(context, "runtime.exec_order")) == order
                assert summary["exec_order"] == order and summary["current_node"] == order[-1], summary
                assert summary["node_runs"] == dict.fromkeys(order, 1), summary
                assert summary["step_count"] == len(order) and summary["stop_reason"] == "completed", summary
                counts = Counter(event["kind"] for event in trace)
                if execution == "compiled":
                    assert counts["block_enter"] == counts["block_exit"] == 1, counts
                assert counts["node"] == (len(order) if trace_level == "full" else 0), counts
                if trace_level == "full":
                    for edge in declaration["edges"]:
                        source, target = edge["from"], edge["to"]
                        # Data deliveries can also be recorded for inactive branch targets.
                        if source in order and ("when" not in edge or target in order):
                            assert summary["edge_executions"][source + "->" + target] == 1, summary
                    if topology in {"split", "join", "bypass"}:
                        consumer = branch + "_end" if topology == "split" else "finish"
                        resolved = [event["details"] for event in trace if event["kind"] == "type_resolve"
                            and event["details"]["consumer"] == consumer
                            and event["details"]["required_type"] == "selected_w"]
                        assert len(resolved) == 1 and resolved[0]["matched_count"] == 1
                        assert resolved[0]["resolved_source_keys"] == [branch + ".w"]
                checks = {name: "PASS" for name in ("intermediate_and_final_values", "execution_order",
                    "node_runs_and_stop", "trace_events", "artifacts")}
                if trace_level == "full":
                    checks["edge_executions"] = "PASS"
                if topology in {"split", "join"}:
                    checks["inactive_branch_not_executed"] = "PASS"
                if topology == "join":
                    checks["exactly_one_semantic_provider_and_source_key"] = "PASS"
                if topology == "bypass":
                    checks["data_bypass_export_and_run_diagrams"] = "PASS"
                if execution == "compiled":
                    checks["block_nodes_and_saved_source"] = "PASS"
                observations.append(dict(topology=topology, execution=execution, trace=trace_level,
                    inputs=initial, result=5 if topology == "linear" else result,
                    order=order, checks=checks, compiled_sources=sources))
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "Python piecewise math")
