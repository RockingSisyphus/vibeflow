"""Named entry variants use the existing generated scheduler."""
from dataclasses import replace

import pytest

from tests.targets.javascript.aot_fixtures import plan_fixture
from tests.targets.javascript.test_aot_core import _linear_plan, _node, _provider, _requirement, _run_esm
from vibeflow.block_compiler.model import WorkflowEntryPlan
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module


@pytest.mark.parametrize("mode", ["sync", "async"])
def test_named_entries_use_shared_core_without_other_entry_or_join_wait(tmp_path, mode):
    description = _linear_plan(middle=_node("middle", "middle", requires=[_requirement("number")],
        provides=[_provider("out", "answer")], join_policy="all"), entry_mode=mode)
    description["nodes"].append(_node("gui", "gui", terminal=True))
    description["routes"].append({"source": "gui", "target": "middle"})
    description["order"].insert(1, "gui")
    plan, bindings = plan_fixture(description)
    entries = tuple(WorkflowEntryPlan(name, start, (start, "middle", "end"), plan.inputs, plan.outputs)
                    for name, start in [("cli", "start"), ("gui", "gui")])
    plan = replace(plan, named_entries=entries)
    (tmp_path / "nodes.mjs").write_text('''
export function start(){globalThis.__vfCalls.push("cli");return {};}
export function gui(){globalThis.__vfCalls.push("gui");return {};}
export function middle(inputs){return {out:inputs.number.value*2};}
export function end(){return {};}
''')
    emitted = emit_workflow_module(plan, javascript_bindings=bindings)
    assert 'WorkflowEntryInputs' in emitted.declarations
    assert 'readonly entry: E' in emitted.declarations
    assert emitted.source.count('case "middle":') == 1
    path = tmp_path / "workflow.mjs"
    path.write_text(emitted.source)
    function = "runWorkflow" if mode == "sync" else "runWorkflowAsync"
    result = _run_esm(path, f'''
let missing=false;
try {{await workflow.{function}({{number:21}});}}catch(error){{missing=error.message.includes("select a workflow entry");}}
const first=await workflow.{function}({{number:21}},{{entry:"cli"}});
const second=await workflow.{function}({{number:3}},{{entry:"gui"}});
console.log(JSON.stringify({{missing,first,second,calls:globalThis.__vfCalls}}));
''')
    assert result == {"missing": True, "first": {"answer": 42}, "second": {"answer": 6}, "calls": ["cli", "gui"]}


def test_entry_contracts_select_inputs_outputs_and_types_without_common_code_duplication(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    from vibeflow.block_compiler.model import PipelineInputSpec, PipelineOutputSpec
    description = {"workflow_id":"contracts","entry_mode":"sync","schemas":{"number":{"type":"number"},"string":{"type":"string"},"seed":{"type":"number"}},
        "nodes":[_node(key,key,terminal=key in {"cli_start","gui_start","end"},
            requires=[_requirement(kind)] if kind else [],provides=[_provider("seed","seed")] if key in {"cli","gui"} else [_provider("answer","number")] if key=="core" else [])
            for key,kind in [("cli_start",None),("gui_start",None),("cli","string"),("gui","number"),("core","seed"),("end",None)]],
        "routes":[{"source":a,"target":b} for a,b in [("cli_start","cli"),("gui_start","gui"),("cli","core"),("gui","core"),("core","end")]],
        "order":["cli_start","gui_start","cli","gui","core","end"]}
    plan,bindings = plan_fixture(description)
    entries = tuple(WorkflowEntryPlan(name,name+"_start",(name+"_start",name,"core","end"),
        (PipelineInputSpec(key,kind,True),),(PipelineOutputSpec("number","exactly_one",name+"_answer"),))
        for name,key,kind in [("cli","text","string"),("gui","value","number")])
    plan = replace(plan,named_entries=entries)
    emitted=emit_workflow_module(plan,javascript_bindings=bindings)
    (tmp_path/"workflow.mjs").write_text(emitted.source)
    (tmp_path/"workflow.d.mts").write_text(emitted.declarations)
    (tmp_path/"nodes.mjs").write_text('''
export function cli_start(){return {};};export function gui_start(){return {};};export function end(){return {};};
export function cli(inputs){return {seed:Number(inputs.string.value)};};
export function gui(inputs){return {seed:inputs.number.value};};
export function core(inputs){return {answer:inputs.seed.value*2};};
''')
    assert _run_esm(tmp_path/"workflow.mjs",'''
console.log(JSON.stringify([workflow.runWorkflow({text:"7"},{entry:"cli"}),workflow.runWorkflow({value:3},{entry:"gui"})]));
''') == [{"cli_answer":14},{"gui_answer":6}]
    (tmp_path/"use.mts").write_text('''
import {runWorkflow} from './workflow.mjs';
const a:number=runWorkflow({text:"7"},{entry:"cli"}).cli_answer;
const b:number=runWorkflow({value:3},{entry:"gui"}).gui_answer;
// @ts-expect-error wrong selected input contract
runWorkflow({text:"7"},{entry:"gui"});
// @ts-expect-error missing entry selection
runWorkflow({text:"7"});
// @ts-expect-error wrong selected output alias
runWorkflow({value:3},{entry:"gui"}).cli_answer;
''')
    tsc=Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])/"node_modules/typescript/bin/tsc"
    result=subprocess.run(["node",str(tsc),"--strict","--noEmit","--target","es2022","--module","nodenext",str(tmp_path/"use.mts")],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
