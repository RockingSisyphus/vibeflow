"""Policies are ordinary Rules; successful loading does not enforce policy."""
import json
import shutil
import subprocess
import sys

import pytest

from tests.tooling.test_project_dependency_scope import project, node, workflow, write
from vibeflow.tooling.project.preparation import ProjectPreparation
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def codes(workspace):
    return {item.rule_id for item in ProjectPreparation(workspace).review().findings}


@pytest.mark.parametrize("location", ["backend", "base_lib", "app/plugins/private"])
@pytest.mark.parametrize("policy", ["default", "allow", "disabled", "replacement"])
def test_nodeset_policies_can_be_replaced(tmp_path, location, policy):
    workspace = project(tmp_path, "python")
    config = tmp_path / "app/main.jsonc"
    write(tmp_path / "app/nodes/step.py", node("python"))
    workflow(config)
    declaration = json.loads(config.read_text())
    imported = tmp_path / location / "group.jsonc"
    write(imported, {"type_key":"group", "display_name":"Group", "description":"Reusable computation",
        "requires":[], "provides":[], "rulesets":[],
        "pipeline":{"nodes":[{"id":"step", "definition_id":"step", "display_name":"Step", "description":"Return value"}]}})
    declaration["nodeset_imports"] = [str(imported)]
    write(config, declaration)
    if policy == "allow":
        write(tmp_path / "app/root_rules.jsonc", {"rule_params":{
            "vibeflow.root.resources":{"allow_cross_root_imports":True}}})
    elif policy == "disabled":
        write(tmp_path / "app/root_rules.jsonc", {"rulesets":[]})
    elif policy == "replacement":
        # The replacement's own Plugin violates the default package location.
        # It must still load in time to replace that policy.
        write(tmp_path / "app/custom.py", 'from vibeflow.targets.python.sdk import Plugin,rule\n'
              'from vibeflow.core.rules import RuleResult\n'
              '@rule(id="custom.boundary",level="root")\n'
              'def check(context,inputs,params):\n'
              '    assert context.facts["root"]["nodeset_imports"]\n'
              '    return RuleResult()\n'
              'plugin=Plugin(id="custom",resources=[check])\n')
        write(tmp_path / "app/root_rules.jsonc", {"plugins":[{"source":{"kind":"file","ref":"custom.py"}}],
            "rulesets":[{"rule_id":"custom.boundary"}]})
    preparation = ProjectPreparation(workspace)
    review = preparation.review()
    assert not review.inventory.issues
    assert config in preparation.workflows, [item.to_dict() for item in review.findings]
    actual = {item.rule_id for item in review.findings}
    expected = ("WORKSPACE.NODESET.PRIVATE" if location == "backend" else
                "WORKSPACE.NODESET.OUTSIDE_ROOT" if location == "base_lib" else "WORKSPACE.NODESET.PLUGIN_PRIVATE")
    assert (expected in actual) == (policy == "default" or policy == "allow" and location == "app/plugins/private"), actual
    assert not actual.intersection({"PROJECT.RESOURCE.PREPARATION", "RULE.EXECUTION.ERROR"}), actual


def test_cross_target_subgraph_runs_and_builds_when_rules_allow_it(tmp_path):
    source = tmp_path / "source"
    workspace = project(source, "python")
    write(source / "backend/vibeflow_project.jsonc", {"project_target":"javascript"})
    # The backend graph is declarative; its calls resolve in the consumer catalog.
    config = source / "app/main.jsonc"
    workflow(config)
    data = json.loads(config.read_text())
    group = {"type_key":"group", "display_name":"Group", "description":"Return an answer",
        "requires":[], "provides":[{"key":"answer","type":"answer","display_name":"Answer"}],
        "rulesets":[], "pipeline":data["pipeline"]}
    write(source / "backend/group.jsonc", group)
    data["nodeset_imports"] = ["../backend/group.jsonc"]
    data["pipeline"]["nodes"][0]["definition_id"] = "group"
    data["pipeline"]["nodes"] = [
        {"id":"start", "definition_id":"boundary", "display_name":"Start", "description":"Enter graph"},
        *data["pipeline"]["nodes"],
        {"id":"end", "definition_id":"boundary", "display_name":"End", "description":"Exit graph"}]
    data["pipeline"]["edges"] = [["start","call"], ["call","end"]]
    write(config, data)
    write(source / "app/nodes/step.py", node("python") + '\n'
        '@node(id="boundary",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={})\n'
        'class Boundary:\n    def run_pure(self,inputs,params):return {}\n')
    write(source / "project_rules.jsonc", {"rulesets":[]})
    write(source / "backend/root_rules.jsonc", {"rulesets":[]})
    workspace = load_workspace_config(workspace.path)
    assert "WORKSPACE.NODESET.TARGET_MISMATCH" in codes(workspace)
    write(source / "app/root_rules.jsonc", {"rulesets":[]})
    from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
    from vibeflow.tooling.application.python.build import build_python_aot, PythonBuildRequest
    assert run_workspace_checked(config, workspace=workspace, run_root=tmp_path/"runs",
        preview_root=tmp_path/"preview").public_outputs["answer"] == 731
    built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path/"bundle", preview_root=tmp_path/"preview"))
    shutil.rmtree(source)
    result = subprocess.run([sys.executable, "-I", "-c",
        'import sys;sys.path.insert(0,sys.argv[1]);from vibeflow.tooling.application.python.bundle import PythonBundle;'
        'assert PythonBundle(sys.argv[2]).run(run_root=sys.argv[3]).public_outputs["answer"]==731',
        str(built.out_dir/"_framework"), str(built.out_dir), str(tmp_path/"bundle-runs")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_plugin_nodes_can_be_loaded_and_built_with_replaced_policy(tmp_path, target):
    source = tmp_path / "source"
    workspace = project(source, target)
    config = source / "app/main.jsonc"
    workflow(config)
    suffix = "py" if target == "python" else "ts"
    body = node(target)
    body += ('\nfrom vibeflow.targets.python.sdk import Plugin\nplugin=Plugin(id="business",resources=[Step])\n'
             if target == "python" else '\nimport {definePlugin,defineDataSchema} from "@vibeflow/plugin";\n'
             'export const plugin=definePlugin({id:"business",resources:[step,defineDataSchema({type_key:"answer",schema:{type:"number"}})]});\n')
    write(source / f"app/plugins/business/plugin.{suffix}", body)
    data = json.loads(config.read_text())
    data["plugins"] = [{"source":{"kind":"file","ref":f"plugins/business/plugin.{suffix}"}}]
    write(config, data)
    assert "PLUGIN.PACKAGE.BUSINESS_NODE" in codes(workspace)
    write(source / "app/root_rules.jsonc", {"rulesets":[]})
    assert "PLUGIN.PACKAGE.BUSINESS_NODE" not in codes(workspace)
    if target == "python":
        from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
        from vibeflow.tooling.application.python.build import build_python_aot, PythonBuildRequest
        assert run_workspace_checked(config, workspace=workspace, run_root=tmp_path/"runs",
            preview_root=tmp_path/"preview").public_outputs["answer"] == 731
        built = build_python_aot(PythonBuildRequest(workspace,config,tmp_path/"bundle",preview_root=tmp_path/"preview"))
        from vibeflow.tooling.application.python.bundle import PythonBundle
        assert PythonBundle(built.out_dir).run(run_root=tmp_path/"aot-runs").public_outputs["answer"] == 731
    else:
        from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
        built = build_project_aot(ProjectBuildRequest(workspace.path,config,tmp_path/"bundle",target="node",
            profile="single-esm",preview_root=tmp_path/"preview"))
        result = subprocess.run(["node","--input-type=module","-e",
            'const m=await import(process.argv[1]);console.log(JSON.stringify(m.runWorkflow({})));',built.entry.as_uri()], capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
        assert "731" in result.stdout


def test_include_dependency_uses_root_rules(tmp_path):
    source = tmp_path / "source"
    workspace = project(source, "python")
    config = source / "app/main.jsonc"
    workflow(config)
    write(source / "app/nodes/step.py", node("python"))
    write(source / "backend/assets/value.txt", "731")
    from vibeflow.tooling.application.python.build import build_python_aot, PythonBuildRequest
    request = PythonBuildRequest(workspace,config,tmp_path/"bundle",include=("../backend/assets",),preview_root=tmp_path/"preview")
    with pytest.raises(ValueError, match="ROOT.RESOURCE.PRIVATE_IMPORT"):
        build_python_aot(request)
    write(source / "app/root_rules.jsonc", {"rule_params":{"vibeflow.root.resources":{"allow_cross_root_imports":True}}})
    built = build_python_aot(request)
    assert (built.out_dir/"shared/backend/assets/value.txt").read_text() == "731"


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_declaration_placement_is_a_rule(tmp_path, target):
    workspace = project(tmp_path, target)
    suffix = "py" if target == "python" else "ts"
    write(tmp_path / f"app/base_lib/step.{suffix}", node(target))
    workflow(tmp_path / "app/main.jsonc")
    assert "ROOT.RESOURCE.LOCATION" in codes(workspace)
    write(tmp_path / "app/root_rules.jsonc", {"rulesets":[]})
    preparation = ProjectPreparation(workspace)
    assert "ROOT.RESOURCE.LOCATION" not in {item.rule_id for item in preparation.review().findings}
    assert preparation.workflows[tmp_path / "app/main.jsonc"].catalogs.nodes.require("step")


def test_root_named_project_does_not_inherit_project_package_policy(tmp_path):
    workspace = project(tmp_path, "python")
    data = json.loads(workspace.path.read_text())
    data["roots"][0]["id"] = "project"
    write(workspace.path, data)
    workspace = load_workspace_config(workspace.path)
    write(tmp_path / "app/custom.py", 'from vibeflow.targets.python.sdk import Plugin\nplugin=Plugin(id="custom")\n')
    workflow(tmp_path / "app/main.jsonc")
    write(tmp_path / "app/nodes/step.py", node("python"))
    data = json.loads((tmp_path / "app/main.jsonc").read_text())
    data["plugins"] = [{"source":{"kind":"file","ref":"custom.py"}}]
    write(tmp_path / "app/main.jsonc", data)
    assert "PLUGIN.PACKAGE.LOCATION" in codes(workspace)
    write(tmp_path / "app/root_rules.jsonc", {"rulesets":[]})
    assert "PLUGIN.PACKAGE.LOCATION" not in codes(workspace)



def test_explicit_import_base_does_not_override_resolved_ownership(tmp_path):
    workspace = project(tmp_path, "python")
    config = tmp_path / "app/main.jsonc"
    workflow(config)
    write(tmp_path / "app/nodes/step.py", node("python"))
    data = json.loads(config.read_text())
    write(tmp_path / "backend/group.jsonc", {"type_key":"group", "display_name":"Group",
        "description":"Resolved foreign declaration", "requires":[], "provides":[],
        "pipeline":data["pipeline"]})
    data["nodeset_imports"] = [{"root":"app", "path":"../backend/group.jsonc"}]
    write(config, data)
    preparation = ProjectPreparation(workspace)
    imported = preparation.workflow_resources(config).document.nodeset_imports[0]
    assert imported["root_id"] == imported["import_root"] == "backend"
    assert "WORKSPACE.NODESET.PRIVATE" in {item.rule_id for item in preparation.review().findings}
