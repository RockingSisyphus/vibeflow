"""Entry-specific preprocessing, contracts, shared joins and TypeScript callers."""
import json
import sys

import pytest

from .host_projects import javascript_project
from .support import ROOT, cli, command, workspace, write


PYTHON='''from vibeflow.targets.python.sdk import node
@node(id="entry.boundary",node_type="vibeflow.node",flow_kind="terminal",rulesets=[],contract={})
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(id="entry.cli",node_type="vibeflow.node",rulesets=[],contract={"input_semantics":{"string":["Selected entry input"]},"requires":[{"type":"string","cardinality":"exactly_one","display_name":"Text"}],"output_semantics":{"seed":["Selected seed"]},"provides":[{"key":"seed","type":"seed","display_name":"Seed"}]})
class CLI:
    def run_pure(self,inputs,params):
        print("entered CLI")
        return {"seed":int(inputs["string"]["value"])}
@node(id="entry.gui",node_type="vibeflow.node",rulesets=[],contract={"input_semantics":{"number":["Selected entry input"]},"requires":[{"type":"number","cardinality":"exactly_one","display_name":"Number"}],"output_semantics":{"seed":["Selected seed"]},"provides":[{"key":"seed","type":"seed","display_name":"Seed"}]})
class GUI:
    def run_pure(self,inputs,params):
        print("entered GUI")
        return {"seed":inputs["number"]["value"]}
@node(id="entry.core",node_type="vibeflow.node",rulesets=[],contract={"input_semantics":{"seed":["Selected entry input"]},"requires":[{"type":"seed","cardinality":"exactly_one","display_name":"Seed"}],"output_semantics":{"answer":["Doubled seed"]},"provides":[{"key":"answer","type":"number","display_name":"Answer"}]})
class Core:
    def run_pure(self,inputs,params):return {"answer":inputs["seed"]["value"]*2}
'''
JAVASCRIPT='''import {defineNode} from "@vibeflow/plugin";
export const boundary=defineNode({id:"entry.boundary",node_type:"vibeflow.node",flow_kind:"terminal",rulesets:[],contract:{},run(){return {};}});
export const cli=defineNode({id:"entry.cli",node_type:"vibeflow.node",rulesets:[],contract:{input_semantics:{"string":["Selected entry input"]},requires:[{type:"string",cardinality:"exactly_one",display_name:"Text"}],output_semantics:{seed:["Selected seed"]},provides:[{key:"seed",type:"seed",display_name:"Seed"}]},run(inputs){console.log("entered CLI");return {seed:Number(inputs.string.value)};}});
export const gui=defineNode({id:"entry.gui",node_type:"vibeflow.node",rulesets:[],contract:{input_semantics:{"number":["Selected entry input"]},requires:[{type:"number",cardinality:"exactly_one",display_name:"Number"}],output_semantics:{seed:["Selected seed"]},provides:[{key:"seed",type:"seed",display_name:"Seed"}]},run(inputs){console.log("entered GUI");return {seed:inputs.number.value};}});
export const core=defineNode({id:"entry.core",node_type:"vibeflow.node",rulesets:[],contract:{input_semantics:{"seed":["Selected entry input"]},requires:[{type:"seed",cardinality:"exactly_one",display_name:"Seed"}],output_semantics:{answer:["Doubled seed"]},provides:[{key:"answer",type:"number",display_name:"Answer"}]},run(inputs){return {answer:inputs.seed.value*2};}});
'''


@pytest.fixture(scope="module")
def entry_project(tmp_path_factory,toolchain,request):
    root=tmp_path_factory.mktemp("named-entries")
    language=request.param
    if language=="python":
        app=workspace(root,PYTHON,plugin='''from vibeflow.targets.python.sdk import Plugin,data_schema
plugin=Plugin(id="entries",resources=[data_schema(type_key=key,schema={"type":kind}) for key,kind in [("number","number"),("string","string"),("seed","number")]])
''')
        workspace_path=root / "vibeflow_config.jsonc";plugin="plugins/example/plugin.py"
    else:
        app=root / "app"
        workspace_path,_=javascript_project(app,JAVASCRIPT,'''import {definePlugin,defineDataSchema} from "@vibeflow/plugin";
export const plugin=definePlugin({id:"entries",resources:[["number","number"],["string","string"],["seed","number"]].map(([type_key,type])=>defineDataSchema({type_key,schema:{type}}))});
''');plugin="plugins/demo/plugin.ts"
    nodes=[{"id":name,"definition_id":"entry."+("boundary" if name in {"cli_start","gui_start","end"} else name),
        "display_name":name,"description":"Named entry "+name,**({"join_policy":"all"} if name=="core" else {})}
        for name in ("cli_start","gui_start","cli","gui","core","end")]
    entries={name:{"start":name+"_start","inputs":[{"key":key,"type":kind,"required":True,"display_name":key}],
        "outputs":[{"type":"number","as":name+"_answer","cardinality":"exactly_one","display_name":"Answer"}]}
        for name,key,kind in (("cli","text","string"),("gui","value","number"))}
    config=write(app / "configs/main.jsonc",{"plugins":[{"source":{"kind":"file","ref":plugin}}],"rulesets":[],"pipeline":{
        "nodes":nodes,"edges":[[a,b] for a,b in (("cli_start","cli"),("gui_start","gui"),("cli","core"),("gui","core"),("core","end"))],
        "entries":entries,"entry_mode":"async" if language=="javascript-async" else "sync"}})
    args=["build","--workspace",workspace_path,"--config",config,"--out-dir",root / "bundle"]
    if language.startswith("javascript"):args += ["--target","node","--profile","esm-module"]
    result=cli(root,*args)
    return language,root,config,json.loads(result.stdout)


@pytest.mark.parametrize("name,initial,expected",[("cli",{"text":"7"},14),("gui",{"value":3},6)])
@pytest.mark.parametrize("entry_project",["python","javascript","javascript-async"],indirect=True)
def test_named_entry_runs_only_its_selected_path(entry_project,tmp_path,name,initial,expected):
    language,root,config,built=entry_project
    request=write(tmp_path / "request.json",{"entry":name,"initial":initial,"options":{"entry":name},
        "mode":"async" if language=="javascript-async" else "sync"})
    if language=="python":
        result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",root / "bundle",request,
            tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None},timeout=20)
        output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["outputs"]
    else:
        result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",built["entry"],request,cwd=tmp_path,timeout=20)
        output=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
    assert output=={name+"_answer":expected}
    assert "entered "+name.upper() in result.stdout
    assert "entered "+("GUI" if name=="cli" else "CLI") not in result.stdout


@pytest.mark.parametrize("entry_project",["python","javascript","javascript-async"],indirect=True)
def test_named_entry_contract_errors_are_specific(entry_project,tmp_path):
    language,root,config,built=entry_project
    for selection,initial,needle in ((None,{"text":"7"},"select a workflow entry"),("gui",{},"required"),
        ("gui",{"text":"7"},"unknown")):
        request=write(tmp_path / "request.json",{"entry":selection,"initial":initial,"options":{"entry":selection},
            "mode":"async" if language=="javascript-async" else "sync"})
        if language=="python":
            result=command(sys.executable,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",root / "bundle",request,
                tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None},success=False)
        else:result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",built["entry"],request,cwd=tmp_path,success=False)
        assert result.returncode!=0 and needle in (result.stdout+result.stderr).lower(),result.stdout+result.stderr


@pytest.mark.parametrize("entry_project",["javascript","javascript-async"],indirect=True)
def test_javascript_entry_schema_value_rejection(entry_project,tmp_path):
    language,root,config,built=entry_project
    request=write(tmp_path / "request.json",{"initial":{"value":"bad"},"options":{"entry":"gui"},
        "mode":"async" if language=="javascript-async" else "sync"})
    result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",built["entry"],request,cwd=tmp_path,success=False)
    payload=json.loads(next(line[8:] for line in result.stdout.splitlines() if line.startswith("FAILURE ")))
    assert result.returncode==1 and payload["code"]=="VF_INPUT_SCHEMA",payload


@pytest.mark.parametrize("entry_project",["javascript"],indirect=True)
def test_generated_typescript_contract_accepts_good_and_rejects_wrong_callers(entry_project,toolchain,tmp_path):
    language,root,config,built=entry_project
    write(root / "package.json",{"type":"module"})
    source=write(root / "use.mts",'''
import {runWorkflow} from './bundle/workflow.js';
const a:number=runWorkflow({text:"7"},{entry:"cli"}).cli_answer;
const b:number=runWorkflow({value:3},{entry:"gui"}).gui_answer;
// @ts-expect-error wrong selected input contract
runWorkflow({text:"7"},{entry:"gui"});
// @ts-expect-error missing entry selection
runWorkflow({text:"7"});
// @ts-expect-error wrong selected output alias
runWorkflow({value:3},{entry:"gui"}).cli_answer;
''')
    command("node",toolchain / "node_modules/typescript/bin/tsc","--strict","--noEmit","--target","es2022","--module","nodenext",source,cwd=root)
