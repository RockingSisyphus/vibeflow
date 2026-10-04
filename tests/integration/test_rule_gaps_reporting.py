"""New API acceptance must retain real failures and incomplete observation groups."""

import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location("gaps_" + name, ROOT / "sandbox/rule_gaps" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load("run_all")
COMMON = load("common")


def case(case_id="example", *, actual_status="PASS", handler_called=True):
    return {"id": case_id, "title": "Real handler acceptance", "family": "source_api",
            "classification": "new_feature", "expected": {"should_accept": True,
            "metrics": {"handler_called": True}}, "actual": {"status": actual_status,
            "codes": [], "positions": [], "metrics": {"handler_called": handler_called}}}


def test_skipped_handler_is_not_a_passing_positive_control():
    row, = RUNNER.assess([case(handler_called=False)])
    assert row["mismatches"] == ["metric handler_called: expected True, got False"]


def test_invalid_reported_state_survives_normalization():
    process = subprocess.CompletedProcess([], 0, '{"status":"unknown"}', "")
    row = case()
    row["actual"] = COMMON.normalize(process, metrics={"handler_called": True})
    assert RUNNER.assess([row])[0]["mismatches"]


def test_unrelated_exception_cannot_replace_declaration_rejection():
    row = case(actual_status="ERROR")
    row["expected"] = {"should_accept": False, "codes": ["DESCRIPTOR.INVALID"],
                       "message_contains": "shape", "metrics": {"json_output": True}}
    process = subprocess.CompletedProcess([], 1, "", "TypeError: unhashable type: dict")
    row["actual"] = COMMON.normalize(process)
    mismatches = RUNNER.assess([row])[0]["mismatches"]
    assert any("missing diagnostics" in reason for reason in mismatches)
    assert any("json_output" in reason for reason in mismatches)


def test_duplicate_ids_cannot_inflate_coverage():
    with pytest.raises(ValueError, match="duplicate case IDs"):
        RUNNER.assess([case(), case()])


@pytest.mark.parametrize("payload", [[], {}, [{"id": "incomplete"}]])
def test_empty_or_incomplete_group_is_an_observation_error(tmp_path, monkeypatch, payload):
    def run(*args, **kwargs):
        (tmp_path / "python/observations.json").write_text(json.dumps(payload))
        return subprocess.CompletedProcess([], 0)
    monkeypatch.setattr(RUNNER.subprocess, "run", run)
    with pytest.raises(ValueError):
        RUNNER.observe("python", tmp_path, None, None)


@pytest.mark.parametrize("broken_group", [False, True])
def test_report_distinguishes_acceptance_failure_from_observation_failure(tmp_path, monkeypatch, broken_group):
    def observe(*args, **kwargs):
        if broken_group:
            raise RuntimeError("worker did not produce observations")
        return [case("normal"), case("broken", handler_called=False)]
    monkeypatch.setattr(RUNNER, "observe", observe)
    report = tmp_path / "report.json"
    exit_code = RUNNER.run(tmp_path / "work", ("python",), report)
    result = json.loads(report.read_text())
    assert exit_code == (2 if broken_group else 1)
    if broken_group:
        assert result["summary"]["process_errors"] == 1
        assert result["summary"]["cases"] == 0
    else:
        assert result["summary"]["matched"] == 1
        assert result["summary"]["unmatched"] == 1
        assert not result["errors"]
