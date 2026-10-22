"""Owner-relative imports and same-named private resources across two roots."""
import json
import shutil

from vibeflow.tooling.project.workspace_loader import load_workspace_config
from vibeflow.tooling.project.preparation import ProjectPreparation
from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
from vibeflow.tooling.application.python.bundle import PythonBundle
from vibeflow.tooling.application.python.workspace_service import run_workspace_checked


def shared_project(path):
    for group in ("nodes", "base_lib"):
        (path / group).mkdir()
    (path / "base_lib/shared.py").write_text('''from vibeflow.targets.python.sdk import base_lib
@base_lib(id="shared.math", rulesets=[])
def increment(value): return value + 10
''')
    (path / "nodes/shared.py").write_text('''from vibeflow.targets.python.sdk import node
from ..base_lib.shared import increment
@node(id="shared.step", node_type="vibeflow.node", flow_kind="terminal", rulesets=[], base_libs=["shared.math"],
 contract={"requires":[{"type":"local.value","cardinality":"exactly_one","display_name":"Local value"}],
 "provides":[{"key":"result","type":"result.value","display_name":"Result"}],"input_semantics":{"local.value":["Prepared private value"]},"output_semantics":{"result":["Shared result"]}})
class Shared:
    def run_pure(self, inputs, params): return {"result":increment(inputs["local.value"]["value"])}
''')
    for name, factor in (("desktop", 2), ("backend", 3)):
        root = path / name
        for group in ("nodes", "base_lib", "configs"):
            (root / group).mkdir(parents=True)
        (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
        (root / "base_lib/local.py").write_text(f'''from vibeflow.targets.python.sdk import base_lib
@base_lib(id="local.math", rulesets=[])
def multiply(value): return value * {factor}
''')
        (root / "nodes/local.py").write_text('''from vibeflow.targets.python.sdk import node
from ..base_lib.local import multiply
@node(id="local.step", node_type="vibeflow.node", flow_kind="terminal", rulesets=[], base_libs=["local.math"],
 contract={"provides":[{"key":"local","type":"local.value","display_name":"Local value"}],"output_semantics":{"local":["Private result"]}})
class Local:
    def run_pure(self, inputs, params): return {"local":multiply(4)}
''')
        data = {"base_lib":{"modules":["local.math","shared.math"]},"pipeline":{"nodes":[
            {"id":"local","definition_id":"local.step","display_name":"Local","description":"Prepare private value"},
            {"id":"shared","definition_id":"shared.step","display_name":"Shared","description":"Apply shared arithmetic"}],
            "edges":[["local","shared"]],"outputs":[{"type":"result.value","cardinality":"exactly_one","display_name":"Result","as":"result"}]}}
        (root / "configs/main.jsonc").write_text(json.dumps(data))
    (path / "vibeflow_config.jsonc").write_text(json.dumps({"roots":[{"id":name,"path":name} for name in ("desktop","backend")]}))
    return load_workspace_config(path / "vibeflow_config.jsonc")


def test_shared_and_private_imports_survive_two_roots_and_moved_aot(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    workspace = shared_project(source)
    governance = ProjectPreparation(workspace).review()
    assert not governance.findings, [item.to_dict() for item in governance.findings]
    for root, expected in zip(workspace.roots, (18, 22)):
        config = root.path / "configs/main.jsonc"
        result = run_workspace_checked(config, workspace=workspace, run_root=tmp_path / "source-runs",
            run_id=root.id, preview_root=tmp_path / "preview")
        assert result.public_outputs["result"] == expected
        build_python_aot(PythonBuildRequest(workspace.path, config, tmp_path / ("bundle-" + root.id),
                                           preview_root=tmp_path / "preview"))
    shutil.rmtree(source)
    for name, expected in (("desktop", 18), ("backend", 22)):
        bundle = PythonBundle(tmp_path / ("bundle-" + name))
        result = bundle.run(run_root=tmp_path / "aot-runs", run_id=name)
        assert result.public_outputs["result"] == expected


def test_javascript_project_plugin_uses_consumer_toolchain_and_bundles_both_owners(tmp_path):
    import os
    import subprocess
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
    from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest, audit_javascript_project
    source=tmp_path/"source";source.mkdir()
    for directory in ("nodes","base_lib","plugins/layout"):(source/directory).mkdir(parents=True)
    (source/"plugins/layout/plugin.ts").write_text('''import {definePlugin,defineNodeType,defineDataSchema} from "@vibeflow/plugin";
const shell=defineNodeType({id:"shared.shell",rulesets:[],presentation:{shape:"hex",fill:"#abcdef"}});
export const plugin=definePlugin({id:"layout",resources:[shell,...["local.value","result.value"].map(type_key=>defineDataSchema({type_key,schema:{type:"number"}}))]});
''')
    (source/"base_lib/shared.ts").write_text('''import {defineBaseLib} from "@vibeflow/plugin";
export function increment(value){return value+10;}
export const library=defineBaseLib({id:"shared.math",rulesets:[],implementation:increment});
''')
    (source/"nodes/shared.ts").write_text('''import {defineNode} from "@vibeflow/plugin";
import {increment} from "../base_lib/shared.ts";
export const shared=defineNode({id:"shared.step",node_type:"shared.shell",flow_kind:"terminal",base_libs:["shared.math"],
 contract:{requires:[{type:"local.value",cardinality:"exactly_one",display_name:"Local value"}],provides:[{key:"result",type:"result.value",display_name:"Result"}],input_semantics:{"local.value":["Prepared private value"]},output_semantics:{result:["Shared result"]}},
 run(inputs){return {result:increment(inputs["local.value"].value)};}});
''')
    for name,factor in (("desktop",2),("backend",3)):
        root=source/name
        (root/"nodes").mkdir(parents=True);(root/"configs").mkdir()
        (root/"package.json").write_text('{"type":"module"}')
        (root/"node_modules").symlink_to(os.path.join(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"],"node_modules"),target_is_directory=True)
        (root/"vibeflow_project.jsonc").write_text('{"project_target":"javascript"}')
        (root/"root_rules.jsonc").write_text('{"rulesets":[]}')
        (root/"nodes/local.ts").write_text('''import {defineNode} from "@vibeflow/plugin";
export const local=defineNode({id:"local.step",node_type:"vibeflow.node",flow_kind:"terminal",rulesets:[],
 contract:{provides:[{key:"local",type:"local.value",display_name:"Local value"}],output_semantics:{local:["Private result"]}},
 run(){return {local:4*FACTOR};}});
'''.replace('FACTOR',str(factor)))
        (root/"configs/main.jsonc").write_text(json.dumps({"plugins":[{"scope":"project","source":{"kind":"file","ref":"plugins/layout/plugin.ts"}}],
            "pipeline":{"nodes":[{"id":key,"definition_id":key+".step","display_name":key,"description":key} for key in ("local","shared")],
            "edges":[["local","shared"]],"outputs":[{"type":"result.value","as":"result","cardinality":"exactly_one","display_name":"Result"}]}}))
    (source/"vibeflow_config.jsonc").write_text(json.dumps({"roots":[{"id":name,"path":name} for name in ("desktop","backend")]}))
    workspace=load_workspace_config(source/"vibeflow_config.jsonc")
    review=ProjectPreparation(workspace).review()
    assert not review.findings,[item.to_dict() for item in review.findings]
    entries=[]
    for root in workspace.roots:
        request=JavascriptAuditRequest(workspace.path,root.path/"configs/main.jsonc",audit_sources=False)
        assert audit_javascript_project(request).architecture==audit_javascript_project(request).architecture
        built=build_project_aot(ProjectBuildRequest(workspace.path,root.path/"configs/main.jsonc",tmp_path/('bundle-'+root.id),"node","single-esm",preview_root=tmp_path/"preview"))
        entries.append(built.entry)
    shutil.rmtree(source)
    for entry,expected in zip(entries,(18,22)):
        actual=subprocess.run(['node','--input-type=module','-e','const m=await import(process.argv[1]);console.log(JSON.stringify(m.runWorkflow({})));',entry.as_uri()],capture_output=True,text=True)
        assert actual.returncode==0,actual.stderr
        assert json.loads(actual.stdout)=={"result":expected}
