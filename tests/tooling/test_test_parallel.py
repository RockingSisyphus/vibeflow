"""Verification concurrency, isolation and error reporting."""

import argparse
import json
from pathlib import Path
from threading import Lock
import time

import pytest

from tests.fixtures.rule_gaps import run_all as gaps
from tools import run_tests, verify_project
from tools.test_parallel import WORKER_ENVIRONMENT, add_worker_argument


def parse_workers(arguments=()):
    parser = argparse.ArgumentParser()
    add_worker_argument(parser)
    return parser.parse_args(arguments).workers


@pytest.mark.parametrize("runner", [run_tests, verify_project])
def test_in_repository_scratch_is_rejected_before_creating_work(runner, tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    work = tmp_path / "dist" / "regression-work"
    with pytest.raises(SystemExit) as error:
        runner.main(["--scratch", str(work)])
    assert error.value.code == 2
    assert not work.exists()


def test_default_environment_and_cli_precedence(monkeypatch):
    monkeypatch.delenv(WORKER_ENVIRONMENT, raising=False)
    assert parse_workers() == 12
    assert run_tests._parser().parse_args([]).workers == 12
    assert verify_project._parser().parse_args([]).workers == 12
    monkeypatch.setenv(WORKER_ENVIRONMENT, "3")
    assert parse_workers() == 3
    assert parse_workers(["--workers", "2"]) == 2
    monkeypatch.setenv(WORKER_ENVIRONMENT, "invalid")
    assert parse_workers(["--workers", "1"]) == 1


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "invalid"])
def test_invalid_workers_are_cli_errors(monkeypatch, value):
    with pytest.raises(SystemExit) as error:
        parse_workers(["--workers", value])
    assert error.value.code == 2
    monkeypatch.setenv(WORKER_ENVIRONMENT, value)
    with pytest.raises(SystemExit) as error:
        parse_workers()
    assert error.value.code == 2


@pytest.mark.parametrize("workers", [1, 2, 8, 12])
def test_rule_jobs_share_one_bounded_pool(tmp_path, monkeypatch, workers):
    active = peak = 0
    lock = Lock()
    calls = []

    def observe(group, work, toolchain, renderer, family, part, *, workers):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
            calls.append((group, family, part, workers))
        time.sleep(0.03)
        with lock:
            active -= 1
        case_id = ".".join(filter(None, (group, family, part)))
        return [{"id": case_id, "title": case_id, "family": "unit",
                 "classification": "new_feature", "expected": {"should_accept": True},
                 "actual": {"status": "PASS", "codes": []}}]

    monkeypatch.setattr(gaps, "observe", observe)
    monkeypatch.setattr(gaps, "validate_counts", lambda rows: None)
    report = tmp_path / "report.json"
    status = gaps.run(tmp_path / "work", gaps.GROUPS, report,
                      toolchain=tmp_path, renderer=tmp_path, workers=workers)
    result = json.loads(report.read_text())
    assert status == 0
    assert peak == min(workers, len(calls))
    assert len(calls) == 19
    assert len({(group, family, part) for group, family, part, _ in calls}) == 19
    assert all(count == workers for _, _, _, count in calls)
    assert result["workers"] == workers
    assert result["summary"]["matched"] == 19


def test_parallel_observation_error_remains_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(gaps, "observe", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("marker failure")))
    report = tmp_path / "report.json"
    assert gaps.run(tmp_path / "work", ("python",), report, workers=8) == 2
    result = json.loads(report.read_text())
    assert result["summary"]["process_errors"] == 1
    assert "marker failure" in result["errors"][0]["error"]


def test_verify_forwards_worker_count(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(verify_project, "_run", lambda command, **kwargs: commands.append(command))
    monkeypatch.setattr(verify_project, "_puppeteer_root", lambda scratch: scratch / "renderer")
    verify_project._pytest(tmp_path, workers=2)
    verify_project._rule_regressions(tmp_path, workers=2)
    assert len(commands) == 3
    for command in commands:
        values = list(map(str, command))
        assert values[values.index("--workers") + 1] == "2"
