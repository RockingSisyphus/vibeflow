"""Host native dependency closure must be fixed before Rule scope and binding."""
import json
from pathlib import Path

from .common import run_cli, run_command, row
from .js_fixtures import project, edit, config, cli_args, cli_summary, check_cli
from .js_lifecycle import _build


def child(root, *, lines=20, rules=True, dependency=True, second_file=False):
    marker=json.dumps(str(root/"host-events.jsonl"))
    source='import {defineHostExtension} from "@vibeflow/plugin";import {appendFileSync} from "node:fs";\n'
    source+='export const child=defineHostExtension({id:"audit.child",targets:["node","browser"],provides:[],implementation_files:["child_support.ts"'+(',"child_second.ts"' if second_file else '')+'],rulesets:'+('["vibeflow.host_extension"]' if rules else '[]')+',createHost(){appendFileSync('+marker+',JSON.stringify({event:"child-create"})+"\\n");return {start(){appendFileSync('+marker+',JSON.stringify({event:"child-start"})+"\\n");},stop(){appendFileSync('+marker+',JSON.stringify({event:"child-stop"})+"\\n");}};}});\n'
    (root/"src/child.ts").write_text(source)
    (root/"src/child_support.ts").write_text("// Registered child implementation line\n"*lines)
    if second_file:(root/"src/child_second.ts").write_text("// Independent registered implementation line\n"*lines)
    path=root/"src/plugin.ts";text=path.read_text()
    text='import {child} from "./child.ts";\n'+text
    text=text.replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,child]')
    path.write_text(text)
    if dependency:edit(root/"src/host.ts",'id:"demo.host",','id:"demo.host",dependencies:["audit.child"],')


def _host_execution(root,kernel,built,toolchain):
    entry=(built.get("payload") or {}).get("entry")
    if not entry:return {"exit_code":None,"number":None,"events":[]}
    script='const workflow=await import('+json.dumps(Path(entry).as_uri())+');let result;if(typeof workflow.createWorkflowHost==="function"){const host=workflow.createWorkflowHost();await host.start();result=await host.runWorkflow({});await host.stop();}else{result=await workflow.runWorkflow({});}console.log(JSON.stringify(result));'
    run=run_command(root,["node","--input-type=module","--eval",script],kernel,name="host-run",toolchain=toolchain)
    marker=root/"host-events.jsonl"
    events=[json.loads(line)["event"] for line in marker.read_text().splitlines()] if marker.exists() else []
    return {"exit_code":run["exit_code"],"number":(run.get("payload") or {}).get("number"),"events":events}


def health_cases(work,kernel,toolchain):
    rows=[]
    for variant,command in (("child501","validate"),("child501","build"),("explicit501","build"),
            ("child500","validate"),("child500","build"),("two300","build"),("unconstrained501","build"),("unselected501","validate")):
        identifier=f"js.A10.health.{variant}.{command}";root=project(work/identifier,toolchain)
        lines=500 if variant=="child500" else 300 if variant=="two300" else 501
        child(root,lines=lines,rules=variant!="unconstrained501",dependency=variant!="unselected501",second_file=variant=="two300")
        if variant=="explicit501":config(root,lambda data:data["host_extensions"].append({"id":"audit.child"}))
        result=_build(root,kernel,toolchain) if command=="build" else run_cli(root,cli_args(root,command),kernel,name=command,toolchain=toolchain)
        observed=cli_summary(result);accepted=variant not in {"child501","explicit501"}
        failures=check_cli(observed,accepted=accepted,code="BASE_LIB.SOURCE.MAX_LINES" if not accepted else None,owner="audit.child" if not accepted else None)
        if not accepted:
            target=[item for item in observed["diagnostics"] if item.get("code")=="BASE_LIB.SOURCE.MAX_LINES"]
            if target and not any(Path(item["source_location"]["path"]).name=="child_support.ts" and item["source_location"].get("line")==1 for item in target):
                failures.append("size failure must point to child support file line 1")
        if command=="build" and accepted:
            observed["native"]=_host_execution(root,kernel,result,toolchain)
            expected_native={"exit_code":0,"number":6,"events":["child-create","child-start","child-stop"]}
            if observed["native"]!=expected_native:failures.append(f"single native child lifecycle changed: {observed['native']}")
        rows.append(row(identifier,"A10","Every active Host dependency applies its own per-file Ruleset before AOT",
            {"exit_code":0 if accepted else 1},observed,failures,root))
    identifier="js.A10.preview.dependency_rules";root=project(work/identifier,toolchain);child(root,lines=501)
    result=run_cli(root,cli_args(root,"review-rules"),kernel,name="preview",toolchain=toolchain)
    observed=cli_summary(result);text=json.dumps(observed["payload"])
    observed["child_visible"]="audit.child" in text and "vibeflow.host_extension" in text
    observed["factory_called"]=(root/"host-events.jsonl").exists()
    failures=check_cli(observed,require_status=False)
    if not observed["child_visible"]:failures.append("preview must include dependency Host and its effective selected Ruleset")
    if observed["factory_called"]:failures.append("preview must not create any Host instance")
    rows.append(row(identifier,"A10","Rule preview shares active Host closure without executing factories",
        {"exit_code":0,"child_visible":True,"factory_called":False},observed,failures,root))
    return rows


def state_cases(work,kernel,toolchain):
    rows=[]
    variants=("disabled_dependency","disabled_planned_dependency","planned_dependency","planned_only","unknown_dependency","cycle","shared_dependency")
    for variant in variants:
        identifier=f"js.A10.state.{variant}";root=project(work/identifier,toolchain)
        child(root,dependency=variant!="planned_only")
        if variant in {"disabled_dependency","disabled_planned_dependency"}:
            config(root,lambda data:data["host_extensions"].append({"id":"audit.child","enabled":False,**({"status":"planned"} if variant=="disabled_planned_dependency" else {})}))
        elif variant=="planned_dependency":config(root,lambda data:data["host_extensions"].append({"id":"audit.child","status":"planned"}))
        elif variant=="planned_only":config(root,lambda data:data.update(host_extensions=[{"id":"audit.child","status":"planned"}]))
        elif variant=="unknown_dependency":edit(root/"src/host.ts",'dependencies:["audit.child"]','dependencies:["audit.missing"]')
        elif variant=="cycle":edit(root/"src/child.ts",'id:"audit.child",','id:"audit.child",dependencies:["demo.host"],')
        elif variant=="shared_dependency":
            path=root/"src/child.ts";path.write_text(path.read_text()+'export const other=defineHostExtension({id:"audit.other",targets:["node","browser"],provides:[],dependencies:["audit.child"],rulesets:["vibeflow.host_extension"],createHost(){return {start(){},stop(){}};}});\n')
            edit(root/"src/plugin.ts",'import {child}','import {child,other}')
            edit(root/"src/plugin.ts",'session,number,child]','session,number,child,other]')
            config(root,lambda data:data["host_extensions"].append({"id":"audit.other"}))
        result=_build(root,kernel,toolchain);observed=cli_summary(result)
        accepted=variant not in {"planned_dependency","unknown_dependency","cycle"}
        failures=check_cli(observed,accepted=accepted)
        expected_code={"planned_dependency":"VF_AOT_HOST_EXTENSION_PLANNED_DEPENDENCY","unknown_dependency":"VF_AOT_HOST_EXTENSION_UNKNOWN","cycle":"VF_AOT_HOST_EXTENSION_CYCLE"}.get(variant)
        if not accepted and observed.get("code")!=expected_code:failures.append(f"native invalid dependency must retain {expected_code}")
        if accepted:
            observed["native"]=_host_execution(root,kernel,result,toolchain)
            expected_events=[] if variant=="planned_only" else ["child-create","child-start","child-stop"]
            expected={"exit_code":0,"number":6,"events":expected_events}
            if observed["native"]!=expected:failures.append(f"native status/closure behavior changed: {observed['native']}")
        rows.append(row(identifier,"A10","Native planned/disabled/dependency behavior stays explicit and instance-deduplicated",
            {"exit_code":0 if accepted else 1},observed,failures,root))
    return rows


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None):
    return [*health_cases(work,kernel,toolchain),*state_cases(work,kernel,toolchain)]
