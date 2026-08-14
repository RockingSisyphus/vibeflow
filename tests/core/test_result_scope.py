from __future__ import annotations

from vibeflow.core.result_scope import add_result_scope, format_result_scope


def test_scope_preserves_status_and_moves_structured_legacy_summary() -> None:
    payload = add_result_scope(
        {"status": "PASS", "summary": {"files": 3}},
        "vibeflow_quality",
        checked_ids=("project_structure",),
    )
    assert payload["status"] == "PASS"
    assert payload["result_code"] == "VIBEFLOW_QUALITY_PASS"
    assert payload["details_summary"] == {"files": 3}
    assert payload["summary"] == "VibeFlow 项目质量检查通过"
    assert payload["checked"] == [{"id": "project_structure", "label": "项目结构"}]
    assert {item["id"] for item in payload["not_checked"]} == {
        "business_correctness",
        "requirements_conformance",
        "external_semantics",
        "domain_data_correctness",
    }


def test_failure_text_does_not_claim_success() -> None:
    payload = add_result_scope(
        {"status": "FAIL"},
        "vibeflow_structure",
        checked_ids=(),
    )
    text = format_result_scope(payload)
    assert "VIBEFLOW_STRUCTURE_FAIL" in text
    assert "通过" not in text
    assert "未检查" in text
