"""Native JS SDK resources retain separate business and Plugin ownership."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import pytest
from tests.fixtures.support.projects import register_root
from vibeflow.tooling.application.cli import main
from vibeflow.tooling.application.rule_review import effective_rule_plans
from vibeflow.tooling.project.workspace_loader import load_project_workspace
from vibeflow.tooling.project.resources import prepare_workflow_resources

SOURCE='''import {defineNode} from "@vibeflow/plugin";
export const calculation=defineNode({node_type:"demo.shell",id:"demo.calculate",contract:{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["Computed value"]}},rulesets:["vibeflow.process","demo.checks"],run(inputs,params){return {result:7};}});
export const start=defineNode({node_type:"demo.shell",id:"demo.start",flow_kind:"terminal",contract:{},rulesets:[],run(inputs,params){return {};}});
'''
PLUGIN_SOURCE='''import {definePlugin,defineNodeType,defineRule,defineRuleset,defineDataSchema} from "@vibeflow/plugin";
export const shell=defineNodeType({id:"demo.shell",presentation:{shape:"rect",fill:"#add8e6"}});
export const health=defineRule({id:"demo.health",check(context,inputs,params){return {records:{},findings:[]};}});
export const checks=defineRuleset({id:"demo.checks",calls:[{id:"health",rule_id:"demo.health"}]});
export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});
export const plugin=definePlugin({id:"demo",resources:[shell,health,checks,number],config_schema:{type:"object",properties:{value:{type:"integer"}},additionalProperties:false},config_defaults:{value:1}});
'''


def project(root, source=SOURCE, selections=None, *, plugin_source=PLUGIN_SOURCE):
    root=Path(root);root.mkdir(parents=True,exist_ok=True);register_root(root,"javascript")
    toolchain=Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    (root/"node_modules").symlink_to(toolchain/"node_modules",target_is_directory=True)
    (root/"package.json").write_text('{"name":"sdk-test","type":"module","private":true}')
    shutil.copy2(toolchain/"package-lock.json",root/"package-lock.json")
    (root/"nodes").mkdir();(root/"nodes/steps.ts").write_text(source)
    (root/"plugins/demo").mkdir(parents=True);(root/"plugins/demo/plugin.ts").write_text(plugin_source)
    config=root/"workflow.jsonc"
    config.write_text(json.dumps({"plugins":selections if selections is not None else [{"source":{"kind":"file","ref":"plugins/demo/plugin.ts"}}],"rulesets":[],"pipeline":{"nodes":[{"id":"start","definition_id":"demo.start","display_name":"Start","description":"Starts calculation"},{"id":"calculate","definition_id":"demo.calculate","display_name":"Calculate","description":"Performs calculation"}],"edges":[["start","calculate"]],"outputs":[{"type":"number","display_name":"Result","cardinality":"exactly_one"}]}}))
    return load_project_workspace(root),config


def build(root,workspace,config,capsys,*,target="node"):
    status=main(["build","--workspace",str(workspace.path),"--config",str(config),"--target",target,"--profile","single-esm","--out-dir",str(root/"build")])
    payload=json.loads(capsys.readouterr().out)
    assert status==0,payload
    return Path(payload["entry"])


def run(entry,body='return runWorkflow({});'):
    code=f'import {{runWorkflow}} from {json.dumps(entry.as_uri())}; function invoke(){{{body}}} console.log(JSON.stringify(await invoke()));'
    result=subprocess.run(["node","--input-type=module","-e",code],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def test_native_declaration_checks_and_aot_execution(tmp_path,capsys):
    workspace,config=project(tmp_path)
    assert main(["validate","--workspace",str(workspace.path),"--config",str(config),"--json"])==0,capsys.readouterr().out
    capsys.readouterr()
    assert run(build(tmp_path,workspace,config,capsys))=={"number":7}


def test_shorthand_callback_keeps_helpers_and_binding(tmp_path,capsys):
    source=SOURCE.replace('export const calculation=','const offset=3;\nfunction add(value){return value+offset;}\nfunction run(inputs,params){return {result:add(4)};}\nexport const calculation=').replace('run(inputs,params){return {result:7};}','run')
    workspace,config=project(tmp_path,source)
    assert run(build(tmp_path,workspace,config,capsys))=={"number":7}


def test_preview_invokes_no_callbacks_or_lifecycle(tmp_path):
    nodes=SOURCE.replace('return {result:7};','throw Error("business invoked");')
    plugin=PLUGIN_SOURCE.replace('return {records:{},findings:[]};','throw Error("Rule invoked");').replace('id:"demo",resources:', 'id:"demo",runtime(){throw Error("runtime invoked");},resources:')
    workspace,config=project(tmp_path,nodes,plugin_source=plugin)
    assert effective_rule_plans(config,workspace=workspace)["nodes"][1]["rulesets"]==["vibeflow.process","demo.checks"]
    assert prepare_workflow_resources(workspace,config).catalogs.origins[("nodes","demo.calculate")].owner.kind=="root"


def test_plugin_removal_reports_missing_type_without_deleting_node(tmp_path):
    workspace,config=project(tmp_path,selections=[])
    with pytest.raises(ValueError,match="missing NodeType"):prepare_workflow_resources(workspace,config)
    assert (tmp_path/"nodes/steps.ts").is_file()


def test_fixed_definitions_and_parameter_isolation(tmp_path):
    workspace,config=project(tmp_path);first=prepare_workflow_resources(workspace,config)
    data=json.loads(config.read_text());data["plugins"][0]["config"]={"value":9};config.write_text(json.dumps(data))
    second=prepare_workflow_resources(workspace,config)
    assert first.catalogs.nodes.to_dict()==second.catalogs.nodes.to_dict()
    assert first.catalogs.plugin_settings["demo"]["value"]==1
    assert second.catalogs.plugin_settings["demo"]["value"]==9


@pytest.mark.parametrize("target",["node","browser"])
def test_node_only_rule_code_is_not_bundled_into_business_artifact(tmp_path,capsys,target):
    plugin='import {readFileSync} from "node:fs";\n'+PLUGIN_SOURCE.replace('return {records:{},findings:[]};',f'readFileSync({json.dumps(str(tmp_path/"package.json"))},"utf8"); return {{records:{{}},findings:[]}};')
    workspace,config=project(tmp_path,plugin_source=plugin)
    entry=build(tmp_path,workspace,config,capsys,target=target)
    text=entry.read_text();assert "readFileSync" not in text
    if target=="browser":assert "node:fs" not in text
    assert run(entry)=={"number":7}


def test_rule_effects_do_not_grant_node_permissions(tmp_path,capsys):
    workspace,config=project(tmp_path,plugin_source=PLUGIN_SOURCE.replace('return {records:{},findings:[]};','console.log("rule"); return {findings:[]};'))
    args=["validate","--workspace",str(workspace.path),"--config",str(config),"--json"]
    assert main(args)==0,capsys.readouterr().out;capsys.readouterr()
    (tmp_path/"nodes/steps.ts").write_text(SOURCE.replace('return {result:7};','console.log("node effect"); return {result:7};'))
    assert main(args)==1
    assert "VF_BASE_LIB_HOST_IO" in capsys.readouterr().out


def test_runtime_instances_are_independent_and_disposed(tmp_path,capsys):
    runtime='''runtime(context){let calls=0;return {beforeRun(){calls++;},afterRun(){if(calls!==1||context.config.value!==1||!Object.isFrozen(context.config))throw Error("shared runtime");},dispose(){if(calls!==1)throw Error("disposal");}};},'''
    workspace,config=project(tmp_path,plugin_source=PLUGIN_SOURCE.replace('id:"demo",resources:','id:"demo",'+runtime+'resources:'))
    entry=build(tmp_path,workspace,config,capsys)
    assert run(entry,'return [runWorkflow({}),runWorkflow({})];')==[{"number":7},{"number":7}]


def test_native_browser_execution(tmp_path,capsys):
    renderer=os.environ.get("VIBEFLOW_MERMAID_RENDERER_ROOT")
    if not renderer:pytest.skip("full gate supplies locked Puppeteer")
    from sandbox.javascript.integration.sandbox_support import run_browser
    workspace,config=project(tmp_path);entry=build(tmp_path,workspace,config,capsys,target="browser")
    html=tmp_path/"index.html"
    module="./"+entry.relative_to(tmp_path).as_posix()
    html.write_text(f'<!doctype html><button id="run">Run</button><output id="output"></output><script type="module">import {{runWorkflow}} from {json.dumps(module)};document.querySelector("#run").onclick=()=>{{document.querySelector("#output").textContent=String(runWorkflow({{}}).number);}};</script>')
    assert run_browser(tmp_path,puppeteer_root=Path(renderer),expected="7")["after"]=="7"
