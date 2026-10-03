"""Formal runtime reviews use selected Rules, while lifecycle plugins stay separate."""

from tests.fixtures.support.strict_support import *
from tests.fixtures.support.declarations import write_node_manifests
from vibeflow.tooling.application.python.cli.config import validate_config_path
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
from vibeflow.tooling.project.workspace_loader import load_project_workspace


def _rule_project(root, *, handler_source=None, outputs=None):
    write_node_manifests(root, [
        ("test.start", "StartNode", {}, {}),
        ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
        ("test.in_end", "InEndNode", {}, {}),
    ])
    manifests = root / "manifests"
    for role in ("rules", "rulesets", "bundles"):
        (manifests / role).mkdir()
    if handler_source is not None:
        (root / "review_rule.py").write_text(handler_source)
        (manifests / "rules/check.jsonc").write_text(json.dumps({
            "kind": "rule", "id": "project.review", "outputs": outputs or {},
            "params_schema": {"severity": {"type": "string", "enum": ["error", "warning"]}},
            "params_defaults": {"severity": "warning"},
            "implementations": [{"language": "python",
                "source": {"kind": "file", "ref": "review_rule.py", "export": "check"}}],
        }))
    _refresh_bundle(root)
    (root / "vibeflow_project.jsonc").write_text(json.dumps({
        "project_target": "python", "descriptors": {"bundles": ["manifests/bundles"]}}))
    config = root / "workflow.jsonc"
    config.write_text(json.dumps({"pipeline": _seed_only_pipeline()}))
    return config


def _select_node_rules(root, *, params=None, relations=(), extra_calls=()):
    data = {"kind": "ruleset", "id": "project.node_review", "calls": [
        {"id": "base", "ruleset_id": "vibeflow.process"}, *extra_calls],
        "relations": list(relations), "entrypoints": {
            phase: ["base", *[call["id"] for call in extra_calls]]
            for phase in ("static", "run")}}
    data["entrypoints"]["import"] = ["base"]
    (root / "manifests/rulesets/node.jsonc").write_text(json.dumps(data))
    manifest = root / "manifests/nodes/test-seed.jsonc"
    node = json.loads(manifest.read_text())
    node["rulesets"] = ["project.node_review"]
    manifest.write_text(json.dumps(node))
    _refresh_bundle(root)


def _refresh_bundle(root):
    manifests = root / "manifests"
    bundle = {"kind": "bundle", "id": "project.review_bundle", "resources": {
        kind: ["../" + kind + "/" + path.name for path in sorted((manifests / kind).glob("*.jsonc"))]
        for kind in ("nodes", "rules", "rulesets")}}
    (manifests / "bundles/review.jsonc").write_text(json.dumps(bundle))


_DIAGNOSTIC_RULE = '''from vibeflow.core import HealthFinding
from vibeflow.core.rules import RuleResult

def check(context, inputs, params):
    kind = context.subject["kind"]
    object_id = str(context.subject.get("call_id", context.subject.get("id", "seed")))
    return RuleResult(findings=(HealthFinding(rule_id="DOMAIN." + kind.upper(),
        severity=params["severity"], object_type=kind, object_id=object_id,
        source_location={"path": "review_rule.py", "line": 7},
        message="A selected domain rule checked this object."),))
'''


def test_ruleset_tightens_source_limit_and_formal_run_consumes_effective_params(tmp_path):
    config = _rule_project(tmp_path)
    _select_node_rules(tmp_path, relations=[{
        "source": "$self", "target": "base/maintainability", "kind": "overrides",
        "params": {"policy": {"node_source": {"max_lines": 1}}},
    }])
    with pytest.raises(CheckedRunError) as refused:
        run_workspace_checked(config, workspace=load_project_workspace(config), run_root=tmp_path / "runs", run_id="limit")
    finding = next(item for item in refused.value.result.health.errors if item.code == "NODE.PURITY.SOURCE_TOO_LARGE")
    assert finding.definition_id == "vibeflow.maintainability"
    executions = refused.value.result.health.info["rule_executions"]
    effective = [call for execution in executions for call in execution["plan"]["calls"]
                 if call["rule_id"] == "vibeflow.maintainability"]
    assert any(call["params"]["policy"].get("node_source", {}).get("max_lines") == 1 for call in effective)


@pytest.mark.parametrize("source,outputs,code", [
    ("def check(context, inputs, params):\n    raise RuntimeError('rule boom')\n", {}, "RULE.EXECUTION"),
    ("from vibeflow.core.rules import RuleResult\ndef check(context, inputs, params):\n    return RuleResult()\n",
        {"required_facts": "project.facts.v1"}, "RULE.EXECUTION"),
])
def test_rule_exceptions_and_missing_records_refuse_formal_run(tmp_path, source, outputs, code):
    config = _rule_project(tmp_path, handler_source=source, outputs=outputs)
    _select_node_rules(tmp_path, extra_calls=[{"id": "domain", "rule_id": "project.review"}])
    with pytest.raises(CheckedRunError) as refused:
        run_workspace_checked(config, workspace=load_project_workspace(config), run_root=tmp_path / "runs", run_id="unavailable")
    assert any(item.code == code for item in refused.value.result.health.errors)
    assert refused.value.result.context is None
    assert not (refused.value.result.run_dir / "output_summary.json").exists()


def test_local_rule_override_changes_severity_without_a_second_policy_switch(tmp_path):
    config = _rule_project(tmp_path, handler_source=_DIAGNOSTIC_RULE)
    _select_node_rules(tmp_path, extra_calls=[{"id": "domain", "rule_id": "project.review", "params": {"severity": "error"}}])
    report = validate_config_path(config)
    assert any(item.code == "DOMAIN.NODE" for item in report.errors), [(item.code, item.message) for item in report.errors]
    manifest = tmp_path / "manifests/rulesets/node.jsonc"
    data = json.loads(manifest.read_text())
    data["relations"] = [{"source": "$self", "target": "domain", "kind": "overrides", "params": {"severity": "warning"}}]
    manifest.write_text(json.dumps(data))
    result = run_workspace_checked(config, workspace=load_project_workspace(config), run_root=tmp_path / "runs", run_id="overridden")
    assert result.context.get("value.in")["value"] == 1
    finding = next(item for item in result.health.warnings if item.code == "DOMAIN.NODE")
    assert finding.definition_id == "project.review"
    assert finding.source_location["line"] == 7


def test_rule_bundle_contributes_node_and_workflow_findings_to_normal_run(tmp_path):
    config = _rule_project(tmp_path, handler_source=_DIAGNOSTIC_RULE)
    _select_node_rules(tmp_path, extra_calls=[{"id": "domain", "rule_id": "project.review"}])
    (tmp_path / "manifests/rulesets/workflow.jsonc").write_text(json.dumps({
        "kind": "ruleset", "id": "project.workflow_review", "calls": [
            {"id": "base", "ruleset_id": "vibeflow.workflow"}, {"id": "domain", "rule_id": "project.review"}],
        "entrypoints": {"static": ["base", "domain"], "run": ["base", "domain"]}}))
    _refresh_bundle(tmp_path)
    data = json.loads(config.read_text())
    data["rulesets"] = ["project.workflow_review"]
    config.write_text(json.dumps(data))
    result = run_workspace_checked(config, workspace=load_project_workspace(config), run_root=tmp_path / "runs", run_id="findings")
    findings = {item.code: item for item in result.health.warnings if item.definition_id == "project.review"}
    assert set(findings) == {"DOMAIN.NODE", "DOMAIN.WORKFLOW"}
    assert all(item.source_location["path"] == "review_rule.py" for item in findings.values())
    assert result.context.get("value.in")["value"] == 1


def test_missing_lifecycle_plugin_refuses_formal_validation(tmp_path, capsys):
    config = _rule_project(tmp_path)
    data = json.loads(config.read_text())
    data["plugins"] = [{"module": str(tmp_path / "missing.py"), "type": "runtime"}]
    config.write_text(json.dumps(data))
    assert cli_main(["validate", "--config", str(config), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert any(item["code"] == "PLUGIN.LOAD" for item in payload["errors"])
