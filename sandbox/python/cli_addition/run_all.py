"""Delegate real argv, files and stdin to a three-number addition workflow."""
from pathlib import Path
import json
import re
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
sys.path[:0] = [str(FIXTURE.parents[2]), str(FIXTURE.parents[2] / "src")]
from tests.fixtures.support.addition_sandboxes import cli, events, main, workspace, assert_artifacts


def run(work, *, toolchain=None):
    config_workspace = workspace(FIXTURE, work)
    observations = []
    for mode in ("yaml", "pathlib", "streams"):
        config = work / "project/configs" / (mode + ".jsonc")
        output = work / (mode + "-sum.txt")
        left = work / "project/data" / ("numbers.yaml" if mode == "yaml" else "left.txt")
        right = work / "project/data/right.txt"
        architecture = work / (mode + "-architecture.jsonc")
        exported = cli(["export-architecture", "--workspace", config_workspace, "--config", config, "--output", architecture])
        assert not output.exists() and architecture.is_file(), "architecture export executed business I/O"
        assert b"sum=" not in exported.stdout
        completed = cli(["delegate-cli", "--workspace", config_workspace, "--config", config,
            "--run-root", work / "runs", "--run-id", mode, "--", "--left", left, "--right", right,
            "--output", output, "--verbose"], stdin=b"4\n")
        stderr = b"writer=open\n" if mode == "streams" else b"writer=pathlib\n"
        assert completed.stdout == b"sum=9\n" and completed.stderr == stderr, (completed.stdout, completed.stderr)
        assert output.read_bytes() == b"9\n"
        run_dir = work / "runs" / mode
        health = json.loads((run_dir / "health_report.json").read_text())
        assert health["status"] in {"PASS", "CONCERNS"} and not health["errors"], health
        declared = json.loads(config.read_text())["pipeline"]["nodes"]
        scopes = health["info"]["node_effect_scopes"]
        for node in declared:
            name = node["id"]
            expected = "terminal" if name in {"parse_argv", "read_stdin", "write_output"} else "python_io" if name.startswith("read_") or name == "write_file" else "none"
            assert scopes[name] == expected, (name, scopes)
        summary = events(run_dir / "runtime_trace.jsonl")[-1]
        assert summary["kind"] == "runtime_summary" and summary["stop_reason"] == "completed"
        assert summary["qualified_node_runs"] == {node["id"]: 1 for node in declared}, summary
        exit_summary = json.loads((run_dir / "output_summary.json").read_text())["cli.exit_code"]
        assert exit_summary["data_type"] == "cli.exit_code" and exit_summary["value"] == {"scalar": True, "type": "int"}
        log = (run_dir / "vibeflow.log").read_text()
        assert "CLI.DELEGATE.END" in log and "exit_code=0" in log
        for text in (str(left), str(right), str(output), "sum=9", stderr.decode().strip()):
            assert text not in log, text
        assert not re.search(r"\b(?:stdin|input|content|payload|value|left|right|output)\s*[:=]\s*['\"]?[2349]\b", log, re.I)
        assert_artifacts(run_dir)
        observations.append({"mode": mode, "inputs": [2, 3, 4], "result": 9, "exit_code": 0, "node_runs": summary["qualified_node_runs"], "effect_scopes": scopes,
            "checks": {name:"PASS" for name in ("argv_and_readers", "exact_stdio", "output_file", "exit_and_summary",
                "effect_scopes", "single_execution", "log_isolation", "export_without_business_io", "artifacts")}})
    return {"status": "PASS", "observations": observations}


if __name__ == "__main__":
    main(run, "Python CLI addition")
