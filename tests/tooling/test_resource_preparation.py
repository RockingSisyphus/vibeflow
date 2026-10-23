import json
import os
from pathlib import Path

import pytest

from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.resources import prepare_workflow_resources


def project(tmp_path, target="python"):
    root = tmp_path / "app"
    package = root / "plugins" / "layout"
    package.mkdir(parents=True)
    (root / "nodes").mkdir()
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": target}))
    config = tmp_path / "vibeflow_config.jsonc"
    config.write_text('{"roots":[{"id":"app","path":"app"}]}')
    (root / "configs").mkdir()
    workflow = root / "configs" / "workflow.jsonc"
    workflow.write_text(json.dumps({"plugins": [{"source": {"kind": "file", "ref": "plugins/layout/plugin.py"}}],
        "pipeline": {"nodes": [{"id": "first", "definition_id": "app.step",
                                 "display_name": "First step", "description": "Run the business step."}], "edges": []}}))
    (package / "plugin.py").write_text('''from vibeflow.targets.python.sdk import Plugin, node_type
shell = node_type(id="layout.step", rulesets=["vibeflow.process"], presentation={"shape":"hex","fill":"#f4e4c0"})
plugin = Plugin(id="layout", resources=[shell])
''')
    (root / "nodes" / "step.py").write_text('''from vibeflow.targets.python.sdk import node
@node(id="app.step", node_type="layout.step", flow_kind="terminal", contract={}, rulesets=[])
class Step:
    def run_pure(self, inputs, params):
        return {}
''')
    return load_workspace_config(config), workflow, root


def test_business_nodes_are_discovered_and_bound_separately_from_plugin_types(tmp_path):
    workspace, workflow, root = project(tmp_path)
    loaded = prepare_workflow_resources(workspace, workflow)
    node = loaded.catalogs.nodes.require("app.step")
    assert node.node_type == "layout.step"
    assert node.presentation["shape"] == "hex"
    assert node.rulesets == ()
    from vibeflow.tooling.presentation.node_presentation import resolve_presentation
    assert resolve_presentation(node).sources["shape"] == "node_type"
    assert node.declaration.presentation == {}
    assert loaded.catalogs.origins[("nodes", node.id)].owner.kind == "root"
    assert loaded.catalogs.origins[("node_types", "layout.step")].owner.path == str(root / "plugins" / "layout")
    assert loaded.resource_bindings[("node", node.id)]().run_pure({}, {}) == {}
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    from vibeflow.tooling.project.config_loader import load_workspace_config_document
    from vibeflow.tooling.project.graph_config import parse_graph_config
    from vibeflow.targets.python.runtime.engine import PipelineRuntime
    registry = declared_python_registry(workspace, workflow, prepared_resources=loaded)
    graph = parse_graph_config(load_workspace_config_document(workflow, workspace=workspace).data)
    runtime = PipelineRuntime(graph, registry=registry, run_dir=tmp_path / "execution")
    runtime.run()
    assert runtime.trace.step_count == 1


def test_python_aot_uses_prepared_nodes_and_rejects_old_artifact_format(tmp_path):
    workspace, workflow, root = project(tmp_path)
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.bundle import PythonBundle
    result = build_python_aot(PythonBuildRequest(workspace.path, workflow, tmp_path / "aot",
                                                preview_root=tmp_path / "preview"))
    metadata = json.loads(result.manifest.read_text())
    assert metadata["format"] == "vibeflow.aot-build.v5"
    assert metadata["abi_version"] == "vibeflow.workflow.v11"
    bundle = PythonBundle(result.out_dir)
    runtime = bundle.create_runtime(run_dir=tmp_path / "aot-run")
    runtime.run()
    assert runtime.trace.step_count == 1
    records = list((tmp_path / "preview" / "vibeflow-preview" / "snapshots").glob("*/record.json"))
    assert len(records) == 1
    assert json.loads(records[0].read_text())["version"] == 4
    metadata["format"] = "vibeflow.aot-build.v3"
    result.manifest.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="rebuild"):
        PythonBundle(result.out_dir)


def test_unused_node_does_not_implicitly_require_another_workflows_plugin(tmp_path):
    workspace, workflow, root = project(tmp_path)
    (root / "nodes" / "unused.py").write_text('''from vibeflow.targets.python.sdk import node
@node(id="app.other", node_type="other.plugin.type", contract={})
class Other:
    def run_pure(self, inputs, params):
        return {}
''')
    loaded = prepare_workflow_resources(workspace, workflow)
    assert loaded.catalogs.nodes.available() == ("app.step",)


def test_missing_plugin_diagnoses_type_without_deleting_business_code(tmp_path):
    workspace, workflow, root = project(tmp_path)
    data = json.loads(workflow.read_text())
    data["plugins"] = []
    workflow.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="missing NodeType"):
        prepare_workflow_resources(workspace, workflow)
    assert (root / "nodes" / "step.py").is_file()


def test_root_quality_diagnostic_blocks_validation_build_and_source_execution(tmp_path):
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path, run_workspace_checked
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.execution import CheckedRunError
    workspace, workflow, root = project(tmp_path)
    (root / "root_rules.jsonc").write_text('{"rulesets":[{"rule_id":"vibeflow.root.files"}]}')
    (root / "support.py").write_text("# large source\n" * 501)
    report = validate_workspace_config_path(workflow, workspace=workspace)
    assert any(item.code == "QUALITY.FILE.MAX_LINES" for item in report.errors)
    with pytest.raises(ValueError, match="QUALITY.FILE.MAX_LINES"):
        build_python_aot(PythonBuildRequest(workspace, workflow, tmp_path / "refused-bundle"))
    with pytest.raises(CheckedRunError) as error:
        run_workspace_checked(workflow, workspace=workspace, run_root=tmp_path / "runs")
    assert any(item.code == "QUALITY.FILE.MAX_LINES" for item in error.value.result.health.errors)
    assert not (tmp_path / "refused-bundle").exists()


def test_plugin_cannot_contribute_implementation_from_outside_its_package(tmp_path):
    workspace, workflow, root = project(tmp_path)
    (root / "outside.py").write_text('from vibeflow.targets.python.sdk import rule\n@rule(id="outside")\ndef check(*args): pass\n')
    (root / "plugins" / "layout" / "plugin.py").write_text('from outside import check\nfrom vibeflow.targets.python.sdk import Plugin\nplugin=Plugin(id="layout",resources=[check])\n')
    # Retain the type required by the workflow so governance can inspect it.
    plugin = root / "plugins/layout/plugin.py"
    plugin.write_text(plugin.read_text().replace('resources=[check]', 'resources=[check, shell]').replace(
        'plugin=Plugin', 'from vibeflow.targets.python.sdk import node_type\nshell=node_type(id="layout.step")\nplugin=Plugin'))
    from vibeflow.tooling.project.preparation import ProjectPreparation
    prepare_workflow_resources(workspace, workflow)
    assert any(item.rule_id == "PLUGIN.PACKAGE.OWNERSHIP" for item in ProjectPreparation(workspace).review().findings)


def test_javascript_discovers_nodes_separately_and_uses_type_presentation(tmp_path):
    workspace, workflow, root = project(tmp_path, "javascript")
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (root / "package.json").write_text('{"type":"module"}')
    (root / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    (root / "plugins" / "layout" / "plugin.py").unlink()
    (root / "nodes" / "step.py").unlink()
    (root / "plugins" / "layout" / "plugin.ts").write_text('''import {definePlugin,defineNodeType} from "@vibeflow/plugin";
const shell=defineNodeType({id:"layout.step",presentation:{shape:"hex",fill:"#f4e4c0"}});
export const plugin=definePlugin({id:"layout",resources:[shell]});
''')
    (root / "nodes" / "step.ts").write_text('''import {defineNode} from "@vibeflow/plugin";
export const step=defineNode({id:"app.step",node_type:"layout.step",flow_kind:"terminal",contract:{},
  run(inputs,params){return {};}});
''')
    data = json.loads(workflow.read_text())
    data["plugins"][0]["source"]["ref"] = "plugins/layout/plugin.ts"
    workflow.write_text(json.dumps(data))
    (root / "nodes/unselected.ts").write_text("throw new Error('plain implementation executed during discovery');")
    loaded = prepare_workflow_resources(workspace, workflow)
    node = loaded.catalogs.nodes.require("app.step")
    assert node.node_type == "layout.step"
    assert node.presentation["shape"] == "hex"
    assert node.implementations[0].source.export == "step.run"
    assert loaded.catalogs.origins[("nodes", node.id)].owner.kind == "root"
    from vibeflow.targets.javascript.frontend.facts import implementation_facts_from_catalog
    from vibeflow.core import compile_core, CoreCompileRequest, TargetFeatureSet
    from vibeflow.tooling.project.config_loader import load_workspace_config_document
    from vibeflow.tooling.project.graph_config import parse_graph_config
    facts = implementation_facts_from_catalog(loaded.catalogs.nodes, target="node")
    graph = parse_graph_config(load_workspace_config_document(workflow, workspace=workspace).data)
    compiled = compile_core(CoreCompileRequest(graph, implementation_facts=facts,
        target_features=TargetFeatureSet(target="javascript"))).compiled_graph
    assert compiled.order == ("first",)
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
    result = build_project_aot(ProjectBuildRequest(workspace.path, workflow, tmp_path / "aot-js",
        target="node", profile="esm-module", preview_root=tmp_path / "preview-js"))
    assert json.loads(result.manifest.read_text())["format"] == "vibeflow.aot-build.v5"
    import subprocess
    executed = subprocess.run(["node", "--input-type=module", "-e",
        "const m=await import(process.argv[1]); if('createWorkflowHost' in m)throw new Error('retired Host export'); m.runWorkflow({});",
        result.entry.as_uri()], check=False, capture_output=True, text=True)
    assert executed.returncode == 0, executed.stderr


def test_plugin_private_imports_cannot_borrow_business_code_even_without_rules(tmp_path):
    workspace, workflow, root = project(tmp_path)
    (root / "utility.py").write_text("color = '#123456'\n")
    plugin = root / "plugins/layout/plugin.py"
    plugin.write_text('from utility import color\n' + plugin.read_text())
    from vibeflow.tooling.project.preparation import ProjectPreparation
    prepare_workflow_resources(workspace, workflow)
    assert any(item.rule_id == "PLUGIN.PACKAGE.IMPORT" for item in ProjectPreparation(workspace).review().findings)
    (root / "root_rules.jsonc").write_text('{"rulesets":[]}')
    assert not any(item.rule_id == "PLUGIN.PACKAGE.IMPORT" for item in ProjectPreparation(workspace).review().findings)


def test_plain_implementation_files_are_not_executed_during_discovery(tmp_path):
    workspace, workflow, root = project(tmp_path)
    (root / "nodes/unselected_implementation.py").write_text("raise RuntimeError('implementation executed')\n")
    assert prepare_workflow_resources(workspace, workflow).catalogs.nodes.require("app.step")


def test_resource_candidates_include_unused_and_planned_nodeset_type_bodies():
    from vibeflow.core.flow import GraphConfig,NodeCallSpec,NodesetTypeSpec
    from vibeflow.tooling.project.resources.ownership import referenced_definition_ids
    body=GraphConfig((NodeCallSpec("leaf","real.business"),))
    group=NodesetTypeSpec("group","Group","Declared reusable body",(),(),body)
    graph=GraphConfig((NodeCallSpec("future","group",status="planned"),),nodeset_types={"group":group})
    assert referenced_definition_ids(graph)==frozenset({"group","real.business"})


def test_discovery_syntax_error_has_a_typed_resource_diagnostic(tmp_path):
    workspace,workflow,root=project(tmp_path)
    path=root/'base_lib/broken.py';path.parent.mkdir(exist_ok=True);path.write_text('def broken(:\n')
    from vibeflow.tooling.project.resources import prepare_workflow_resources,ResourcePreparationError
    with pytest.raises(ResourcePreparationError) as caught:prepare_workflow_resources(workspace,workflow)
    assert caught.value.code=='QUALITY.SYNTAX.PYTHON'
    assert caught.value.diagnostics[0]['source_location']=={'path':str(path),'line':1,'column':12}


def test_invalid_python_declaration_reports_its_source(tmp_path):
    from tests.fixtures.support.projects import project_root
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.project.resources import prepare_workflow_resources, ResourcePreparationError
    root = project_root(tmp_path)
    (root / "nodes").mkdir()
    declaration = root / "nodes/invalid.py"
    declaration.write_text('from vibeflow.targets.python.sdk import node\ninvalid = node(contract={})\n')
    config = root / "workflow.jsonc"
    config.write_text('{"pipeline":{"nodes":[{"id":"bad","definition_id":"missing","display_name":"Bad","description":"Invalid declaration"}]}}')
    with pytest.raises(ResourcePreparationError) as caught:
        prepare_workflow_resources(load_workspace_config(tmp_path / "vibeflow_config.jsonc"), config)
    assert caught.value.code == "DESCRIPTOR.INVALID"
    assert caught.value.diagnostics[0]["source_location"]["path"] == str(declaration)
    assert caught.value.diagnostics[0]["source_location"]["line"] == 2
