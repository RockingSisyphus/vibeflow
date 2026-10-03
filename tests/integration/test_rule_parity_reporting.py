"""The comparative sandbox must report losses, false rejects, and broken fixtures."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "sandbox/rule_parity/results.py"
SPEC = importlib.util.spec_from_file_location("parity_results", SOURCE)
RESULTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RESULTS)


def observation(*, actual_codes=(), status="PASS", expected_codes=(), accept=True, **expected):
    return {"id": "sample", "title": "A real rule scenario", "family": "source",
            "classification": "preserved",
            "expected": {"should_accept": accept, "codes": list(expected_codes), **expected},
            "actual": {"status": status, "codes": list(actual_codes), "metrics": {}, "positions": []}}


def code(value, severity="error"):
    return {"code": value, "severity": severity}


def test_warning_disappearance_is_a_regression_despite_both_versions_accepting():
    baseline = observation(actual_codes=[code("NEAR_LIMIT", "warning")], status="CONCERNS",
                           expected_codes=[code("NEAR_LIMIT", "warning")])
    current = observation(expected_codes=[code("NEAR_LIMIT", "warning")])
    row, = RESULTS.compare([baseline], [current])
    assert row["outcome"] == "regression"
    assert "NEAR_LIMIT" in row["current_mismatches"][0]


def test_unrelated_failure_does_not_mask_the_rule_under_test():
    baseline = observation(actual_codes=[code("IMPORT_FORBIDDEN")], status="FAIL",
                           expected_codes=[code("IMPORT_FORBIDDEN")], accept=False)
    current = observation(actual_codes=[code("WORKSPACE_BROKEN")], status="FAIL",
                          expected_codes=[code("IMPORT_FORBIDDEN")], accept=False)
    assert RESULTS.compare([baseline], [current])[0]["outcome"] == "regression"


def test_new_rejection_of_valid_control_is_a_regression():
    assert RESULTS.compare([observation()], [observation(status="FAIL", actual_codes=[code("NEW_ERROR")])])[0]["outcome"] == "regression"


def test_baseline_fixture_failure_is_not_a_confirmed_product_regression():
    baseline = observation(status="ERROR", expected_codes=[code("PURITY")], accept=False)
    current = observation(actual_codes=[code("PURITY")], status="FAIL", expected_codes=[code("PURITY")], accept=False)
    assert RESULTS.compare([baseline], [current])[0]["outcome"] == "baseline_fixture_failure"


def test_new_feature_has_no_invented_baseline_observation():
    current = observation()
    current["classification"] = "new_feature"
    assert RESULTS.compare([], [current])[0]["outcome"] == "matched"
    current["classification"] = "preserved"
    assert RESULTS.compare([], [current])[0]["outcome"] == "baseline_fixture_failure"


def test_missing_current_case_is_not_silently_ignored():
    assert RESULTS.compare([observation()], [])[0]["outcome"] == "regression"


def test_exact_diagnostics_catch_new_unexpected_warnings():
    current = observation(actual_codes=[code("EXTRA", "warning")], status="CONCERNS", exact_codes=True)
    assert RESULTS.mismatch(current) == ["unexpected diagnostics: [('EXTRA', 'warning')]"]


def test_metrics_and_source_locations_are_observed_independently():
    current = observation(metrics={"chain.length": 5}, located_codes=["SOURCE.ERROR"])
    current["actual"]["metrics"] = {"chain": {"length": 2}}
    reasons = RESULTS.mismatch(current)
    assert any("expected 5, got 2" in reason for reason in reasons)
    assert "missing file/line for SOURCE.ERROR" in reasons


def test_duplicate_case_ids_are_a_fixture_error():
    with pytest.raises(ValueError, match="duplicate case IDs"):
        RESULTS.compare([observation(), observation()], [])


def test_generic_exception_code_must_also_explain_the_expected_branch():
    current = observation(status="ERROR", actual_codes=[code("GraphConfigError")],
                          expected_codes=[code("GraphConfigError")], accept=False,
                          message_contains="loop.max_iterations")
    current["actual"]["message"] = "duplicate node id"
    assert RESULTS.mismatch(current) == ["missing diagnostic reason: loop.max_iterations"]


def process_failure_observation():
    row = observation(status="ERROR", accept=False,
                      metrics={"transport": "uncaught_exception", "exit_code": 1},
                      message_contains="contract_payload")
    row["expected"]["status"] = "ERROR"
    row["actual"].update(metrics={"transport": "uncaught_exception", "exit_code": 1},
                         message="Traceback: contract_payload failed to serialize invalid data")
    row["classification"] = "baseline_limitation"
    return row


def test_explicit_old_cli_crash_can_be_observed_without_forging_a_rule_finding():
    assert RESULTS.mismatch(process_failure_observation()) == []


def test_an_unrelated_exception_cannot_satisfy_the_expected_old_cli_crash():
    row = process_failure_observation()
    row["actual"]["message"] = "ModuleNotFoundError: missing environment dependency"
    assert RESULTS.mismatch(row) == ["missing diagnostic reason: contract_payload"]


@pytest.mark.parametrize("missing", ["status", "message_contains", "metrics"])
def test_incomplete_process_failure_expectations_do_not_hide_errors(missing):
    row = process_failure_observation()
    del row["expected"][missing]
    assert "execution failed without the expected rule diagnostic" in RESULTS.mismatch(row)


def test_expected_cli_crash_does_not_substitute_for_a_required_rule_diagnostic():
    row = process_failure_observation()
    row["expected"]["codes"] = [code("REQUIRED_CONTRACT_ERROR")]
    assert RESULTS.mismatch(row) == ["missing diagnostics: [('REQUIRED_CONTRACT_ERROR', 'error')]"]


@pytest.mark.parametrize("status", ["failed", "unavailable", "unknown", "", None])
def test_incomplete_or_unknown_observation_cannot_appear_as_acceptance(status):
    assert RESULTS.compare([observation()], [observation(status=status)])[0]["outcome"] == "regression"
