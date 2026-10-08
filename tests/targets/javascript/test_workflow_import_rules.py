"""Real workflow import Rules run before native compilation and AOT binding."""
from __future__ import annotations

from tests.fixtures.support.plugins import resource as sdk_resource, update_resources, resource_declarations

import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project, render_architecture
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError


ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def import_project(tmp_path):
    toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("requires the real project-local TypeScript/esbuild toolchain")
    sandbox = tmp_path / "integration"
    shutil.copytree(ROOT / "sandbox/javascript/integration", sandbox,
                    ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".artifacts"))
    project = sandbox / "project"
    from tests.fixtures.support.plugins import copy_sdk_inputs
    copy_sdk_inputs(ROOT / "sandbox/javascript/integration", sandbox)
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    # Workflow Rules receive actual source scopes even when Node Rules are unselected.
    definitions = resource_declarations(project)
    for definition in definitions:
        if definition["kind"] == "node":
            definition["rulesets"] = []
    update_resources(project, definitions)
    return sandbox / "vibeflow_config.jsonc", project


def _select_import_rule(project, scope, outcome):
    config = project / "configs" / ({"root": "linear", "nodeset": "nodeset", "loop": "loop"}[scope] + ".jsonc")
    owner = config if scope == "root" else project / "configs/nodesets" / ("arithmetic.jsonc" if scope == "nodeset" else "loop_body.jsonc")
    declaration = json.loads(owner.read_text())
    declaration["rulesets"] = ["test.workflow_import"]
    owner.write_text(json.dumps(declaration))
    # A loaded unused declaration can opt out of review without adding source reads.
    unused = {"type_key": "unused.block", "display_name": "Unused block", "description": "Outside the actual workflow closure.",
              "requires": [], "provides": [], "rulesets": [], "pipeline": declaration["pipeline"]}
    (project / "configs/nodesets/unused.jsonc").write_text(json.dumps(unused))
    document = json.loads(config.read_text())
    document.setdefault("nodeset_imports", []).append({"path": "nodesets/unused.jsonc"})
    config.write_text(json.dumps(document))
    rule = project / "rules/workflow_import.ts"
    returned = '{findings:[{code:"TEST.IMPORT.WARNING",severity:"warning",message:"Import evidence"},{code:"TEST.IMPORT.REJECT",severity:"error",message:"Reject actual workflow",source_location:{path:file,line:1,column:1}}]}'
    if outcome == "unavailable":
        returned = '{state:"unavailable",findings:[]}'
    elif outcome == "failed":
        returned = '{state:"failed",findings:[{code:"TEST.IMPORT.WARNING",severity:"warning",message:"Incomplete import"}]}'
    elif outcome == "completed":
        returned = '{records:{evidence:{type_id:"test.workflow_import.v1",value:{phase:context.phase,has_compiled:"compiled" in context.facts,order:context.facts.compiled?.order??[],paths:context.subject.call_paths,sources:context.facts.sources.map(source=>source.path)}}}}'
    rule.write_text('export function check(context) {\n'
        ' if((context.phase==="import" && "compiled" in context.facts) || (context.phase==="static" && !("compiled" in context.facts))) throw new Error("Phase needs real compilation facts");\n'
        ' for(const block of Object.values(context.facts.graph.nodesets)) if(!block.graph.nodeset_refs.every(id=>id in context.facts.graph.nodesets)) throw new Error("Invalid Nodeset declaration reference");\n'
        ' if(context.facts.sources.some(source=>source.path.includes("/negative/"))) throw new Error("Unrelated source scan");\n'
        ' const file=context.facts.source_files[0]; if(!file || !context.sources.symbols(file).length) throw new Error("Missing actual source ABI");\n'
        ' if(context.facts.graph.nodes.some(node=>node.type_used==="sandbox.add") && !context.facts.sources.some(source=>source.path.endsWith("/base_lib/math.ts"))) throw new Error("Missing reached helper snapshot");\n'
        ' return ' + returned + ';\n}\n')
    manifest = sdk_resource(project, "rule", "test.workflow_import")
    sdk_resource(project, "rule", "test.workflow_import").write_text(json.dumps({"kind": "rule", "id": "test.workflow_import", "outputs": {"evidence": "test.workflow_import.v1"} if outcome == "completed" else {},
        "implementations": [{"language": "typescript",  "source": {"kind": "file", "ref": "rules/workflow_import.ts", "export": "check"}}]}))
    (sdk_resource(project, "ruleset", "test.workflow_import")).write_text(json.dumps({"kind": "ruleset", "id": "test.workflow_import",
        "calls": [{"id": "check", "rule_id": "test.workflow_import"}], "entrypoints": {"import": ["check"], "static": ["check"] if outcome == "completed" else [], "run": []}}))
    return config, owner


@pytest.mark.parametrize("scope", ["root", "nodeset", "loop"])
@pytest.mark.parametrize("outcome", ["rejected", "unavailable", "failed"])
def test_actual_workflow_import_rejects_before_compilation_and_binding(import_project, tmp_path, monkeypatch, scope, outcome):
    workspace, project = import_project
    config, owner = _select_import_rule(project, scope, outcome)
    def unexpected_compile(*args, **kwargs):
        raise AssertionError("Native compilation or binding ran after rejected import")
    monkeypatch.setattr("vibeflow.tooling.application.javascript.build._compile_core_compilation", unexpected_compile)
    monkeypatch.setattr("vibeflow.tooling.application.javascript.audit._validate_graph_tree", unexpected_compile)
    code = "TEST.IMPORT.REJECT" if outcome == "rejected" else "RULE.RESULT." + outcome.upper()
    for operation in (
        lambda: audit_javascript_project(JavascriptAuditRequest(workspace, config)),
        lambda: build_project_aot(ProjectBuildRequest(workspace, config, tmp_path / "dist", "node", "single-esm")),
    ):
        with pytest.raises(ProjectBuildError) as error:
            operation()
        finding = next(item for item in error.value.diagnostics if item["code"] == code)
        assert finding["definition_id"] == "test.workflow_import"
        assert finding["object_type"] == "workflow"
        assert finding["object_id"] == str(owner)
        assert finding["details"]["call_paths"] == [[] if scope == "root" else ["arithmetic" if scope == "nodeset" else "loop"]]
        if outcome == "rejected":
            assert finding["source_location"]["line"] == 1
            assert Path(finding["source_location"]["path"]).is_file()
            assert any(item["code"] == "TEST.IMPORT.WARNING" for item in error.value.diagnostics)
        else:
            assert finding["details"]["state"] == outcome
            assert finding["details"]["phase"] == "import"
        assert not (tmp_path / "dist").exists()


@pytest.mark.parametrize("scope", ["root", "nodeset", "loop"])
def test_successful_workflow_import_records_survive_static_checks(import_project, scope):
    workspace, project = import_project
    config, _ = _select_import_rule(project, scope, "completed")
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    key = "workflow:" + ("" if scope == "root" else "arithmetic" if scope == "nodeset" else "loop")
    executions = audited.rule_report.results[key]
    imported = next(item for item in executions if item.plan.entrypoint == "import" and item.plan.invocations)
    evidence = next(record for result in imported.results.values() for record in result.records.values())
    assert evidence.value["phase"] == "import"
    assert evidence.value["has_compiled"] is False
    assert evidence.value["order"] == ()
    assert evidence.value["paths"] == (() if scope == "root" else ("arithmetic" if scope == "nodeset" else "loop",),)
    assert all("/negative/" not in file for file in evidence.value["sources"])
    checked = next(item for item in executions if item.plan.entrypoint == "static" and item.plan.invocations)
    static = next(record for result in checked.results.values() for record in result.records.values())
    assert static.value["phase"] == "static"
    assert static.value["has_compiled"] is True
    compiled = audited.compiled if scope == "root" else audited.compiled_by_path[("arithmetic" if scope == "nodeset" else "loop",)]
    assert static.value["order"] == compiled.order


def test_declaration_only_preview_keeps_import_unavailable_without_executing_rule(import_project):
    workspace, project = import_project
    config, _ = _select_import_rule(project, "root", "rejected")
    preview = audit_javascript_project(JavascriptAuditRequest(workspace, config, audit_sources=False))
    assert not preview.rule_report.findings
    imported = next(item for item in preview.rule_report.results["workflow:"] if item.plan.entrypoint == "import")
    assert imported.status == "ERROR"
    assert imported.results["check"].state == "unavailable"


def test_loaded_unused_nodeset_keeps_its_rule_selection_without_fake_calls(import_project):
    workspace, project = import_project
    config, _ = _select_import_rule(project, "root", "completed")
    unused = project / "configs/nodesets/unused.jsonc"
    declaration = json.loads(unused.read_text())
    declaration["rulesets"] = ["test.unregistered"]
    unused.write_text(json.dumps(declaration))
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, config))
    finding = next(item for item in error.value.diagnostics if item["code"] == "RULE.RESOURCE.UNKNOWN")
    assert finding["source_location"]["path"] == str(unused)
    assert not finding["details"].get("call_paths")


def test_workflow_import_builtin_reads_actual_scoped_source_ownership(import_project):
    workspace, project = import_project
    config, _ = _select_import_rule(project, "root", "completed")
    manifest = sdk_resource(project, "ruleset", "test.workflow_import")
    selection = json.loads(manifest.read_text())
    selection["calls"] = [{"id": "guard", "rule_id": "vibeflow.import_side_effects"}]
    selection["entrypoints"] = {"import": ["guard"], "static": [], "run": []}
    manifest.write_text(json.dumps(selection))
    source = project / "nodes/add.ts"
    source.write_text("let mutableCount = 0;\n" + source.read_text())
    with pytest.raises(ProjectBuildError) as error:
        audit_javascript_project(JavascriptAuditRequest(workspace, config))
    finding = next(item for item in error.value.diagnostics if item["code"] == "VF_IMPORT_SIDE_EFFECT")
    assert finding["definition_id"] == "vibeflow.import_side_effects"
    assert finding["source_location"] == {"path": str(source), "line": 1, "column": 1}
    assert finding["details"]["source_owner"]["id"] == "sandbox.add"
    assert finding["details"]["call_paths"] == [[]]


def test_architecture_normalizes_import_and_static_records_without_mutating_live_paths(import_project, tmp_path):
    workspace, project = import_project
    config, _ = _select_import_rule(project, "root", "completed")
    relocated = tmp_path / "relocated"
    shutil.copytree(project.parent, relocated, symlinks=True)
    left = audit_javascript_project(JavascriptAuditRequest(workspace, config))
    right = audit_javascript_project(JavascriptAuditRequest(relocated / workspace.name, relocated / "project" / config.relative_to(project)))
    assert render_architecture(left) == render_architecture(right)
    assert str(project) not in render_architecture(left)
    assert str(relocated / "project") not in render_architecture(right)
    for result, actual_project in ((left, project), (right, relocated / "project")):
        checks = [execution for execution in result.rule_report.results["workflow:"] if execution.plan.invocations]
        assert {execution.plan.entrypoint for execution in checks} == {"import", "static"}
        for execution in checks:
            source_paths = execution.results["check"].records["evidence"].value["sources"]
            assert all(Path(path).is_relative_to(actual_project) for path in source_paths)
        assert all(Path(owner["path"]).is_relative_to(actual_project)
                   for owner in result.rule_report.facts["import_policy"]["owners"])


def test_business_types_remain_outside_health_review(import_project, tmp_path):
    workspace, project = import_project
    source = project / "nodes/add.ts"
    source.write_text('const invalidBusinessType: number = "text";\n' + source.read_text())
    audited = audit_javascript_project(JavascriptAuditRequest(workspace, project / "configs/linear.jsonc"))
    assert not any(item.severity == "error" for item in audited.rule_report.findings)
    # The native target transpiles TypeScript; health rules do not silently add
    # a whole-program type checker to that existing compilation capability.
    built = build_project_aot(ProjectBuildRequest(workspace,project / "configs/linear.jsonc",tmp_path / "dist","node","single-esm"))
    assert built.out_dir.is_dir()

# Historic input mutations are published explicitly before the formal operation.
