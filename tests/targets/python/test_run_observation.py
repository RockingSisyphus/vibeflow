"""Live status, immutable info snapshots and console capture through real runs."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import time

import pytest

from vibeflow.core.run_status import snapshot_info
from vibeflow.targets.python.runtime.observation import RunObservation
from vibeflow.targets.python.runtime.options import RuntimeOptions
from vibeflow.targets.python.sdk import update_run_info
from sandbox.python.typing_annotations.probe import observe
from sandbox.python.runtime_observation.probe import observe as observe_cli
from sandbox.python.sdk_defaults.validate_probe import write_project
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def test_annotation_cli_controls(tmp_path):
    result = observe(tmp_path)
    assert result["matched"], result
    for case in result["cases"]:
        if not case["allowed"]:
            finding = next(item for item in case["errors"] if item["code"].endswith("PURITY.BANNED_CALL"))
            assert finding["severity"] == "error"
            assert finding["source_location"]["path"].endswith(("plugin.py", "helper.py"))
            assert finding["source_location"]["line"] > 0


@pytest.mark.parametrize("case_id", ["success", "runtime_failure", "startup_failure"])
def test_real_cli_monitor_and_native_console(tmp_path, case_id):
    result = observe_cli(tmp_path, case_id)
    assert result["matched"], result


@pytest.mark.parametrize("value", [None, {}, [1], [{"x": object()}], [{"x": float("nan")}], [{"x": float("inf")}]] )
def test_info_json_contract(value):
    with pytest.raises(ValueError, match="JSON"):
        snapshot_info(value)


@pytest.mark.parametrize("interval", [0, -1, True, float("inf"), float("nan")])
def test_interval_contract(interval):
    with pytest.raises(ValueError, match="status_interval"):
        RuntimeOptions(status_interval=interval)


def test_live_status_buffering_atomic_reads_and_reset(tmp_path):
    path = tmp_path / "monitor/status.json"
    observer = RunObservation(tmp_path / "one", interval=.02, status_file=path)
    with observer.scope():
        assert json.loads(path.read_text())["state"] == "starting"
        observer.transition("running")
        info = [{"metrics": {"loss": .125}}, {"message": "训练"}]
        update_run_info(info)
        info[0]["metrics"]["loss"] = 999
        deadline = time.monotonic() + 2
        stamps = set()
        while time.monotonic() < deadline:
            record = json.loads(path.read_text())
            stamps.add(record["updated_at"])
            assert datetime.fromisoformat(record["updated_at"].replace("Z", "+00:00")).tzinfo is not None
            if record["info"] and len(stamps) > 1:
                break
            time.sleep(.005)
        assert record["info"][0]["metrics"]["loss"] == .125
        assert len(stamps) > 1
        print("business stdout")
        update_run_info([])
    final = json.loads(path.read_text())
    assert final["state"] == "succeeded" and final["error"] is None and final["info"] == []
    assert "business stdout" in (tmp_path / "one/business.log").read_text()
    assert "business stdout" not in (tmp_path / "one/vibeflow.log").read_text()
    with RunObservation(tmp_path / "two", status_file=path).scope():
        assert json.loads(path.read_text())["info"] == []


def test_failure_final_record_preserves_latest_info(tmp_path):
    with pytest.raises(RuntimeError, match="training failed"):
        with RunObservation(tmp_path).scope() as observer:
            observer.transition("running")
            update_run_info([{"epoch": 10}])
            raise RuntimeError("training failed")
    result = json.loads((tmp_path / "status.json").read_text())
    assert result["state"] == "failed" and result["error"] == "training failed"
    assert result["info"] == [{"epoch": 10}]


def test_same_process_runs_do_not_mix_info_or_output(tmp_path):
    def run(index):
        root = tmp_path / str(index)
        with RunObservation(root, interval=.01).scope():
            update_run_info([{"run": index}])
            print(f"run-{index}")
            time.sleep(.03)
        return json.loads((root / "status.json").read_text())
    with ThreadPoolExecutor(2) as executor:
        records = list(executor.map(run, (0, 1)))
    assert [record["info"] for record in records] == [[{"run": 0}], [{"run": 1}]]
    for index in (0, 1):
        assert (tmp_path / str(index) / "business.log").read_text() == f"run-{index}\n"


def test_default_process_node_can_update_info_and_project_runtime_options(tmp_path):
    write_project(tmp_path, "integer", 1)
    source = tmp_path / "plugin.py"
    source.write_text('from vibeflow.targets.python.sdk import update_run_info\n' + source.read_text().replace(
        '        value = params["cleanup_record_roots"]',
        '        update_run_info([{"loss": .125}])\n        value = params["cleanup_record_roots"]'))
    monitor = tmp_path / "monitor.json"
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python", "runtime": {
        "status_interval": .01, "status_file": str(monitor)}}))
    workspace = load_workspace_config(tmp_path / "vibeflow_config.jsonc")
    run_workspace_checked(config_path=tmp_path / "workflow.jsonc", workspace=workspace, run_root=tmp_path / "runs")
    assert json.loads(monitor.read_text())["info"] == [{"loss": .125}]
    assert json.loads(monitor.read_text())["state"] == "succeeded"


def test_interruption_writes_failed_state(tmp_path):
    with pytest.raises(KeyboardInterrupt):
        with RunObservation(tmp_path).scope():
            raise KeyboardInterrupt
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["state"] == "failed" and status["error"] == "KeyboardInterrupt"
