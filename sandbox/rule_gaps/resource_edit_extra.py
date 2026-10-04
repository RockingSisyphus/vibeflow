"""Changing declarations is observed by new assembly, execution and review."""
import json
from pathlib import Path

from resource_support import project,cli,replace,observe,KINDS,FILES,IDS,config,declarations
from resource_edits import execution


def mutate(root,kind,variant):
    if variant=="symbol":
        if kind=="plugin":
            replace(root,"plugin.ts","const plugin=definePlugin","const selected=definePlugin")
            config(root,lambda data:data["plugins"][0]["source"].update(export="selected"))
        else:
            name={"node":"model","base_lib":"library","host_extension":"host"}[kind]
            for path in root.glob("*.ts"):
                text=path.read_text().replace('const '+name+'=','const renamed=')
                text=text.replace('{'+name+'}', '{renamed}').replace('{'+name+',','{renamed,')
                text=text.replace(','+name+',',',renamed,').replace(','+name+']',',renamed]')
                text=text.replace(name+'.implementation','renamed.implementation')
                path.write_text(text)
    elif variant=="description":
        replace(root,FILES[kind],'presentation:{','description:"Revised implementation",presentation:{')
    elif variant=="dependency":
        if kind in {"node","host_extension"}:
            replace(root,FILES[kind],'base_libs:["demo.math"]','base_libs:[]')
        else:
            source='import {defineBaseLib} from "@vibeflow/plugin";\nexport const leaf=defineBaseLib({id:"demo.leaf",rulesets:["vibeflow.base_lib"],implementation(value:number){return value;}});\n'
            (root/"leaf.ts").write_text(source)
            plugin=root/"plugin.ts";plugin.write_text('import {leaf} from "./leaf.ts";\n'+plugin.read_text().replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,leaf]'))
            if kind=="base_lib":
                replace(root,"math.ts",'id:"demo.math",','id:"demo.math",dependencies:["demo.leaf"],')
                path=root/"math_support.ts";path.write_text('import {leaf} from "./leaf.ts";\n'+path.read_text().replace('left+right','leaf.implementation(left+right)'))
            else:
                replace(root,"plugin.ts",'id:"demo",','id:"demo",base_libs:["demo.leaf"],')
                path=root/"plugin_support.ts";path.write_text('import {leaf} from "./leaf.ts";\n'+path.read_text().replace('beforeNode(){}','beforeNode(){leaf.implementation(1);}'))
    elif kind=="node":
        replace(root,"node.ts",'contract:{provides:','contract:{params_schema:{scale:{type:"number"}},params_defaults:{scale:2},provides:')
        replace(root,"node.ts",'run(){return {result:','run(inputs,params){return {result:')
        replace(root,"node.ts",'library.implementation(2),2','library.implementation(2),Number(params.scale)')
        config(root,lambda data:data["pipeline"]["nodes"][1].update(config={"scale":3}))
    elif kind=="host_extension":
        replace(root,"host.ts",'provides:["demo.session"]','provides:["demo.session","demo.extra"]')
        replace(root,"host.ts",'capabilities:{"demo.session"','capabilities:{"demo.extra":{identity(value:number){return value;}},"demo.session"')
        path=root/"plugin.ts";path.write_text(path.read_text().replace('resources:[start,model,library,host,session,number]','resources:[start,model,library,host,session,number,extra]').replace('export const plugin=', 'export const extra=defineCapability({id:"demo.extra",targets:["node","browser"],operations:{identity:{input_type:"number",output_type:"number",completion:"immediate"}}});\nexport const plugin='))
    elif kind=="plugin":
        replace(root,"plugin.ts",'id:"demo",','id:"demo",config_schema:{revision:{type:"integer"}},config_defaults:{revision:2},')
        config(root,lambda data:data["plugins"][0].update(config={"revision":3}))


def run_cases(work,toolchain):
    rows=[]
    for kind in KINDS:
        for variant in ("symbol","description","dependency","contract"):
            if kind=="base_lib" and variant=="contract":continue
            case=f"edits.javascript.{kind}.{variant}";root=project(work/case,toolchain=toolchain)
            initial={path:path.read_text() for path in root.glob("*.ts")};original=config(root)
            before=cli(root,"validate",name="before");before_run=execution(root,kind,"before")
            mutate(root,kind,variant)
            actual=cli(root,"validate",name="modified");inspected=cli(root,"inspect-resources",name="modified-registration")
            modified_run=execution(root,kind,"modified")
            changed=next((row for row in declarations(inspected) if row.get("id",row.get("type_key"))==IDS[kind]),{})
            from common import write
            for path,text in initial.items():path.write_text(text)
            write(root/"workflow.jsonc",original)
            restored=cli(root,"validate",name="restored");restored_run=execution(root,kind,"restored")
            denied=variant=="dependency" and kind in {"node","host_extension"}
            actual["metrics"].update(before_exit=before["metrics"]["exit_code"],restored_exit=restored["metrics"]["exit_code"],
                before_run=before_run,restored_run=restored_run,registration_exit=inspected["metrics"]["exit_code"],modified_run=modified_run)
            expected={"before_exit":0,"restored_exit":0,"registration_exit":0,
                "before_run":{"build_exit":0,"runtime_exit":0,"value":6},"restored_run":{"build_exit":0,"runtime_exit":0,"value":6},
                "modified_run":{"build_exit":1 if denied else 0,"runtime_exit":None if denied else 0,"value":None if denied else 9 if kind=="node" and variant=="contract" else 6}}
            if variant=="description":
                actual["metrics"]["description"]=changed.get("description");expected["description"]="Revised implementation"
            rows.append(observe(case,"resource-edits",actual,accept=not denied,
                code=("VF_IMPORT_BASE_LIB" if kind=="node" else "VF_IMPORT_LAYER") if denied else None,metrics=expected))
    return rows
