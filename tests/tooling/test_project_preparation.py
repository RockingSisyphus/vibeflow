import json
import pytest

from vibeflow.tooling.project.preparation import ProjectPreparation
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def project(tmp_path, root_ids):
    (tmp_path / "nodes").mkdir()
    (tmp_path / "nodes" / "shared.py").write_text('''from vibeflow.targets.python.sdk import node
@node(id="shared.step", node_type="vibeflow.node", contract={})
class Step:
    def run_pure(self, inputs, params): return {}
''')
    config = tmp_path / "vibeflow_config.jsonc"
    config.write_text(json.dumps({"purpose": "Shared resource regression", "roots": [
        {"id": identifier, "path": identifier, "purpose": identifier + " application"} for identifier in root_ids]}))
    for identifier in root_ids:
        root = tmp_path / identifier
        (root / "configs").mkdir(parents=True)
        (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
        (root / "configs" / "workflow.jsonc").write_text(json.dumps({"pipeline": {"nodes": [{
            "id": "step", "definition_id": "shared.step", "display_name": "Step", "description": "Execute shared step"}]}}))
    return load_workspace_config(config)


def test_shared_usage_counts_distinct_roots_and_writes_project_architecture(tmp_path):
    workspace = project(tmp_path, ["desktop", "backend"])
    preparation = ProjectPreparation(workspace)
    workflow = workspace.roots[0].path / "configs" / "workflow.jsonc"
    prepared = preparation.workflow_resources(workflow)
    report = preparation.review(write_architecture=True)
    assert preparation.workflow_resources(workflow).catalogs is prepared.catalogs
    assert not report.findings
    row = next(item for item in report.resources if item["id"] == "shared.step")
    assert row["used_by_roots"] == ["backend", "desktop"]
    document = json.loads("\n".join(report.architecture_path.read_text().splitlines()[2:]))
    assert document["purpose"] == "Shared resource regression"
    assert document["roots"][0]["purpose"] == "desktop application"
    assert document["inventory_complete"]
    assert row["used_by_workflows"] == [
        {"path":"desktop/configs/workflow.jsonc", "root":"desktop", "statuses":["implemented"], "relation":"declaration"},
        {"path":"backend/configs/workflow.jsonc", "root":"backend", "statuses":["implemented"], "relation":"declaration"}]


def test_two_workflows_in_one_root_do_not_qualify_as_project_shared(tmp_path):
    workspace = project(tmp_path, ["desktop"])
    directory = workspace.roots[0].path / "configs"
    (directory / "other.jsonc").write_text((directory / "workflow.jsonc").read_text())
    report = ProjectPreparation(workspace).review()
    assert [item.rule_id for item in report.findings] == ["PROJECT.RESOURCE.NOT_SHARED"]


def test_incomplete_inventory_does_not_report_false_resource_usage(tmp_path):
    workspace = project(tmp_path, ["desktop", "backend"])
    (workspace.roots[1].path / "configs" / "workflow.jsonc").write_text('{"pipeline":')
    report = ProjectPreparation(workspace).review()
    assert not report.inventory.complete
    assert "PROJECT.USAGE.INCOMPLETE" in {item.rule_id for item in report.findings}
    assert "PROJECT.RESOURCE.NOT_SHARED" not in {item.rule_id for item in report.findings}


def test_architecture_tracks_planned_real_references_and_survives_project_move(tmp_path):
    import shutil
    source = tmp_path / "source"
    source.mkdir()
    workspace = project(source, ["desktop", "backend"])
    shared = source / "nodes/shared.py"
    shared.write_text(shared.read_text().replace('contract={}', 'flow_kind="terminal", contract={}'))
    path = workspace.roots[0].path / "configs/planned.jsonc"
    path.write_text(json.dumps({"rulesets":[], "pipeline":{"nodes":[
        {"id":"future", "definition_id":"shared.step", "display_name":"Future", "description":"Planned real declaration",
         "status":"planned", "flow_kind":"terminal", "requires":[], "provides":[]},
        {"id":"missing", "definition_id":"not.implemented", "display_name":"Missing", "description":"Placeholder only",
         "status":"planned", "flow_kind":"terminal", "requires":[], "provides":[]} ]}}))
    report = ProjectPreparation(workspace).review(write_architecture=True)
    assert report.inventory.complete, report.inventory.issues
    resource = next(item for item in report.resources if item["id"] == "shared.step")
    assert {item["path"] for item in resource["used_by_workflows"]} == {
        "desktop/configs/workflow.jsonc", "desktop/configs/planned.jsonc", "backend/configs/workflow.jsonc"}
    assert next(item for item in resource["used_by_workflows"] if "planned" in item["path"])["statuses"] == ["planned"]
    assert not any(item["id"] == "not.implemented" for item in report.resources)
    original = report.architecture_path.read_text()
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    build_python_aot(PythonBuildRequest(workspace,workspace.roots[0].path/"configs/workflow.jsonc",tmp_path/"bundle",preview_root=tmp_path/"preview"))
    assert report.architecture_path.read_text() == original
    shutil.move(source, tmp_path / "moved")
    document = json.loads("\n".join((tmp_path/"moved/PROJECT_ARCHITECTURE.jsonc").read_text().splitlines()[2:]))
    row = next(item for item in document["resources"] if item["id"] == "shared.step")
    assert (tmp_path/"moved"/row["path"]).is_file()
    assert all((tmp_path/"moved"/item["path"]).is_file() for item in row["used_by_workflows"])


def test_preview_cli_exports_root_workflow_and_registered_document_index(tmp_path):
    from vibeflow.tooling.presentation.preview.cli import main
    workspace=project(tmp_path,["desktop","backend"])
    (tmp_path/"nodes/shared.py").write_text((tmp_path/"nodes/shared.py").read_text().replace('contract={}', 'flow_kind="terminal",contract={}'))
    for owner in workspace.roots:
        config=owner.path/"configs/workflow.jsonc"
        value=json.loads(config.read_text());value["description"]="Workflow for "+owner.id
        value["pipeline"].update(entries={"main":{"start":"step"}},default_entry="main")
        config.write_text(json.dumps(value))
        owner.config_path.write_text(json.dumps({"project_target":"python","architecture":{"documents":[
            {"workflow":"configs/workflow.jsonc","document":"docs/custom-main.jsonc"}]}}))
    assert main(["--workspace",str(workspace.path)])==0
    document=json.loads("\n".join((tmp_path/"PROJECT_ARCHITECTURE.jsonc").read_text().splitlines()[2:]))
    assert document["format"]=="vibeflow.project-architecture.v2"
    assert {row["path"] for row in document["directories"] if row["role"]=="root"}=={"desktop","backend"}
    for owner in document["roots"]:
        row=owner["workflows"][0]
        assert row["description"]=="Workflow for "+owner["id"]
        assert row["entries"]=={"main":{"start":"step"}} and row["default_entry"]=="main"
        assert row["architecture"]==owner["id"]+"/docs/custom-main.jsonc"
        assert row["architecture_exists"] is False
        assert not (tmp_path/row["architecture"]).exists()
    script=(tmp_path/"vibeflow-preview/project.js").read_text()
    payload=json.loads(script[len("VibeFlowPreview.project("):-3])
    assert payload["architecture"]==document


def test_project_custom_rule_is_loaded_atomically_without_activating_business_plugin(tmp_path):
    workspace = project(tmp_path, ["desktop"])
    package = tmp_path / "plugins" / "governance"
    package.mkdir(parents=True)
    (package / "plugin.py").write_text('''from vibeflow.targets.python.sdk import Plugin, rule
from vibeflow.core.rules import RuleResult
@rule(id="custom.project", level="project")
def check(context, inputs, params):
    assert "project" in context.facts and "root" not in context.facts
    return RuleResult()
plugin=Plugin(id="governance", resources=[check])
''')
    (tmp_path / "project_rules.jsonc").write_text(json.dumps({
        "plugins": [{"source": {"kind": "file", "ref": "plugins/governance/plugin.py"}}],
        "rulesets": [{"rule_id": "custom.project"}]}))
    preparation = ProjectPreparation(workspace)
    report = preparation.review()
    assert not report.findings
    assert report.results[0].executed == ("rule",)
    assert not next(iter(preparation.workflows.values())).records


def test_quality_command_uses_shared_preparation_and_writes_complete_project_document(tmp_path, capsys):
    from tests.tooling.test_resource_preparation import project
    from vibeflow.tooling.application.cli import main
    workspace, workflow, root = project(tmp_path)
    code = main(["quality-check", "--workspace", str(workspace.path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0, payload
    assert payload["status"] in {"PASS", "CONCERNS"}
    assert [item["config"] for item in payload["reports"]] == [str(workflow)]
    assert (tmp_path / "PROJECT_ARCHITECTURE.jsonc").is_file()
    assert not (tmp_path / "vibeflow-preview").exists()
    review = ProjectPreparation(workspace).review()
    package = next(item for item in review.resources if item["kind"] == "plugin_declaration")
    assert package["used_by_workflows"] == [{"path":"app/configs/workflow.jsonc", "root":"app",
        "statuses":["implemented"], "relation":"selection"}]
    assert not any(item["owner"]["kind"] == "plugin" for item in review.resources)


def test_root_quality_rules_receive_all_root_source_facts(tmp_path):
    from tests.tooling.test_resource_preparation import project
    workspace, workflow, root = project(tmp_path)
    (root / "support.py").write_text("def broken(:\n")
    result = ProjectPreparation(workspace, root=workspace.roots[0], workflow=workflow).review()
    assert any(item.rule_id.startswith("QUALITY.SYNTAX.") for item in result.findings)


def test_build_does_not_inspect_unselected_workflows_in_its_root(tmp_path):
    from tests.tooling.test_resource_preparation import project
    from vibeflow.tooling.application.python.project.core import build_workspace_environment
    workspace, workflow, root = project(tmp_path)
    (root / "configs" / "broken.jsonc").write_text("{broken")
    environment = build_workspace_environment(workspace, workflow)
    assert not any(item.rule_id == "CONFIG.JSON.PARSE" for item in environment.findings)
    full = ProjectPreparation(workspace).review()
    assert not full.inventory.complete


def test_unused_shared_resources_are_checked_even_without_workflows(tmp_path):
    workspace = project(tmp_path, ["desktop"])
    (workspace.roots[0].path / "configs/workflow.jsonc").unlink()
    (tmp_path / "plugins/unused").mkdir(parents=True)
    result = ProjectPreparation(workspace).review()
    underused = {item.details["resource_id"] for item in result.findings
                 if item.rule_id == "PROJECT.RESOURCE.NOT_SHARED"}
    assert underused == {"shared.step", "unused"}


def test_declaration_discovery_is_once_per_operation_and_refreshes_next_command(tmp_path, monkeypatch):
    from vibeflow.targets.python.sdk import discovery
    workspace = project(tmp_path, ["desktop", "backend"])
    original, seen = discovery.discover_resources, []
    def collect(directory, **kwargs):
        seen.append(directory)
        return original(directory, **kwargs)
    monkeypatch.setattr(discovery, "discover_resources", collect)
    first = ProjectPreparation(workspace)
    first.review()
    assert seen.count(tmp_path) == 1
    path = tmp_path / "nodes/shared.py"
    path.write_text(path.read_text().replace('contract={}', 'contract={}, description="Edited declaration"'))
    second = ProjectPreparation(workspace)
    second.review()
    assert seen.count(tmp_path) == 2
    resource = next(iter(second.workflows.values())).catalogs.nodes.require("shared.step")
    assert resource.description == "Edited declaration"


def test_delayed_project_rule_resolves_relative_support_inside_its_plugin(tmp_path):
    workspace = project(tmp_path, ["desktop"])
    package = tmp_path / "plugins/governance"
    package.mkdir(parents=True)
    (package / "plugin.py").write_text('''from vibeflow.targets.python.sdk import Plugin,rule,SourceLocator
check=rule(id="custom.project",level="project",source=SourceLocator("file","check.py","check"))
plugin=Plugin(id="governance",resources=[check])
''')
    (package / "helpers.py").write_text('from vibeflow.core.rules import RuleResult\ndef passed(): return RuleResult()\n')
    (package / "check.py").write_text('from .helpers import passed\ndef check(context,inputs,params):\n    assert "project" in context.facts and "root" not in context.facts\n    return passed()\n')
    (tmp_path / "project_rules.jsonc").write_text(json.dumps({"plugins":[{"source":{"kind":"file","ref":"plugins/governance/plugin.py"}}],
        "rulesets":[{"rule_id":"custom.project"}]}))
    report = ProjectPreparation(workspace).review()
    assert not report.findings, [item.to_dict() for item in report.findings]
    assert report.results[0].status == "PASS"


def test_javascript_governance_plugin_reads_project_and_root_views_without_business_activation(tmp_path):
    import os
    from pathlib import Path
    workspace = project(tmp_path, ["desktop"])
    (tmp_path / "node_modules").symlink_to(Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) / "node_modules", target_is_directory=True)
    package = tmp_path / "plugins/governance"
    package.mkdir(parents=True)
    (package / "plugin.ts").write_text('''import {definePlugin,defineRule} from "@vibeflow/plugin";
const project=defineRule({id:"custom.project",level:"project",check(context){
 if(!context.facts.project || context.facts.root || context.facts.project.roots.length!==1) throw Error("wrong project view");
 return {findings:[]};}});
const root=defineRule({id:"custom.root",level:"root",check(context){
 if(!context.facts.root || context.facts.project || context.facts.root.id!=="desktop") throw Error("wrong root view");
 if(!context.facts.root.source_quality.files) throw Error("missing source facts");
 return {findings:[]};}});
export const plugin=definePlugin({id:"governance",resources:[project,root]});
''')
    selection = {"scope":"project", "language":"javascript", "source":{"kind":"file","ref":"plugins/governance/plugin.ts"}}
    (tmp_path / "project_rules.jsonc").write_text(json.dumps({"plugins":[selection], "rulesets":[{"rule_id":"custom.project"}]}))
    (workspace.roots[0].path / "root_rules.jsonc").write_text(json.dumps({"plugins":[selection], "rulesets":[{"rule_id":"custom.root"}]}))
    prepared = ProjectPreparation(workspace)
    report = prepared.review()
    assert not report.findings, [item.to_dict() for item in report.findings]
    assert all(item.status == "PASS" for item in report.results)
    assert not next(iter(prepared.workflows.values())).records


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("registered", [False, True])
def test_root_source_rule_receives_current_resource_ownership(tmp_path, target, registered):
    """Turning off Node rules never removes facts from the selected root Rule."""
    from tests.fixtures.support.projects import register_root
    import os
    from pathlib import Path
    root = tmp_path / "app"
    register_root(root, target)
    (root / "root_rules.jsonc").write_text(json.dumps({"rulesets":["vibeflow.root.default"],
        "rule_params":{"vibeflow.root.structure":{"enabled":True}}}))
    (root / "nodes").mkdir()
    if target == "python":
        support = ',implementation_files=["helper.py"]' if registered else ''
        (root / "nodes/helper.py").write_text('def value():\n    return 7\n')
        (root / "nodes/steps.py").write_text('from vibeflow.targets.python.sdk import node\nfrom .helper import value\n'
            f'@node(id="leaf",node_type="vibeflow.node",flow_kind="terminal",contract={{}},rulesets=[]{support})\n'
            'class Leaf:\n    def run_pure(self,inputs,params):\n        value()\n        return {}\n')
    else:
        (root / "node_modules").symlink_to(Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) / "node_modules", target_is_directory=True)
        (root / "package.json").write_text('{"type":"module"}')
        support = ',implementation_files:["helper.ts"]' if registered else ''
        (root / "nodes/helper.ts").write_text('export function value(){return 7;}\n')
        (root / "nodes/steps.ts").write_text('import {defineNode} from "@vibeflow/plugin";\nimport {value} from "./helper.ts";\n'
            'export const leaf=defineNode({id:"leaf",node_type:"vibeflow.node",flow_kind:"terminal",contract:{},rulesets:[]'
            +support+',run(){value();return {}}});\n')
    (root / "workflow.jsonc").write_text(json.dumps({"rulesets":[],"pipeline":{"nodes":[{
        "id":"leaf","definition_id":"leaf","display_name":"Leaf","description":"Root ownership scope"}]}}))
    workspace = load_workspace_config(root.parent / "vibeflow_config.jsonc")
    report = ProjectPreparation(workspace).review()
    findings = [item for item in report.findings if item.rule_id=="RESOURCE.REFERENCE.UNDECLARED"]
    assert bool(findings) is not registered
    if findings:
        assert "leaf" in findings[0].message


def test_governance_only_exemption_does_not_hide_business_adoption(tmp_path):
    workspace=project(tmp_path,['desktop','backend'])
    package=tmp_path/'plugins/governance';package.mkdir(parents=True)
    (package/'plugin.py').write_text('from vibeflow.targets.python.sdk import Plugin,rule\n@rule(id="governance.root",level="root")\ndef check(context,inputs,params):return {"findings":[]}\nplugin=Plugin(id="governance",resources=[check])\n')
    selection={'scope':'project','source':{'kind':'file','ref':'plugins/governance/plugin.py'}}
    (workspace.roots[0].path/'root_rules.jsonc').write_text(json.dumps({'plugins':[selection],'rulesets':[{'rule_id':'governance.root'}]}))
    assert not ProjectPreparation(workspace).review().findings
    workflow=workspace.roots[0].path/'configs/workflow.jsonc'
    data=json.loads(workflow.read_text());data['plugins']=[selection];workflow.write_text(json.dumps(data))
    findings=ProjectPreparation(workspace).review().findings
    assert any(item.rule_id=='PROJECT.RESOURCE.NOT_SHARED' and item.details['resource_id']=='governance' for item in findings)
