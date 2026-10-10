"""Shared observations and independently specified golden values, not business code."""

from pathlib import Path


SCENARIOS = (
    {"name": "positive", "x": 4, "result": 480, "history": [236, 238, 240], "selected": "square"},
    {"name": "negative", "x": -3, "result": 20, "history": [6, 8, 10], "selected": "negative"},
    {"name": "zero_input", "x": 0, "result": 32, "history": [12, 14, 16], "selected": "square"},
    {"name": "optional_offset", "x": 4, "offset": 7, "result": 487, "history": [236, 238, 240], "selected": "square"},
    {"name": "repeat", "x": 1, "result": 90, "history": [41, 43, 45], "selected": "square"},
    {"name": "branch_boundary", "x": -1, "result": 10, "history": [1, 3, 5], "selected": "square"},
)


def expected_order(case):
    return ["start", "receive", "offset", "prepare", "companion", "route",
            case["selected"], "choice", "join", "loop", "finish", "send"]


def assert_warning_feedback(report, *, repaired=False):
    assert not report.get("errors"), report
    warnings = report.get("warnings", [])
    custom = [item for item in warnings if item["code"] in {"MATH.MIN_T", "MATH.T_ADVICE"}]
    assert sorted(item["code"] for item in custom) == ([] if repaired else ["MATH.MIN_T", "MATH.T_ADVICE"]), custom
    for item in custom:
        assert item["severity"] == "warning" and item["object_id"] == "math.square", item
        assert item["definition_id"] == {"MATH.MIN_T": "math.min_t", "MATH.T_ADVICE": "math.t_advice"}[item["code"]], item
        location = item["source_location"]
        path = Path(location["path"])
        assert path.stem == "square" and location["line"] == (4 if path.suffix == ".py" else 1) and location["column"] == 1, item
        assert item["message"] and item["details"]["minimum"] == 10, item
        assert item["details"]["actual"] == 6, item
        calls = item["details"].get("calls", [])
        paths = item["details"].get("call_paths", [])
        assert any(call["node"] == "square" for call in calls) or ["square"] in paths, item
    if custom:
        assert custom[0]["details"]["actual"] == custom[1]["details"]["actual"], custom
        advice = next(item for item in custom if item["code"] == "MATH.T_ADVICE")
        assert advice["details"]["record_type"] == "math.t_count.v1", advice
    native = [item for item in warnings if item["code"] == "NODE.PURITY.SOURCE_NEAR_LIMIT"]
    assert native, warnings
    assert all(item["details"]["limit"] == 4 and item["details"]["lines"] >= 4 for item in native), native
    assert {"math.affine", "math.step"} <= {item["object_id"] for item in native}, native
    allowed = {"MATH.MIN_T", "MATH.T_ADVICE", "NODE.PURITY.SOURCE_NEAR_LIMIT", "BASE_LIB.SOURCE.NEAR_LIMIT", "GRAPH.SMELL.DUPLICATE_LOGIC"}
    assert all(item["severity"] == "warning" and item["code"] in allowed for item in warnings), warnings
    assert report["status"] == "CONCERNS", report
    return {"custom_warnings": len(custom), "native_source_warnings": len(native)}
