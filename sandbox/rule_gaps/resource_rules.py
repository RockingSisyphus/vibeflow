"""Rules compose independently of Node/Host/Plugin execution identities."""
import json

from resource_support import project,cli,replace,observe,KINDS,FILES,PARTS


def definitions(root,kind,variant):
    path=root/"plugin.ts"
    if variant=="empty":
        replace(root,FILES[kind],'rulesets:["vibeflow.'+{"node":"process","base_lib":"base_lib","plugin":"plugin","host_extension":"host_extension"}[kind]+'"]','rulesets:[]')
        return
    marker=str(root/"consumer.marker")
    source='import {defineRule,defineRuleset} from "@vibeflow/plugin";\nimport {writeFileSync} from "node:fs";\n'
    provider_state='"failed"' if variant=="failed_provider" else '"completed"'
    provider_findings='[{rule_id:"DEMO.PROVIDER",severity:"error",file:context.facts.source_files[0],line:1,message:"provider diagnostic"}]' if variant in {"error_records","failed_provider"} else '[]'
    source+='export const provider=defineRule({id:"demo.provider",outputs:{value:"demo.value"},check(context){return {state:'+provider_state+',records:{value:{type_id:"demo.value",value:[]}},findings:'+provider_findings+'};}});\n'
    check='return {findings:[]};'
    if variant=="custom_fail":check='return {findings:[{rule_id:"DEMO.SUPPORT",severity:"error",file:context.facts.source_files.find(file=>file.endsWith('+json.dumps(PARTS[kind])+')),line:1,message:"registered support rejected"}]};'
    if variant=="parameter_override":check='if(params.limit!==2)throw Error("wrong effective parameter");return {findings:[]};'
    source+='export const checker=defineRule({id:"demo.checker",params_schema:{limit:{type:"integer"}},params_defaults:{limit:1},check(context,inputs,params){'+check+'}});\n'
    source+='export const consumer=defineRule({id:"demo.consumer",inputs:{input:"demo.value"},check(context,inputs){writeFileSync('+json.dumps(marker)+',JSON.stringify(inputs.input.value));return {findings:[]};}});\n'
    calls=[{"id":"check","rule_id":"demo.checker"}];relations=[];entry=["check"]
    if variant in {"requires","error_records","failed_provider"}:
        calls=[{"id":"provider","rule_id":"demo.provider"},{"id":"consumer","rule_id":"demo.consumer"}]
        relations=[{"kind":"requires","source":"consumer","target":"provider","bindings":{"input":"value"}}];entry=["consumer"]
    elif variant in {"parameter_override","implementation_override"}:
        relations=[{"kind":"overrides","source":"$self","target":"check",**({"params":{"limit":2}} if variant=="parameter_override" else {"replace_rule":"demo.replacement"})}]
        source+='export const replacement=defineRule({id:"demo.replacement",params_schema:{limit:{type:"integer"}},params_defaults:{limit:2},check(){return {findings:[]};}});\n'
    source+='export const checks=defineRuleset('+json.dumps({"id":"demo.checks","calls":calls,"relations":relations,"entrypoints":{"static":entry}})+');\n'
    if variant=="nested":
        source+='export const outer=defineRuleset({id:"demo.outer",calls:[{id:"nested",ruleset_id:"demo.checks"}],entrypoints:{static:["nested"]}});\n'
    resource_names='provider,checker,consumer,checks'+(',replacement' if variant in {"parameter_override","implementation_override"} else '')+(',outer' if variant=="nested" else '')
    text=path.read_text();text=source+text.replace('resources:[start,model,library,host,session,number]',f'resources:[start,model,library,host,session,number,{resource_names}]')
    path.write_text(text)
    selection="demo.outer" if variant=="nested" else "demo.checks"
    replace(root,FILES[kind],'rulesets:["vibeflow.'+{"node":"process","base_lib":"base_lib","plugin":"plugin","host_extension":"host_extension"}[kind]+'"]','rulesets:["'+selection+'"]')


def run_cases(work,toolchain):
    rows=[]
    variants=("empty","custom_pass","custom_fail","nested","requires","error_records","failed_provider","parameter_override","implementation_override")
    for kind in KINDS:
        for variant in variants:
            case=f"rules.javascript.{kind}.{variant}";root=project(work/case,toolchain=toolchain)
            definitions(root,kind,variant)
            actual=cli(root,"validate",name="validate")
            invoked=(root/"consumer.marker").exists()
            actual["metrics"]["consumer_called"]=invoked
            code="DEMO.SUPPORT" if variant=="custom_fail" else "DEMO.PROVIDER" if variant in {"error_records","failed_provider"} else None
            rows.append(observe(case,"resource-rules",actual,accept=code is None,code=code,
                metrics={"consumer_called":variant in {"requires","error_records"}}))
    from resource_sdk_extra import run_cases as sdk_cases
    rows.extend(sdk_cases(work,toolchain))
    return rows
