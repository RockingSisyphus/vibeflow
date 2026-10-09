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
        "code_security",
        "general_execution_semantics",
        "determinism",
        "all_side_effects",
        "effect_boundaries",
        "node_relationships",
        "direct_input_writes",
        "source_quality",
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


def test_empty_selection_does_not_claim_optional_source_checks():
    payload = add_result_scope({"status":"PASS", "rule_executions":[]}, "vibeflow_quality")
    assert payload["checked"] == []


def test_completed_rule_outputs_define_coverage_including_custom_effect_rules():
    execution = {"plan":{"calls":[{"id":"custom", "rule_id":"example.effects"},
        {"id":"input", "rule_id":"vibeflow.input_writes"}]}, "results":{
        "custom":{"state":"completed", "records":{"policy":{"type_id":"vibeflow.effect_policy.v1", "value":{}}}},
        "input":{"state":"unavailable", "records":{}}}}
    payload = add_result_scope({"status":"PASS", "info":{"rule_executions":[execution]}}, "vibeflow_quality")
    assert [item["id"] for item in payload["checked"]] == ["effect_boundaries"]
