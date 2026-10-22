"""Resource policy is replaceable once, with the same result for every consumer."""
import json

import pytest

from tests.tooling.test_project_dependency_scope import project, node, workflow, write
from vibeflow.tooling.project.preparation import ProjectPreparation


def example(path, target="python"):
    workspace = project(path, target)
    suffix = "py" if target == "python" else "ts"
    library = ('from vibeflow.targets.python.sdk import base_lib\n'
               '@base_lib(id="d",rulesets=[])\ndef value(): return 731\n' if target == "python" else
               'import {defineBaseLib} from "@vibeflow/plugin";\nexport function value(){return 731;}\n'
               'export const lib=defineBaseLib({id:"d",rulesets:[],implementation:value});\n')
    write(path / f"app/base_lib/d.{suffix}", library)
    imports = 'from ..base_lib.d import value' if target == "python" else 'import {value} from "../base_lib/d.ts";'
    body = node(target, imports=imports, expression="value()")
    body = body.replace('rulesets=[]', 'rulesets=[],base_libs=["d"]') if target == "python" else body.replace('rulesets:[]', 'rulesets:[],base_libs:["d"]')
    write(path / f"app/nodes/step.{suffix}", body)
    config = path / "app/configs/main.jsonc"
    workflow(config)
    return workspace, config


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("selection", [None, {}, {"modules": []}, {"modules": ["d"]}])
def test_explicit_independent_libraries(tmp_path, selection, target):
    workspace, config = example(tmp_path, target)
    data = json.loads(config.read_text())
    if selection is not None:
        data["base_lib"] = selection
    write(config, data)
    preparation = ProjectPreparation(workspace, root=workspace.root_for_path(config), workflow=config)
    review = preparation.review()
    errors = [item.rule_id for item in review.findings if item.severity == "error"]
    selected = selection == {"modules": ["d"]}
    assert ("RESOURCE.REFERENCE.UNAVAILABLE" in errors) != selected, [item.to_dict() for item in review.findings]
    assert preparation.resource_use(config).allows("base_lib", "d") == selected
    assert not selected or not errors, [item.to_dict() for item in review.findings]


def test_indirect_library_requires_its_own_selection(tmp_path):
    workspace, config = example(tmp_path)
    source = tmp_path / "app/base_lib/d.py"
    source.write_text(source.read_text().replace('rulesets=[]', 'rulesets=[],dependencies=["e"]'))
    write(tmp_path / "app/base_lib/e.py", 'from vibeflow.targets.python.sdk import base_lib\n@base_lib(id="e",rulesets=[])\ndef extra():return 1\n')
    data = json.loads(config.read_text())
    for modules in (["d"], ["d", "e"]):
        data["base_lib"] = {"modules": modules}
        write(config, data)
        findings = ProjectPreparation(workspace, root=workspace.root_for_path(config), workflow=config).review().findings
        errors = [item for item in findings if item.severity == "error"]
        assert bool(errors) == (modules == ["d"]), [item.to_dict() for item in findings]


def test_disabled_resource_rules_are_unconstrained(tmp_path):
    workspace, config = example(tmp_path)
    write(tmp_path / "app/root_rules.jsonc", {"rulesets": []})
    preparation = ProjectPreparation(workspace, root=workspace.root_for_path(config), workflow=config)
    assert not preparation.review().findings
    assert preparation.resource_use(config).resources is None


def custom_selection(path):
    write(path / "app/plugins/policy/plugin.py", '''from vibeflow.targets.python.sdk import Plugin,rule,ruleset,RuleCall,RuleRelation
from vibeflow.core.rules import RuleRecord,RuleResult
@rule(id="custom.libraries",level="root",outputs={"resources":"vibeflow.resource_set.v1"})
def libraries(context,inputs,params):
    values={w["workflow"]:[{"kind":"base_lib","id":r["id"],"reason":"custom"}
        for r in w["resources"] if r["kind"]=="base_lib" and r["owner"]["kind"]!="plugin"]
        for w in context.facts["root"]["resource_workflows"]}
    return RuleResult({"resources":RuleRecord("vibeflow.resource_set.v1",{"workflows":values})})
checks=ruleset(id="custom.defaults",calls=[RuleCall("defaults",ruleset_id="vibeflow.root.default")],
    relations=[RuleRelation("$self","defaults/resource_independent","overrides",replace_rule="custom.libraries")])
plugin=Plugin(id="policy",resources=[libraries,checks])
''')
    write(path / "app/root_rules.jsonc", {"plugins": [{"source": {"kind": "file", "ref": "plugins/policy/plugin.py"}}],
        "rulesets": ["custom.defaults"]})


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_replacement_controls_validation_execution_and_moved_bundle(tmp_path, target):
    import shutil
    import subprocess
    workspace, config = example(tmp_path / "source", target)
    custom_selection(tmp_path / "source")
    if target == "javascript":
        write(tmp_path / "source/app/plugins/types/plugin.ts", 'import {definePlugin,defineDataSchema} from "@vibeflow/plugin";\n'
            'export const plugin=definePlugin({id:"types",resources:[defineDataSchema({type_key:"answer",schema:{type:"number"}})]});\n')
        data = json.loads(config.read_text())
        data["plugins"] = [{"source": {"kind": "file", "ref": "plugins/types/plugin.ts"}}]
        write(config, data)
    preparation = ProjectPreparation(workspace, root=workspace.root_for_path(config), workflow=config)
    findings = preparation.review().findings
    assert not [item for item in findings if item.severity == "error"], [item.to_dict() for item in findings]
    assert preparation.resource_use(config).allows("base_lib", "d")
    if target == "python":
        from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
        from vibeflow.tooling.application.python.build import build_python_aot, PythonBuildRequest
        from vibeflow.tooling.application.python.bundle import PythonBundle
        assert run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "runs", preview_root=tmp_path / "preview").public_outputs["answer"] == 731
        built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "built", preview_root=tmp_path / "preview"))
        assert json.loads((built.out_dir / "python-workflow.json").read_text())["resource_use"]["resources"]
        built.out_dir.rename(tmp_path / "moved")
        shutil.rmtree(tmp_path / "source")
        assert PythonBundle(tmp_path / "moved").run(run_root=tmp_path / "bundle-runs").public_outputs["answer"] == 731
    else:
        from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
        from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
        assert audit_javascript_project(JavascriptAuditRequest(workspace, config)).architecture["resource_use"]["resources"]
        built = build_project_aot(ProjectBuildRequest(workspace.path, config, tmp_path / "built", "node", "single-esm", preview_root=tmp_path / "preview"))
        assert json.loads((built.out_dir / "resource-use.json").read_text())["resources"]
        entry = built.entry.relative_to(built.out_dir)
        built.out_dir.rename(tmp_path / "moved")
        shutil.rmtree(tmp_path / "source")
        result = subprocess.run(["node", "--input-type=module", "-e",
            'const m=await import(process.argv[1]);console.log(JSON.stringify(m.runWorkflow({})));', (tmp_path / "moved" / entry).as_uri()], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout) == {"answer": 731}


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("selection", ["enabled", "disabled", "planned", "duplicate"])
def test_plugin_libraries_are_selected_as_one_package(tmp_path, target, selection):
    workspace, config = example(tmp_path, target)
    suffix = "py" if target == "python" else "ts"
    package = tmp_path / "app/plugins/a"
    package.mkdir(parents=True)
    (tmp_path / f"app/base_lib/d.{suffix}").rename(package / f"library.{suffix}")
    source = tmp_path / f"app/nodes/step.{suffix}"
    source.write_text(source.read_text().replace("..base_lib.d", "..plugins.a.library").replace("../base_lib/d.ts", "../plugins/a/library.ts"))
    write(package / f"plugin.{suffix}",
        'from vibeflow.targets.python.sdk import Plugin\nfrom .library import value\nplugin=Plugin(id="a",resources=[value])\n' if target == "python" else
        'import {definePlugin} from "@vibeflow/plugin";\nimport {lib} from "./library.ts";\nexport const plugin=definePlugin({id:"a",resources:[lib]});\n')
    data = json.loads(config.read_text())
    spec = {"id":"a","source":{"kind":"file","ref":f"plugins/a/plugin.{suffix}"}}
    if selection == "disabled":spec["enabled"] = False
    if selection == "planned":spec.update(status="planned",display_name="Future a",description="Future package")
    data["plugins"] = [spec]
    if selection == "duplicate":data["base_lib"] = {"modules":["d"]}
    write(config,data)
    preparation = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
    findings = preparation.review().findings
    codes = {item.rule_id for item in findings if item.severity == "error"}
    if selection == "enabled":assert not codes, [item.to_dict() for item in findings]
    elif selection == "duplicate":assert "RESOURCE.BASE_LIB.PLUGIN_SELECTION" in codes
    else:assert "RESOURCE.REFERENCE.UNAVAILABLE" in codes
    assert preparation.resource_use(config).allows("base_lib","d") == (selection in {"enabled","duplicate"})


def test_failed_selection_rule_never_becomes_unconstrained(tmp_path):
    workspace, config = example(tmp_path)
    custom_selection(tmp_path)
    plugin = tmp_path / "app/plugins/policy/plugin.py"
    plugin.write_text(plugin.read_text().replace('    values={', '    raise ValueError("policy failed")\n    values={'))
    preparation = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
    assert any("policy failed" in item.message for item in preparation.review().findings)
    with pytest.raises(ValueError,match="did not produce"):
        preparation.resource_use(config)


@pytest.mark.parametrize("scope", ["root", "project"])
@pytest.mark.parametrize("member", ["entry", "support", "symlink", "import", "module"])
def test_plugin_owned_code_must_stay_in_its_actual_directory(tmp_path, scope, member):
    workspace, config = example(tmp_path)
    base = tmp_path / "app" if scope == "root" else tmp_path
    package = base / "plugins/a"
    package.mkdir(parents=True)
    write(base / "outside.py", 'def value():return 731\n')
    write(package / "inside.py", 'def value():return 731\n')
    (tmp_path / "app/base_lib/d.py").unlink()
    source = tmp_path / "app/nodes/step.py"
    source.write_text(source.read_text().replace('from ..base_lib.d import value','').replace('value()', '731'))
    ref = "inside.py"
    support = []
    imported = ''
    if member == "module":ref = "outside"
    if member == "entry":ref = "../../outside.py"
    if member == "support":support = ["../../outside.py"]
    if member == "symlink":
        (package / "link.py").symlink_to(base / "outside.py")
        ref = "link.py"
    if member == "import":imported = 'from ...outside import value\n'
    write(package / "plugin.py", 'from vibeflow.targets.python.sdk import Plugin,base_lib,SourceLocator\n'+imported+
        f'library=base_lib(id="d",rulesets=[],source=SourceLocator(kind={"module" if member == "module" else "file"!r},ref={ref!r}),implementation_files={support!r})\n'
        'plugin=Plugin(id="a",resources=[library])\n')
    data = json.loads(config.read_text())
    data["plugins"] = [{"scope":scope,"source":{"kind":"file","ref":"plugins/a/plugin.py"}}]
    write(config,data)
    findings = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config).review().findings
    expected = "PLUGIN.PACKAGE.IMPORT" if member == "import" else "PLUGIN.PACKAGE.OWNERSHIP"
    assert any(item.rule_id == expected and item.definition_id == f"vibeflow.{scope}.plugin_ownership" for item in findings), [item.to_dict() for item in findings]
    if member == "module":
        write(tmp_path / "project_rules.jsonc", {"rulesets": []})
        write(tmp_path / "app/root_rules.jsonc", {"rulesets": []})
        unchecked = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
        assert not unchecked.review().findings
        assert unchecked.resource_use(config).allows("base_lib", "d")



def test_changed_graph_rechecks_references_through_selected_rules(tmp_path):
    from dataclasses import replace
    workspace, config = example(tmp_path)
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][0].update(status="planned",planned_behavior="blocking",flow_kind="terminal",requires=[],provides=[])
    write(config,data)
    preparation = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
    assert not any(item.rule_id == "RESOURCE.REFERENCE.UNAVAILABLE" for item in preparation.review().findings)
    graph = preparation.workflow_resources(config).graph
    changed = replace(graph,nodes=tuple(replace(node,status="implemented",planned_behavior="") for node in graph.nodes))
    review = preparation.review_graph(config,changed)
    assert any(item.rule_id == "RESOURCE.REFERENCE.UNAVAILABLE" for item in review.findings)


@pytest.mark.parametrize("output", ["conflicting", "missing", "unknown", "no_resources", "bad_planned"])
def test_invalid_or_conflicting_final_providers_are_errors(tmp_path, output):
    workspace, config = example(tmp_path)
    custom_selection(tmp_path)
    plugin = tmp_path / "app/plugins/policy/plugin.py"
    text = plugin.read_text()
    rows = '[{"kind":"base_lib","id":"unknown","reason":"custom"}]' if output == "unknown" else '[]'
    value = '{}' if output == "missing" else '{w["workflow"]:{"workflow":w["workflow"],"resources":'+rows+'} for w in context.facts["root"]["resource_workflows"]}'
    if output == "no_resources":value = '{w["workflow"]:{"workflow":w["workflow"]} for w in context.facts["root"]["resource_workflows"]}'
    if output == "bad_planned":value = '{w["workflow"]:{"workflow":w["workflow"],"resources":None,"planned":[7]} for w in context.facts["root"]["resource_workflows"]}'
    text += '\n@rule(id="custom.final",level="root",outputs={"use":"vibeflow.resource_use.v1"})\ndef final(context,inputs,params):\n    return RuleResult({"use":RuleRecord("vibeflow.resource_use.v1",{"workflows":'+value+'})})\nplugin=Plugin(id="policy",resources=[libraries,checks,final])\n'
    plugin.write_text(text)
    rules = tmp_path / "app/root_rules.jsonc"
    data = json.loads(rules.read_text())
    data["rulesets"] = ([{"rule_id":"custom.final"}] if output in {"no_resources", "bad_planned"}
                        else [*data["rulesets"], {"rule_id":"custom.final"}])
    write(rules,data)
    preparation = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
    findings = preparation.review().findings
    assert any(item.rule_id == "RESOURCE.RECORD.INVALID" for item in findings), [item.to_dict() for item in findings]
    with pytest.raises(ValueError,match="did not produce"):
        preparation.resource_use(config)


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_visibility_replacement_cannot_be_bypassed_by_a_node_call(tmp_path, target):
    workspace, config = example(tmp_path, target)
    data = json.loads(config.read_text())
    data["base_lib"] = {"modules": ["d"]}
    write(config, data)
    custom_selection(tmp_path)
    plugin = tmp_path / "app/plugins/policy/plugin.py"
    source = plugin.read_text()
    start, end = source.index("    values="), source.index("    return RuleResult")
    source = source[:start] + '    values={w["workflow"]:[r for r in w["resources"] if r["kind"]!="node"] for w in context.facts["root"]["resource_workflows"]}\n' + source[end:]
    plugin.write_text(source.replace("defaults/resource_independent", "defaults/resource_visibility"))
    findings = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config).review().findings
    assert any(item.rule_id == "RESOURCE.REFERENCE.UNAVAILABLE" and item.details.get("resource_id") == "step" for item in findings)


def test_actual_javascript_compile_hook_rechecks_new_library_reference(tmp_path):
    from dataclasses import replace
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, prepare_project_build
    from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
    workspace, config = example(tmp_path, "javascript")
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][0].update(status="planned",planned_behavior="blocking",flow_kind="terminal",requires=[],provides=[])
    write(config, data)
    called = []
    def implement(graph, catalogs):
        called.append(True)
        return replace(graph,nodes=tuple(replace(node,status="implemented",planned_behavior="") for node in graph.nodes))
    with pytest.raises(ProjectBuildError) as error:
        prepare_project_build(ProjectBuildRequest(workspace.path, config, tmp_path / "bundle",target="node",profile="single-esm"),before_compile_hooks=(implement,))
    assert called == [True]
    assert error.value.code == "RESOURCE.REFERENCE.UNAVAILABLE"


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_uncalled_nodes_remain_candidates_without_resolving_unused_types(tmp_path, target):
    workspace, config = example(tmp_path, target)
    suffix = "py" if target == "python" else "ts"
    write(tmp_path / f"app/nodes/unused.{suffix}", node(target, "unused", node_type="unselected.type"))
    data = json.loads(config.read_text())
    data["base_lib"] = {"modules": ["d"]}
    write(config, data)
    preparation = ProjectPreparation(workspace,root=workspace.root_for_path(config),workflow=config)
    assert not preparation.review().findings
    assert preparation.resource_use(config).allows("node", "unused")


@pytest.mark.parametrize("custom", [False, True])
def test_available_unused_library_is_not_loaded_or_packaged(tmp_path, custom):
    import shutil
    from vibeflow.tooling.application.python.build import build_python_aot, PythonBuildRequest
    from vibeflow.tooling.application.python.bundle import PythonBundle
    source = tmp_path / "source"
    workspace, config = example(source)
    package = source / "app/base_lib"
    write(package / "__init__.py", "")
    write(package / "unused_impl.py", 'raise RuntimeError("unused implementation loaded")\n')
    write(package / "unused.py", 'from vibeflow.targets.python.sdk import base_lib,SourceLocator\n'
        'unused=base_lib(id="unused",rulesets=[],source=SourceLocator(kind="file",ref="base_lib/unused_impl.py",export="value"),implementation_files=["base_lib/missing.txt"])\n')
    if custom:
        custom_selection(source)
    else:
        data = json.loads(config.read_text())
        data["base_lib"] = {"modules": ["d", "unused"]}
        write(config, data)
    built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path / "built", preview_root=tmp_path / "preview"))
    use = json.loads((built.out_dir / "python-workflow.json").read_text())["resource_use"]
    assert any(item["id"] == "unused" for item in use["resources"])
    assert not list(built.out_dir.rglob("unused_impl.py"))
    assert not list(built.out_dir.rglob("unused.py"))
    built.out_dir.rename(tmp_path / "moved")
    shutil.rmtree(source)
    assert PythonBundle(tmp_path / "moved").run(run_root=tmp_path / "runs").public_outputs["answer"] == 731
