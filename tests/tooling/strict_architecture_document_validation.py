from __future__ import annotations

import json
from copy import deepcopy

import pytest

from vibeflow.tooling.application.python.presentation.architecture_validation import architecture_regenerate_command, check_architecture_document
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document, load_raw_config_document
from vibeflow.tooling.project.document_kinds import ARCHITECTURE_DOCUMENT_HEADER


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


def _source_payload():
    return {
        "workflow": {"source": "main.jsonc"},
        "implementation_graph": {
            "files": {"file:demo": {"path": "node.py", "load_state": "not_loaded", "owners": [
                {"kind": "node", "id": "demo", "role": "entry", "symbol": "Demo"}]}},
            "resources": {"node:demo": {
                "rulesets": ["vibeflow.process"],
                "effective_rules": {"static": [{"ruleset_id": "vibeflow.process"}]},
                "effective_presentation": {"values": {"fill": "#abcdef", "shape": "rect"}},
                "origin": {"plugin_id": "demo", "path": "plugin.py", "line": 2},
                "metadata": {"load_state": "business-value"},
                "sources": [{"path": "node.py", "symbol": "Demo", "language": "python",
                             "role": "entry", "load_state": "not_loaded"}],
            }},
            "relations": [{"from": "node:demo", "to": "file:demo", "relation": "entry"}],
        },
    }


@pytest.mark.parametrize("file_state,resource_state", [
    ("loaded", "loaded"), ("unknown", "loaded"), ("loaded", "unknown"),
])
def test_architecture_freshness_allows_valid_load_state_observations(tmp_path, file_state, resource_state):
    payload = _source_payload()
    observed = deepcopy(payload)
    observed["implementation_graph"]["files"]["file:demo"]["load_state"] = file_state
    observed["implementation_graph"]["resources"]["node:demo"]["sources"][0]["load_state"] = resource_state
    path = tmp_path / "ARCHITECTURE.jsonc"
    path.write_text(_expected(observed))
    assert _check(path, payload, _expected(payload), workflow=tmp_path / "main.jsonc") is None
    assert json.loads(path.read_text().removeprefix(ARCHITECTURE_DOCUMENT_HEADER)) == observed


@pytest.mark.parametrize("section", ["file", "resource"])
@pytest.mark.parametrize("state", ["missing", "invalid", None, [], {}])
def test_architecture_freshness_keeps_missing_and_invalid_load_states(tmp_path, section, state):
    payload = _source_payload()
    observed = deepcopy(payload)
    graph = observed["implementation_graph"]
    record = graph["files"]["file:demo"] if section == "file" else graph["resources"]["node:demo"]["sources"][0]
    if state == "missing":
        record.pop("load_state")
    else:
        record["load_state"] = state
    path = tmp_path / "ARCHITECTURE.jsonc"
    path.write_text(_expected(observed))
    finding = _check(path, payload, _expected(payload), workflow=tmp_path / "main.jsonc")
    assert finding.rule_id == "ARCHITECTURE.DOCUMENT.STALE"
    assert all(item.endswith(".load_state") for item in finding.details["difference_paths"])


@pytest.mark.parametrize("mutation", ["file_path", "source_path", "symbol", "rules", "effective_rules",
    "color", "shape", "origin", "owner", "relation", "metadata"])
def test_architecture_freshness_preserves_structure_checks_with_new_load_state(tmp_path, mutation):
    payload = _source_payload()
    changed = deepcopy(payload)
    graph = changed["implementation_graph"]
    file = graph["files"]["file:demo"]
    resource = graph["resources"]["node:demo"]
    file["load_state"] = resource["sources"][0]["load_state"] = "loaded"
    if mutation == "file_path": file["path"] = "moved.py"
    elif mutation == "source_path": resource["sources"][0]["path"] = "moved.py"
    elif mutation == "symbol": resource["sources"][0]["symbol"] = "Other"
    elif mutation == "rules": resource["rulesets"] = []
    elif mutation == "effective_rules": resource["effective_rules"]["static"][0]["ruleset_id"] = "custom"
    elif mutation == "color": resource["effective_presentation"]["values"]["fill"] = "#fedcba"
    elif mutation == "shape": resource["effective_presentation"]["values"]["shape"] = "hex"
    elif mutation == "origin": resource["origin"]["path"] = "other_plugin.py"
    elif mutation == "owner": file["owners"][0]["id"] = "other"
    elif mutation == "relation": graph["relations"][0]["relation"] = "support"
    else: resource["metadata"]["load_state"] = "changed-business-value"
    path = tmp_path / "ARCHITECTURE.jsonc"
    path.write_text(_expected(changed))
    finding = _check(path, payload, _expected(payload), workflow=tmp_path / "main.jsonc")
    assert finding.rule_id == "ARCHITECTURE.DOCUMENT.STALE"
    assert finding.details["difference_paths"]
    assert all(not item.endswith(".load_state") or ".metadata." in item
               for item in finding.details["difference_paths"])


def test_architecture_load_observations_do_not_bypass_canonical_format(tmp_path):
    payload = _source_payload()
    changed = deepcopy(payload)
    changed["implementation_graph"]["files"]["file:demo"]["load_state"] = "loaded"
    path = tmp_path / "ARCHITECTURE.jsonc"
    path.write_text(_expected(changed) + "\n")
    finding = _check(path, payload, _expected(payload), workflow=tmp_path / "main.jsonc")
    assert finding.rule_id == "ARCHITECTURE.DOCUMENT.NON_CANONICAL"
