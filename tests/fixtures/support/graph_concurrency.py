"""Shared public-CLI cases and trace assertions for both concurrency sandboxes."""

from copy import deepcopy
import json
import os
import subprocess
import sys

from .addition_sandboxes import ROOT


SUCCESS_CASES = (("concurrent", "success", None), ("capacity-four", "queue4", 4),
                 ("default-eight", "queue8", 8))
TOPOLOGY_CASES = {
    "collector-dispatch": ("GRAPH.JOIN.FORK_CONFLICT", "error"),
    "disconnected-worker": ("GRAPH.FLOW.CANNOT_REACH_END", "error"),
}


def write_cases(work):
    """Derive small, inspectable variants without maintaining duplicate graphs."""
    directory = work / "project/configs"
    original = json.loads((directory / "concurrent.jsonc").read_text())
    for name, limit in (("capacity-four", 4), ("default-eight", None)):
        data = deepcopy(original)
        start = data["pipeline"]["nodes"][0]
        if limit is None:
            start.pop("config", None)
        else:
            start["config"] = {"max_concurrency": limit}
        (directory / f"{name}.jsonc").write_text(json.dumps(data, indent=2) + "\n")

    for name in TOPOLOGY_CASES:
        data = deepcopy(original)
        graph = data["pipeline"]
        if name == "disconnected-worker":
            graph["edges"].remove(["w11", "collect"])
        else:
            # Empty contracts isolate the topology error from payload errors.
            keep = {"start", "w0", "w1", "w2", "w3", "w4", "collect", "end"}
            graph["nodes"] = [node for node in graph["nodes"] if node["id"] in keep]
            for node in graph["nodes"]:
                if node["id"] not in {"start", "end"}:
                    node["type_used"] = "native.noop"
            graph["outputs"] = []
            next(node for node in graph["nodes"] if node["id"] == "w0")["join_policy"] = "all"
            graph["edges"] = [["start", "w1"], ["start", "w2"], ["w1", "w0"], ["w2", "w0"],
                ["w0", "w3"], ["w0", "w4"], ["w3", "collect"], ["w4", "collect"], ["collect", "end"]]
        (directory / f"{name}.jsonc").write_text(json.dumps(data, indent=2) + "\n")


def check_topology_cases(work):
    observations = []
    javascript = json.loads((work / "project/vibeflow_project.jsonc").read_text())["project_target"] == "javascript"
    for name, (expected_rule, severity) in TOPOLOGY_CASES.items():
        done = subprocess.run([sys.executable, "-m", "vibeflow", "validate", "--workspace",
            str(work / "vibeflow_config.jsonc"), "--config", str(work / f"project/configs/{name}.jsonc"),
            "--json"], capture_output=True, text=True, timeout=60, cwd=work,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
        (work / f"{name}.stdout.json").write_text(done.stdout)
        (work / f"{name}.stderr.log").write_text(done.stderr)
        expected_exit = 1 if severity == "error" else 0
        assert done.returncode == expected_exit, (name, done.returncode, done.stdout[-2000:], done.stderr)
        payload = json.loads(done.stdout)
        def findings(value):
            if isinstance(value, dict):
                if value.get("rule_id") == expected_rule and value.get("severity") == severity:
                    yield value
                for child in value.values():
                    yield from findings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from findings(child)
        assert list(findings(payload)), (name, expected_rule, severity, payload)
        observations.append({"case": name, "execution": "validate", "status": "PASS",
            "expected_rule": expected_rule, "severity": severity, "exit_code": done.returncode})
        out = work / f"rejected-{name}"
        args = [sys.executable, "-m", "vibeflow", "build", "--workspace", str(work / "vibeflow_config.jsonc"),
            "--config", str(work / f"project/configs/{name}.jsonc"), "--out-dir", str(out)]
        if javascript:
            args.extend(["--target", "node", "--profile", "single-esm"])
        built = subprocess.run(args, capture_output=True, text=True, timeout=60, cwd=work,
            env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"})
        (work / f"{name}.build.stdout.json").write_text(built.stdout)
        (work / f"{name}.build.stderr.log").write_text(built.stderr)
        assert built.returncode == 1, (name, built.returncode, built.stdout, built.stderr)
        assert expected_rule in json.dumps(json.loads(built.stdout)), (name, built.stdout)
        assert not out.exists(), (name, "rejected graph published build artifacts")
        observations.append({"case": name, "execution": "build", "status": "PASS",
            "expected_rule": expected_rule, "exit_code": built.returncode})
    return observations


def assert_worker_trace(events, capacity=None):
    """Count real starts/exits and require refill before the first batch drains."""
    active, started, finished = set(), [], []
    peak = collectors = 0
    for event in events:
        kind = event.get("event") if event.get("kind") == "node_trace" else event.get("kind")
        if kind == "collector_started":
            assert not active and len(finished) == 12, (active, finished)
            collectors += 1
        if kind not in {"worker_started", "cleanup_finished"}:
            continue
        index = event["details"]["index"]
        if kind == "worker_started":
            assert index not in started, started
            if capacity is not None and index == capacity:
                assert finished == [capacity - 1], (started, finished)
                assert active == set(range(capacity - 1)), active
            active.add(index)
            started.append(index)
            peak = max(peak, len(active))
            if capacity is not None:
                assert peak <= capacity, (peak, capacity)
        else:
            assert index in active, (index, active)
            active.remove(index)
            finished.append(index)
    assert sorted(started) == sorted(finished) == list(range(12)), (started, finished)
    assert not active and collectors == 1, (active, collectors)
    if capacity is not None:
        assert peak == capacity, (peak, capacity)
    return {"workers": 12, "peak": peak, "collectors": collectors,
            "incremental_refill": capacity is not None}
