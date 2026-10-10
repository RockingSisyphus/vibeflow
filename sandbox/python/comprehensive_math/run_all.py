"""One checked application, then reuse its graph for a table of runtime inputs."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter


FIXTURE = Path(__file__).resolve().parent
REPOSITORY = FIXTURE.parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src")]

from tests.fixtures.support.comprehensive_math import SCENARIOS, assert_warning_feedback, expected_order
from vibeflow.core.findings import HealthReport
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.targets.python.runtime.planning import build_execution_plan
from vibeflow.tooling.application.python.project.core import build_workspace_environment
from vibeflow.tooling.application.python.workspace_service import _prepare_workspace_graph, run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def _value(context, key):
    value = context.get(key)
    return value["value"] if isinstance(value, Mapping) and "value" in value else value.value if hasattr(value, "value") else value


def _capabilities(case, received, sent):
    def receive(request):
        received.append(dict(request))
        return {"value": case["x"]}

    def send(request):
        sent.append(dict(request))

    return {"vibeflow.port": {"receive": receive, "send": send}}


def _assert_result(case, context, trace_path, received, sent):
    assert _value(context, "result") == case["result"], context.to_dict()
    assert _value(context, "history") == case["history"], context.to_dict()
    assert _value(context, "iterations") == 3, context.to_dict()
    assert received == [{"port": "math.in"}], received
    assert sent == [{"port": "math.out", "value": case["result"]}], sent
    events = [json.loads(line) for line in trace_path.read_text().splitlines()]
    iterations = [event for event in events if event["kind"] == "loop_iteration"]
    assert len(iterations) == 3, iterations
    assert [event["path"] for event in iterations] == [["loop", f"iter_{index}"] for index in range(3)], iterations
    summary = next(event for event in events if event["kind"] == "runtime_summary")
    assert summary["exec_order"] == expected_order(case), summary
    runs = summary["node_runs"]
    assert runs[case["selected"]] == 1 and runs.get({"square": "negative", "negative": "square"}[case["selected"]], 0) == 0, runs
    assert runs["choice"] == runs["join"] == 1, runs
    assert summary["stop_reason"] == "completed", summary
    qualified = summary["qualified_exec_order"]
    assert "prepare.inner.affine" in qualified, qualified
    assert [name for name in qualified if name.startswith("loop.iter_") and name.endswith(".step")] == [f"loop.iter_{index}.step" for index in range(3)], qualified
    return {"name": case["name"], "result": case["result"], "history": case["history"], "node_runs": runs}


def run(work):
    started = perf_counter()
    shutil.copytree(FIXTURE / "project", work / "project", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copy2(FIXTURE / "vibeflow_config.jsonc", work / "vibeflow_config.jsonc")
    workspace_path = work / "vibeflow_config.jsonc"
    config = work / "project/configs/formula.jsonc"
    workspace = load_workspace_config(workspace_path)
    checked_case = SCENARIOS[0]
    received, sent = [], []
    checked = run_workspace_checked(config, workspace=workspace, run_root=work / "checked", run_id="positive",
        runtime_options=RuntimeOptions(trace="full"), capabilities=_capabilities(checked_case, received, sent))
    warning_counts = assert_warning_feedback(checked.health.to_dict())
    observations = [_assert_result(checked_case, checked.context, checked.run_dir / "runtime_trace.jsonl", received, sent)]
    for name in ("architecture.jsonc", "graph.mmd", "graph.svg", "graph.expanded.svg"):
        assert (checked.run_dir / name).is_file(), name
    mermaid = (checked.run_dir / "graph.mmd").read_text()
    assert all(name in mermaid for name in ("prepare", "loop", "choice", "join", "receive", "send")), mermaid

    environment = build_workspace_environment(workspace, config_path=config)
    prepared = _prepare_workspace_graph(config, workspace=workspace, env=environment)
    assert not isinstance(prepared, HealthReport), prepared
    plan = build_execution_plan(prepared.graph, prepared.compilation.compiled_graph,
        registry=environment.registry)
    portable = plan.to_workflow_plan(workflow_id="comprehensive.math")
    inner = next(block for block in portable.blocks if any(node.id == "affine" for node in block.nodes))
    assert [node.id for node in inner.nodes] == ["start", "affine", "end"]
    assert all([node.completion, node.schedule, node.executor] == ["immediate", "inline", "current"] for node in inner.nodes)
    assert not inner.tasks
    prepare_frame = plan.frame("prepare")
    inner_frame = prepare_frame.subplan.frame("inner")
    affine_params = inner_frame.subplan.frame("affine").params
    assert {key: affine_params.get(key) for key in ("gain", "shift")} == {"gain": 3, "shift": 2}, affine_params
    assert prepare_frame.subplan.frame("subtract").params.get("amount") == 3
    assert list(prepare_frame.subplan.order) == ["start", "inner", "subtract", "end"]
    assert [provider.key for provider in prepare_frame.exports] == ["q"]
    assert [provider.key for provider in inner_frame.exports] == ["scaled"]

    def execute(case, execution="plan", *, driver=None):
        if driver is None:
            received, sent, port_input = [], [], dict(case)
            run_dir = work / "runtime" / (case["name"] + "-" + execution)
            runtime = PipelineRuntime(prepared.graph, registry=environment.registry,
                runtime_options=RuntimeOptions(trace="full", execution=execution), run_dir=run_dir,
                capabilities=_capabilities(port_input, received, sent))
            driver = {"runtime": runtime, "input": port_input, "received": received,
                      "sent": sent, "trace": run_dir / "runtime_trace.jsonl"}
        # Only the test-owned Port input changes; the runtime uses its public API.
        driver["input"].update(case)
        driver["received"].clear()
        driver["sent"].clear()
        result = driver["runtime"].run({"math.offset": case["offset"]} if "offset" in case else {})
        observation = _assert_result(case, result, driver["trace"], driver["received"], driver["sent"])
        observation["execution"] = execution
        return observation, driver

    driver = None
    for case in SCENARIOS:
        observation, driver = execute(case, driver=driver)
        observations.append(observation)
    for execution in ("block", "compiled"):
        for case in SCENARIOS[:2]:
            observations.append(execute(case, execution)[0])
    with ThreadPoolExecutor(max_workers=2) as executor:
        jobs = [executor.submit(execute, {**case, "name": "concurrent-" + case["name"]}) for case in SCENARIOS[:2]]
        observations.extend(job.result()[0] for job in jobs)

    # A real source edit must remove both custom warnings while leaving native
    # warnings in place. The original fixture is never edited.
    square = work / "project/nodes/square.py"
    square.write_text(square.read_text().replace('        return ', '        padding = "tttttttttt"\n        return ', 1))
    command = [sys.executable, "-m", "vibeflow", "validate", "--workspace", str(workspace_path), "--config", str(config), "--json"]
    completed = subprocess.run(command, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(REPOSITORY / "src")})
    assert completed.returncode == 0, completed.stdout + completed.stderr
    repaired = json.loads(completed.stdout)
    assert_warning_feedback(repaired, repaired=True)
    (work / "repaired-health.json").write_text(json.dumps(repaired, ensure_ascii=False, indent=2))
    report = {"target": "python", "status": "PASS", "seconds": round(perf_counter() - started, 3),
              "warnings": warning_counts, "observations": observations, "source_repair": "PASS"}
    (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Python comprehensive math: PASS observations={len(observations)} seconds={report['seconds']} report={work / 'report.json'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="retain the temporary project and reports here")
    parser.add_argument("--renderer-root", type=Path, help="reuse an installed Mermaid/Puppeteer toolchain")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-python-math-") as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        renderer = args.renderer_root or (Path(os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"]) if os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT") else None)
        if renderer is None:
            renderer = work / "renderer"
            renderer.mkdir()
            for name in ("package.json", "package-lock.json"):
                shutil.copy2(REPOSITORY / "tools/mermaid-renderer" / name, renderer / name)
            subprocess.run(["npm", "ci"], cwd=renderer, check=True)
        os.environ["VIBEFLOW_MERMAID_RENDERER_ROOT"] = str(renderer.resolve())
        run(work)


if __name__ == "__main__":
    main()
