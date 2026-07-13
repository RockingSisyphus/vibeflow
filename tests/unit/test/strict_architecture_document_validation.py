from __future__ import annotations

import json

from vibeflow.architecture_validation import architecture_regenerate_command, check_architecture_document
from vibeflow.config.loader import ConfigLoadError, load_config_document, load_raw_config_document
from vibeflow.rendering.architecture_document import ARCHITECTURE_DOCUMENT_HEADER


def _expected(payload: dict[str, object]) -> str:
    return ARCHITECTURE_DOCUMENT_HEADER + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _check(path, payload, text, *, workflow):
    return check_architecture_document(
        path,
        expected_payload=payload,
        expected_text=text,
        workflow_path=workflow,
    )


def test_architecture_document_check_accepts_only_exact_canonical_text(tmp_path) -> None:
    workflow = tmp_path / "main.jsonc"
    workflow.write_text("{}", encoding="utf-8")
    document = tmp_path / "ARCHITECTURE.jsonc"
    payload = {"workflow": {"source": "main.jsonc"}, "nodesets": {}, "node_types": {}, "resources": {}}
    expected = _expected(payload)
    document.write_text(expected, encoding="utf-8")

    assert _check(document, payload, expected, workflow=workflow) is None

    document.write_text(expected + "\n", encoding="utf-8")
    finding = _check(document, payload, expected, workflow=workflow)
    assert finding is not None
    assert finding.rule_id == "ARCHITECTURE.DOCUMENT.NON_CANONICAL"
    assert "regenerate it with:" in finding.message
    assert finding.details["difference_paths"] == ["$.__canonical_text__"]


def test_architecture_document_check_reports_missing_header_jsonc_and_stale(tmp_path) -> None:
    workflow = tmp_path / "main.jsonc"
    workflow.write_text("{}", encoding="utf-8")
    document = tmp_path / "ARCHITECTURE.jsonc"
    payload = {"workflow": {"source": "main.jsonc"}, "nodesets": {}, "node_types": {}, "resources": {}}
    expected = _expected(payload)

    missing = _check(document, payload, expected, workflow=workflow)
    assert missing is not None
    assert missing.rule_id == "ARCHITECTURE.DOCUMENT.MISSING"
    assert missing.details["document_path"] == str(document)
    assert missing.details["difference_paths"] == ["$"]

    document.write_text(json.dumps(payload), encoding="utf-8")
    header = _check(document, payload, expected, workflow=workflow)
    assert header is not None
    assert header.rule_id == "ARCHITECTURE.DOCUMENT.HEADER"
    assert header.details["difference_paths"] == ["$.__header__"]

    document.write_text(ARCHITECTURE_DOCUMENT_HEADER + "{broken", encoding="utf-8")
    invalid = _check(document, payload, expected, workflow=workflow)
    assert invalid is not None
    assert invalid.rule_id == "ARCHITECTURE.DOCUMENT.JSONC"
    assert invalid.source_location["path"] == str(document)
    assert invalid.details["difference_paths"] == ["$"]

    document.write_text(_expected({**payload, "resources": {"plugins": ["changed"]}}), encoding="utf-8")
    stale = _check(document, payload, expected, workflow=workflow)
    assert stale is not None
    assert stale.rule_id == "ARCHITECTURE.DOCUMENT.STALE"
    assert stale.details["difference_count"] >= 1
    assert any(path.startswith("$.resources") for path in stale.details["difference_paths"])


def test_architecture_document_is_raw_readable_but_not_executable_config(tmp_path) -> None:
    path = tmp_path / "main.architecture.jsonc"
    payload = {"workflow": {}, "nodesets": {}, "node_types": {}, "resources": {}}
    path.write_text(_expected(payload), encoding="utf-8")

    assert load_raw_config_document(path).data == payload
    try:
        load_config_document(path)
    except ConfigLoadError as exc:
        assert exc.rule_id == "CONFIG.ARCHITECTURE_DOCUMENT.NON_EXECUTABLE"
        assert "vibeflow_project.jsonc" in exc.message
    else:
        raise AssertionError("architecture document must not load as an executable workflow")

    path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        load_config_document(path)
    except ConfigLoadError as exc:
        assert exc.rule_id == "CONFIG.ARCHITECTURE_DOCUMENT.NON_EXECUTABLE"
    else:
        raise AssertionError("removing the generated header must not make the document executable")


def test_architecture_regenerate_command_prefers_distribution_wrapper(tmp_path) -> None:
    workspace = tmp_path / "vibeflow_config.jsonc"
    workspace.write_text("{}", encoding="utf-8")
    (tmp_path / "run.py").write_text("", encoding="utf-8")
    workflow = tmp_path / "project" / "configs" / "main.jsonc"
    document = tmp_path / "project" / "ARCHITECTURE.jsonc"

    command = architecture_regenerate_command(workflow, document, workspace_path=workspace)

    assert command == "python run.py architecture --config project/configs/main.jsonc --output project/ARCHITECTURE.jsonc"
