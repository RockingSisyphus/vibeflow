"""Visible declaration identity and explicitly permitted, relocatable imports."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from vibeflow.tooling.project.preparation import ProjectPreparation
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))


def project(path, target):
    write(path / "vibeflow_config.jsonc", {"roots":[{"id":r,"path":r} for r in ("app","backend")]})
    for root in ("app", "backend"):
        write(path / root / "vibeflow_project.jsonc", {"project_target":target})
        if target == "javascript":
            write(path / root / "package.json", {"type":"module"})
            (path / root / "node_modules").symlink_to(Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]) / "node_modules", target_is_directory=True)
    return load_workspace_config(path / "vibeflow_config.jsonc")


def node(target, identifier="step", *, imports="", expression="731", node_type="vibeflow.node", support=()):
    contract = {"provides":[{"key":"answer","type":"answer","display_name":"Answer"}],
                "output_semantics":{"answer":["Imported value"]}}
    if target == "python":
        return ('from vibeflow.targets.python.sdk import node\n' + imports + '\n'
                f'@node(id={identifier!r},node_type={node_type!r},flow_kind="terminal",rulesets=[],implementation_files={list(support)!r},contract={contract!r})\n'
                f'class Step:\n    def run_pure(self,inputs,params):return {{"answer":{expression}}}\n')
    return ('import {defineNode} from "@vibeflow/plugin";\n' + imports + '\n'
            f'export const step=defineNode({{id:{json.dumps(identifier)},node_type:{json.dumps(node_type)},'
            f'flow_kind:"terminal",rulesets:[],implementation_files:{json.dumps(support)},contract:{json.dumps(contract)},run(){{return {{answer:{expression}}}}}}});\n')


def workflow(path):
    write(path, {"rulesets":[],"pipeline":{"nodes":[{"id":"call","definition_id":"step",
        "display_name":"Call","description":"Read imported value"}],
        "outputs":[{"type":"answer","as":"answer","cardinality":"exactly_one","display_name":"Answer"}]}})


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("shared", [False, True])
def test_unused_duplicate_nodes_fail_in_the_visible_scope(tmp_path, target, shared):
    workspace = project(tmp_path, target)
    suffix = ".py" if target == "python" else ".ts"
    write(tmp_path / ("app/nodes/step" + suffix), node(target))
    workflow(tmp_path / "app/main.jsonc")
    write(tmp_path / ("app/nodes/a" + suffix), node(target,"duplicate",node_type="unselected.type"))
    other = tmp_path if shared else tmp_path / "app"
    write(other / ("nodes/b" + suffix), node(target,"duplicate",node_type="unselected.type"))
    report = ProjectPreparation(workspace).review()
    conflicts = [item for item in report.findings if item.rule_id in {"DESCRIPTOR.DUPLICATE","DESCRIPTOR.CONFLICT"}]
    assert conflicts, [item.to_dict() for item in report.findings]
    assert "nodes/a" in conflicts[0].message and "nodes/b" in conflicts[0].message


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_private_same_names_do_not_activate_unused_types(tmp_path, target):
    workspace = project(tmp_path, target)
    suffix = ".py" if target == "python" else ".ts"
    for root in workspace.roots:
        write(root.path / ("nodes/step" + suffix), node(target))
        write(root.path / ("nodes/unused" + suffix), node(target,"unused",node_type="unselected.type"))
        workflow(root.path / "main.jsonc")
    report = ProjectPreparation(workspace).review()
    assert report.inventory.complete, [item.to_dict() for item in report.findings]
    assert not any("DESCRIPTOR" in item.rule_id for item in report.findings)


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_explicit_cross_root_import_survives_source_free_deployment(tmp_path, target):
    source = tmp_path / "source"
    workspace = project(source, target)
    suffix = ".py" if target == "python" else ".ts"
    library = ('from pathlib import Path\nfrom vibeflow.targets.python.sdk import base_lib\n'
               'marker=Path(__file__).with_name("loads.txt")\n'
               'marker.write_text(marker.read_text()+"loaded\\n" if marker.exists() else "loaded\\n")\n'
               '@base_lib(id="backend.secret",rulesets=[],implementation_files=["value.txt"])\n'
               'def value():return int(Path(__file__).with_name("value.txt").read_text())\n' if target == "python" else
               'import {defineBaseLib} from "@vibeflow/plugin";\nexport function value(){return 731;}\n'
               'export const lib=defineBaseLib({id:"backend.secret",rulesets:[],implementation:value});\n')
    write(source / ("backend/base_lib/secret" + suffix), library)
    write(source / "backend/base_lib/value.txt", "731")
    imports = ('from backend.base_lib.secret import value' if target == "python" else
               'import {value} from "../../backend/base_lib/secret.ts";')
    write(source / ("app/nodes/step" + suffix), node(target, imports=imports, expression="value()", support=["../../backend/base_lib/secret" + suffix]))
    config = source / "app/main.jsonc"
    workflow(config)
    if target == "javascript":
        write(source / "app/plugins/types/plugin.ts",
            'import {definePlugin,defineDataSchema} from "@vibeflow/plugin";\n'
            'export const plugin=definePlugin({id:"types",resources:[defineDataSchema({type_key:"answer",schema:{type:"number"}})]});\n')
        data = json.loads(config.read_text())
        data["plugins"] = [{"source":{"kind":"file","ref":"plugins/types/plugin.ts"}}]
        write(config, data)
    restricted = ProjectPreparation(workspace).review()
    assert any(item.severity == "error" for item in restricted.findings)
    for root in workspace.roots:
        write(root.path / "root_rules.jsonc", {"rule_params":{"vibeflow.root.resources":{"allow_cross_root_imports":True}}})
    if target == "python":
        from vibeflow.tooling.application.python.workspace_service import run_workspace_checked
        from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
        result = run_workspace_checked(config, workspace=workspace,run_root=tmp_path/"runs",preview_root=tmp_path/"preview")
        assert result.public_outputs["answer"] == 731
        (source / "backend/base_lib/loads.txt").unlink()
        # A dependency-only build must not discover/activate the whole foreign root.
        write(source / "backend/base_lib/unrelated.py", 'from vibeflow.targets.python.sdk import base_lib\nraise AssertionError("unrelated resource loaded")\n')
        built = build_python_aot(PythonBuildRequest(workspace, config, tmp_path/"built",preview_root=tmp_path/"preview"))
        assert (source / "backend/base_lib/loads.txt").read_text() == "loaded\n"
        assert not (built.out_dir / "shared/backend/base_lib/unrelated.py").exists()
    else:
        from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
        built = build_project_aot(ProjectBuildRequest(workspace.path,config,tmp_path/"built",target="node",profile="single-esm",preview_root=tmp_path/"preview"))
    entry = built.entry.relative_to(built.out_dir)
    relocated = tmp_path / "relocated"
    built.out_dir.rename(relocated)
    shutil.rmtree(source)
    environment = {key:value for key,value in os.environ.items() if key != "PYTHONPATH"}
    if target == "python":
        script = ('import sys;sys.path.insert(0,sys.argv[1]);from vibeflow.tooling.application.python.bundle import PythonBundle;'
                  'from vibeflow.tooling.project import inventory;'
                  'inventory.inventory_project=lambda *a,**k:(_ for _ in ()).throw(AssertionError("rescan"));'
                  'print(PythonBundle(sys.argv[2]).run(run_root=sys.argv[3]).public_outputs["answer"])')
        command = [sys.executable,"-I","-c",script,str(relocated/"_framework"),str(relocated),str(tmp_path/"aot-runs")]
    else:
        command = ["node","--input-type=module","-e",
            'const m=await import(process.argv[1]);const r=m.runWorkflow({});console.log(JSON.stringify(r));', (relocated/entry).as_uri()]
    result = subprocess.run(command,cwd=tmp_path,env=environment,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert "731" in result.stdout, result.stdout


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("policy", ["default", "allow", "disabled", "shared_only"])
def test_shared_code_cannot_import_root_private_code(tmp_path, target, policy):
    workspace = project(tmp_path, target)
    suffix = ".py" if target == "python" else ".ts"
    write(tmp_path / ("backend/base_lib/secret" + suffix),
          "def value():return 731\n" if target == "python" else "export function value(){return 731;}\n")
    write(tmp_path / ("base_lib/shared" + suffix),
          "from backend.base_lib.secret import value\n" if target == "python" else
          'export {value} from "../backend/base_lib/secret.ts";\n')
    write(tmp_path / ("app/nodes/step" + suffix), node(target, expression="value()", imports=
          "from base_lib.shared import value" if target == "python" else
          'import {value} from "../../base_lib/shared.ts";'))
    workflow(tmp_path / "app/main.jsonc")
    if policy == "shared_only":
        write(tmp_path / ("base_lib/shared" + suffix),
              "def value():return 731\n" if target == "python" else "export function value(){return 731;}\n")
    if policy in {"allow", "disabled"}:
        write(tmp_path / "project_rules.jsonc", {"rulesets":[]} if policy == "disabled" else
              {"rule_params":{"vibeflow.project.dependencies":{"allow_cross_root_imports":True}}})
    # Root-scoped checks/builds must enforce the same boundary as a project scan.
    for selected in (None, *workspace.roots):
        report = ProjectPreparation(workspace, root=selected).review()
        findings = [item for item in report.findings if item.rule_id == "PROJECT.RESOURCE.PRIVATE_IMPORT"]
        assert bool(findings) == (policy == "default")
        if findings:
            assert findings[0].source_location["path"].endswith("base_lib/shared" + suffix)
            assert findings[0].details["imported_root"] == "backend"


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_quality_command_reports_shared_reverse_import(tmp_path, target, capsys):
    from vibeflow.tooling.application.cli import main
    project(tmp_path, target)
    suffix = ".py" if target == "python" else ".ts"
    write(tmp_path / ("backend/base_lib/private" + suffix),
          "VALUE=731\n" if target == "python" else "export const VALUE=731;\n")
    write(tmp_path / ("base_lib/shared" + suffix),
          "from backend.base_lib.private import VALUE\n" if target == "python" else
          'export {VALUE} from "../backend/base_lib/private.ts";\n')
    assert main(["quality-check", "--path", str(tmp_path / "app"), "--json"]) != 0
    report = json.loads(capsys.readouterr().out)
    assert any(item["rule_id"] == "PROJECT.RESOURCE.PRIVATE_IMPORT" for item in report["errors"])
