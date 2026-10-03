"""Semantic comparisons for the baseline sandbox, without importing VibeFlow."""

from __future__ import annotations

from collections import Counter


def _codes(rows):
    return {(row["code"], row.get("severity", "error")) if isinstance(row, dict)
            else (str(row), "error") for row in rows}


def _metric(metrics, path):
    if path in metrics:
        return metrics[path]
    value = metrics
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise KeyError(path)
        value = value[key]
    return value


def mismatch(observation):
    """A different rejection cannot satisfy the expected rule rejection."""
    expected, actual = observation["expected"], observation["actual"]
    wanted = _codes(expected.get("codes", ()))
    received = _codes(actual.get("codes", ()))
    reasons = []
    if actual.get("status") not in {"PASS", "CONCERNS", "FAIL", "ERROR"}:
        reasons.append("invalid observation status: " + repr(actual.get("status")))
    if wanted - received:
        reasons.append("missing diagnostics: " + repr(sorted(wanted - received)))
    if expected.get("exact_codes") and received - wanted:
        reasons.append("unexpected diagnostics: " + repr(sorted(received - wanted)))
    forbidden = {row[0] for row in received} & set(expected.get("forbidden_codes", ()))
    if forbidden:
        reasons.append("forbidden diagnostics: " + repr(sorted(forbidden)))
    errors = {row for row in received if row[1] == "error"}
    rejected = actual.get("status") not in {"PASS", "CONCERNS"} or bool(errors)
    should_accept = expected.get("should_accept", not any(row[1] == "error" for row in wanted))
    if rejected == should_accept:
        reasons.append("expected acceptance" if should_accept else "expected rejection")
    # An explicitly documented old CLI crash is an observation of a baseline
    # limitation, never evidence that a requested Rule emitted its diagnostic.
    metrics = expected.get("metrics", {})
    exit_code = metrics.get("exit_code")
    expected_process_failure = (
        expected.get("status") == "ERROR" and not should_accept
        and metrics.get("transport") == "uncaught_exception"
        and isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
        and bool(expected.get("message_contains"))
    )
    # Infrastructure errors and unrelated exceptions are not rule findings.
    if actual.get("status") == "ERROR" and not (wanted & errors) and not expected_process_failure:
        reasons.append("execution failed without the expected rule diagnostic")
    if "status" in expected and actual.get("status") != expected["status"]:
        reasons.append(f"status: expected {expected['status']}, got {actual.get('status')}")
    fragments = expected.get("message_contains", ())
    if isinstance(fragments, str):
        fragments = (fragments,)
    for fragment in fragments:
        if fragment not in actual.get("message", ""):
            reasons.append("missing diagnostic reason: " + fragment)
    for path, wanted_value in expected.get("metrics", {}).items():
        try:
            received_value = _metric(actual.get("metrics", {}), path)
        except KeyError:
            reasons.append("missing metric: " + path)
            continue
        if received_value != wanted_value:
            reasons.append(f"metric {path}: expected {wanted_value!r}, got {received_value!r}")
    for code in expected.get("located_codes", ()):
        positions = [row for row in actual.get("positions", ()) if row.get("code") == code]
        if not any(row.get("path") and isinstance(row.get("line"), int) and row["line"] > 0 for row in positions):
            reasons.append("missing file/line for " + code)
    return reasons


def compare(baseline, current):
    """Keep baseline fixture errors separate from confirmed regressions."""
    for name, rows in (("baseline", baseline), ("current", current)):
        duplicates = [key for key, count in Counter(row["id"] for row in rows).items() if count > 1]
        if duplicates:
            raise ValueError(name + " duplicate case IDs: " + repr(duplicates))
    before = {row["id"]: row for row in baseline}
    after = {row["id"]: row for row in current}
    findings = []
    for case_id in sorted(before.keys() | after.keys()):
        old, new = before.get(case_id), after.get(case_id)
        classification = (new or old).get("classification", "preserved")
        if old is None and classification == "new_feature":
            old_failures = []
        elif old is None:
            old_failures = ["case missing from baseline observations"]
        else:
            old_failures = mismatch(old)
        new_failures = mismatch(new) if new is not None else ["case missing from current observations"]
        outcome = ("baseline_fixture_failure" if old_failures else "regression" if new_failures else "matched")
        findings.append({"id": case_id, "title": (new or old)["title"],
                         "family": (new or old)["family"], "classification": classification,
                         "outcome": outcome, "baseline_mismatches": old_failures,
                         "current_mismatches": new_failures, "baseline": old, "current": new})
    return findings


def summarize(findings):
    return {"cases": len(findings), **dict(Counter(row["outcome"] for row in findings)),
            "classifications": dict(Counter(row["classification"] for row in findings)),
            "families": dict(Counter(row["family"] for row in findings))}
