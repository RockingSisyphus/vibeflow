import json
from types import SimpleNamespace

from vibeflow.core.rules import RuleCall, RuleContext, RuleDescriptor, RuleResult, RulesetDescriptor
from vibeflow.core.descriptors.contributions import ContributionBuilder, compose_contributions
from vibeflow.tooling.project.governance import execute_governance, governance_context, load_governance_config
from vibeflow.tooling.project.inventory import inventory_project
from vibeflow.tooling.project.resources import load_builtin_plugins
from vibeflow.targets.shared.rule_support.governance import governance_handlers


def workspace(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    return SimpleNamespace(root=tmp_path, roots=(SimpleNamespace(id="app", path=root,
        project_target="python", architecture_documents=()),))


def test_governance_defaults_override_and_explicit_empty_are_independent(tmp_path):
    project = workspace(tmp_path)
    dump = tmp_path / "dump"
    dump.mkdir()
    inventory = inventory_project(project)
    catalogs = load_builtin_plugins("project").catalogs
    config = load_governance_config(tmp_path, "project")
    results = execute_governance(config, governance_context(inventory), catalogs=catalogs, handlers=governance_handlers())
    assert results[0].status == "FAIL"
    assert [finding.rule_id for result in results[0].results.values() for finding in result.findings] == ["PROJECT.DIRECTORY.UNDECLARED"]
    (tmp_path / "project_rules.jsonc").write_text(json.dumps({"rule_params": {
        "vibeflow.project.layout": {"directories": [{"path": "dump", "purpose": "user requested exports"}]}}}))
    configured = load_governance_config(tmp_path, "project")
    assert execute_governance(configured, governance_context(inventory), catalogs=catalogs,
                              handlers=governance_handlers())[0].status == "PASS"
    (project.roots[0].path / "root_rules.jsonc").write_text('{"rulesets":[]}')
    assert not load_governance_config(project.roots[0].path, "root").selections
    assert load_governance_config(tmp_path, "project").selections == ("vibeflow.project.default",)


def test_root_facts_do_not_expose_other_roots_or_project_facts(tmp_path):
    project = workspace(tmp_path)
    context = governance_context(inventory_project(project), root=project.roots[0])
    assert tuple(context.facts) == ("root",)
    assert "roots" not in context.facts["root"]
    assert context.scope["level"] == "root"


def test_nested_root_container_does_not_hide_undeclared_sibling_directory(tmp_path):
    from vibeflow.targets.shared.rule_support.governance import project_layout
    root = tmp_path / "apps" / "desktop"
    root.mkdir(parents=True)
    (root.parent / "dump").mkdir()
    project = SimpleNamespace(root=tmp_path, roots=(SimpleNamespace(id="desktop", path=root,
        project_target="python", architecture_documents=()),))
    context = governance_context(inventory_project(project))
    result = project_layout(context, {}, {"directories": []})
    assert len(result.findings) == 1
    assert result.findings[0].source_location["path"].endswith("apps/dump")
    assert not project_layout(context, {}, {"directories": [
        {"path": "apps/dump", "purpose": "author-requested exports"}]}).findings


def test_lower_level_selection_cannot_invoke_project_rule_with_project_facts(tmp_path):
    config_path = tmp_path / "root_rules.jsonc"
    config_path.write_text('{"rulesets":["malicious"]}')
    builder = ContributionBuilder("checks")
    builder.add(RuleDescriptor("project_only", level="project"))
    builder.add(RulesetDescriptor("malicious", calls=(RuleCall("read", rule_id="project_only"),)))
    catalogs = compose_contributions((builder.finish(),))
    executed = []
    context = RuleContext(facts={"root": {}}, subject={"kind": "root", "id": "app"}, scope={"level": "root"})
    result = execute_governance(load_governance_config(tmp_path, "root"), context, catalogs=catalogs,
        handlers={"project_only": lambda *_: executed.append(True) or RuleResult()})[0]
    assert result.status == "ERROR"
    assert not executed
    assert result.results["read"].findings[0].rule_id == "RULE.LEVEL.MISMATCH"
