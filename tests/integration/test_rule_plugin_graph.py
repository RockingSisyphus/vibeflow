"""The same declarative Rule graph executes through both real Target boundaries."""

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from tests.fixtures.support.rule_sandbox import create_rule_graph_sandbox
from vibeflow.tooling.application.cli import main


@pytest.fixture(params=["python", "javascript"])
def rule_project(tmp_path, request):
    project = create_rule_graph_sandbox(tmp_path, request.param)
    yield project
    sys.modules.pop("rule_graph_nodes", None)


def cli(capsys, arguments):
    code = main(arguments)
    output = capsys.readouterr().out
    return code, json.loads(output)


def findings(payload):
    if isinstance(payload, dict):
        if "code" in payload and "message" in payload:
            yield payload
        for value in payload.values():
            yield from findings(value)
    elif isinstance(payload, list):
        for value in payload:
            yield from findings(value)


def validate(project, capsys):
    return cli(capsys, ["validate", *project.common_arguments(), "--json"])


def configure(project, *, mode="valid", entrypoints=None, relations=()):
    data = project.read(project.graph_resource)
    data["calls"][0]["params"] = {"mode": mode}
    data["relations"].extend(relations)
    if entrypoints is not None:
        data["entrypoints"] = entrypoints
    project.write(project.graph_resource, data)


def business_result(project, capsys):
    if project.target == "python":
        from vibeflow.tooling.application.python import workspace_service
        original = workspace_service.run_workspace_checked
        actual_runs = []
        def observe(*args, **kwargs):
            result = original(*args, **kwargs)
            actual_runs.append(result)
            return result
        # Observe the real return value of the formal command. The public CLI
        # intentionally summarizes value types rather than printing user data.
        with patch.object(workspace_service, "run_workspace_checked", observe):
            code, payload = cli(capsys, ["run", *project.common_arguments(), "--input", str(project.root / "input.json"),
                "--run-root", str(project.root / "runs"), "--run-id", "actual"])
        assert code == 0, payload
        summary = json.loads((project.root / "runs/actual/output_summary.json").read_text())
        assert summary["result"]["data_type"] == "example.output"
        return {"result": actual_runs[0].context.get("result")["value"]}
    code, payload = cli(capsys, ["build", *project.common_arguments(), "--target", "node", "--profile", "single-esm",
        "--out-dir", str(project.root / "dist")])
    assert code == 0, payload
    entry = Path(payload["entry"])
    process = subprocess.run(["node", "--input-type=module", "--eval",
        f"import {{pathToFileURL}} from 'node:url'; const app=await import(pathToFileURL({json.dumps(str(entry))})); console.log(JSON.stringify(await app.runWorkflow({{value:3}})));"],
        capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


@pytest.mark.parametrize(("mode", "exit_code", "total", "error_code"), [
    ("valid", 0, 3, None), ("empty", 0, 0, None), ("warning", 0, 3, "EXAMPLE.PROVIDER.FINDING"),
    ("error", 1, 3, "EXAMPLE.PROVIDER.FINDING"), ("missing", 1, None, "RULE.EXECUTION"),
    ("wrong_type", 1, None, "RULE.EXECUTION"), ("failed", 1, None, None),
    ("unavailable", 1, None, None),
])
def test_jsonc_requires_automatically_binds_real_records_and_blocks_unavailable_consumers(rule_project, capsys, mode, exit_code, total, error_code):
    configure(rule_project, mode=mode, entrypoints={"static": ["checker"]})
    code, payload = validate(rule_project, capsys)
    assert code == exit_code, payload
    events = rule_project.events()
    assert events[0]["handler"] == "provider"
    assert events[0]["phase"] == "static"
    if total is None:
        assert len(events) == 1
        assert any(item["code"] == "RULE.INPUT.UNAVAILABLE" for item in findings(payload)), payload
    else:
        assert [item["handler"] for item in events] == ["provider", "checker"]
        assert events[1]["type_id"] == "example.numbers.v1"
        assert events[1]["total"] == total
        assert events[1]["numbers"] == ([] if mode == "empty" else [3])
    if error_code:
        assert any(item["code"] == error_code for item in findings(payload)), payload
    if mode in ("failed", "unavailable"):
        assert any(item.get("definition_id") == "example.number_provider" and item.get("details", {}).get("state") == mode
            for item in findings(payload)), payload
    if mode in ("warning", "error"):
        finding = next(item for item in findings(payload) if item["code"] == error_code)
        assert finding["definition_id"] == "example.number_provider"
        assert finding["source_location"]["line"] > 0


def test_static_default_has_no_hidden_import_or_run_audits_and_business_really_executes(rule_project, capsys):
    code, payload = validate(rule_project, capsys)
    assert code == 0, payload
    assert {item["phase"] for item in rule_project.events()} == {"static"}
    rule_project.marker.unlink()
    actual = business_result(rule_project, capsys)
    assert not any(item["phase"] in {"import", "run"} for item in rule_project.events())
    assert actual == {"result": 7}


def test_explicit_import_and_run_entrypoints_use_the_same_graph_and_records(rule_project, capsys):
    configure(rule_project, entrypoints={"import": ["checker"], "static": [], "run": ["checker"]})
    code, payload = validate(rule_project, capsys)
    assert code == 0, payload
    assert {item["phase"] for item in rule_project.events()} == {"import"}
    rule_project.marker.unlink()
    actual = business_result(rule_project, capsys)
    assert actual == {"result": 7}
    events = rule_project.events()
    assert {item["phase"] for item in events} == ({"import", "run"} if rule_project.target == "python" else {"import"})
    assert all(item["total"] == 3 for item in events if item["handler"] == "checker")
    if rule_project.target == "javascript":
        # AOT build checks static. Offline runWorkflow executes the business
        # graph without loading arbitrary external Rule workers. The explicit
        # Target run entrance still executes this same typed Rule graph.
        from vibeflow.targets.javascript.quality.rules import run_javascript_rules
        from vibeflow.tooling.project.graph_config import parse_graph_config
        from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs
        rule_project.marker.unlink()
        catalogs = load_project_descriptor_catalogs(rule_project.project)
        graph = parse_graph_config(rule_project.read(rule_project.config), project_root=rule_project.project)
        report = run_javascript_rules(graph, catalogs, project_root=rule_project.project, package_root=rule_project.project, phase="run", target="node")
        result = report.results["example.calculate"][-1].results["checker"]
        assert result.records["proof"].value["total"] == 3
        assert {item["phase"] for item in rule_project.events()} == {"import", "run"}


@pytest.mark.parametrize("replace_provider", [False, True])
def test_nested_shared_includes_keep_instance_parameters_and_replacement_local(rule_project, capsys, replace_provider):
    document = {"kind": "ruleset", "id": "example.rule_graph", "calls": [
        {"id": "left", "ruleset_id": "example.nested"}, {"id": "right", "ruleset_id": "example.nested"}],
        "relations": [{"source": "$self", "target": "left/pair/provider", "kind": "overrides", "params": {"value": 5}}]}
    if replace_provider:
        document["relations"][0]["replace_rule"] = "example.replacement_provider"
    rule_project.write(rule_project.graph_resource, document)
    code, payload = validate(rule_project, capsys)
    assert code == 0, payload
    checks = [item for item in rule_project.events() if item["handler"] == "checker"]
    assert {item["call"]: item["total"] for item in checks} == {"left/pair/checker": 15 if replace_provider else 5, "right/pair/checker": 3}


def test_consumed_provider_local_implementation_replacement_keeps_typed_interface(rule_project, capsys):
    configure(rule_project, entrypoints={"static": ["checker"]}, relations=[
        {"source": "$self", "target": "provider", "kind": "overrides", "replace_rule": "example.replacement_provider"}])
    code, payload = validate(rule_project, capsys)
    assert code == 0, payload
    assert rule_project.events()[-1]["total"] == 13
    code, preview = cli(capsys, ["review-rules", *rule_project.common_arguments(), "--node", "calculate", "--json"])
    assert code == 0, preview
    call = next(item for item in preview["nodes"][0]["plans"][0]["calls"] if item["id"] == "provider")
    assert call["rule_id"] == "example.replacement_provider"
    assert call["original_rule_id"] == "example.number_provider"


def test_explicit_override_precedence_and_equal_or_independent_fields_merge(rule_project, capsys):
    data = rule_project.read(rule_project.graph_resource)
    data["calls"].extend([{"id": "general", "rule_id": "example.number_provider"},
                          {"id": "specific", "rule_id": "example.number_provider"},
                          {"id": "peer", "rule_id": "example.number_provider"}])
    data["relations"].extend([
        {"source": "general", "target": "provider", "kind": "overrides", "params": {"value": 7, "mode": "warning"}},
        {"source": "specific", "target": "provider", "kind": "overrides", "params": {"value": 5}},
        {"source": "peer", "target": "provider", "kind": "overrides", "params": {"mode": "warning"}},
        {"source": "specific", "target": "general", "kind": "overrides"},
    ])
    rule_project.write(rule_project.graph_resource, data)
    code, payload = validate(rule_project, capsys)
    assert code == 0, payload
    assert next(item for item in rule_project.events() if item["handler"] == "checker")["total"] == 5
    code, preview = cli(capsys, ["review-rules", *rule_project.common_arguments(), "--node", "calculate", "--json"])
    assert code == 0, preview
    provider = next(item for item in preview["nodes"][0]["plans"][0]["calls"] if item["id"] == "provider")
    assert provider["params"]["value"] == 5
    assert provider["params"]["mode"] == "warning"
    assert provider["parameter_sources"]["value"] == "override:specific"
    assert provider["parameter_sources"]["mode"] == "override:general,peer"


@pytest.mark.parametrize(("case", "expected"), [("replacement", "RULE.REPLACEMENT.INTERFACE"),
    ("requires", "RULE.REQUIRES.CYCLE"), ("includes", "RULE.INCLUDES.CYCLE"),
    ("includes_relations", "RULE.INCLUDES.CYCLE"),
    ("overrides", "RULE.OVERRIDES.CYCLE"), ("conflict", "RULE.OVERRIDE.CONFLICT"),
    ("binding", "RULE.INPUT.BINDING")])
def test_invalid_rule_graphs_fail_formal_cli_before_external_handlers(rule_project, capsys, case, expected):
    data = rule_project.read(rule_project.graph_resource)
    if case == "replacement":
        data["relations"].append({"source": "$self", "target": "provider", "kind": "overrides", "replace_rule": "example.wrong_provider"})
    elif case == "requires":
        data["relations"].append({"source": "provider", "target": "checker", "kind": "requires"})
    elif case == "includes":
        data["calls"] = [{"id": "recursive", "ruleset_id": "example.rule_graph"}]
        data["relations"] = []
    elif case == "includes_relations":
        data["calls"] = [{"id": "left", "ruleset_id": "example.shared_pair"}, {"id": "right", "ruleset_id": "example.shared_pair"}]
        data["relations"] = [{"source": "left", "target": "right", "kind": "includes"},
                             {"source": "right", "target": "left", "kind": "includes"}]
    elif case == "overrides":
        data["relations"].extend([{"source": "provider", "target": "checker", "kind": "overrides"},
                                  {"source": "checker", "target": "provider", "kind": "overrides"}])
    elif case == "conflict":
        data["calls"].extend([{"id": "specific", "rule_id": "example.number_provider"}, {"id": "general", "rule_id": "example.number_provider"}])
        data["relations"].extend([{"source": "specific", "target": "provider", "kind": "overrides", "params": {"value": 5}},
                                  {"source": "general", "target": "provider", "kind": "overrides", "params": {"value": 7}}])
    else:
        data["relations"][0]["bindings"] = {"numbers": "missing"}
    rule_project.write(rule_project.graph_resource, data)
    code, payload = validate(rule_project, capsys)
    assert code == 1, payload
    finding = next(item for item in findings(payload) if item["code"] == expected)
    assert not rule_project.events()
    assert finding.get("source_location", {}).get("path") == str(rule_project.graph_resource), finding
    assert finding["source_location"]["line"] > 0
