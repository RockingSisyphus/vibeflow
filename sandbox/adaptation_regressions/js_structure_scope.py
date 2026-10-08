"""Initialization and erased-type imports keep explicit source ownership."""
from pathlib import Path
from .common import run_cli,row
from .js_fixtures import project,cli_args,cli_summary,check_cli
from .js_structure import minimal,_CONTRACT


def fixture(root,variant,registered):
    minimal(root,'declaration')
    plugin=root/'src/plugin.ts';plugin.write_text(plugin.read_text().replace('declaration_rulesets:["vibeflow.plugin_declaration"]','declaration_rulesets:[]').replace('runtime(){return {beforeNode(){},afterNode(){},dispose(){}};},','').replace('rulesets:["vibeflow.plugin"]','rulesets:[]'))
    helper=root/'src/helper.ts';helper.write_text('export const value=1;\nexport type Input=Record<string,unknown>;\n')
    imported='import {value} from "./helper.ts";\n'
    prefix=''
    method='run(){return {result:6};}'
    if variant=='top_void':prefix='void value;\n'
    elif variant=='top_const':prefix='const snapshot=value;\n'
    elif variant=='direct_type':
        imported='import type {Input} from "./helper.ts";\n'
        method='run(inputs:Input){return {result:6};}'
    elif variant=='alias_type':
        imported='import type {Input} from "./helper.ts";\n';prefix='type Local=Input;\n'
        method='run(inputs:Local){return {result:6};}'
    elif variant=='side_effect':imported='import "./helper.ts";\n'
    elif variant in {'method_called','method_unused'}:
        prefix='const tools={read(){return value;}};\n'+('tools.read();\n' if variant=='method_called' else '')
    elif variant in {'constructor_called','constructor_unused'}:
        prefix='class Holder{constructor(){void value;}}\n'+('new Holder();\n' if variant=='constructor_called' else '')
    elif variant=='symbol_isolation':
        helper.write_text('export function value(){return 6;}\n')
        (root/'src/right.ts').write_text('export function right(){return 7;}\n')
        imported='import {value} from "./helper.ts";\nimport {right} from "./right.ts";\n'
        method='run(){return {result:value()};}'
    else:raise ValueError(variant)
    support='implementation_files:["helper.ts"],' if registered else ''
    text='import {defineNode} from "@vibeflow/plugin";\n'+imported+prefix+'export const model=defineNode({type_key:"demo.model",'+support+'rulesets:[],contract:'+_CONTRACT+','+method+'});\n'
    if variant=='symbol_isolation':
        text+='export const rightModel=defineNode({type_key:"audit.right",implementation_files:["right.ts"],rulesets:[],contract:'+_CONTRACT+',run(){return {result:right()};}});\n'
        plugin.write_text(plugin.read_text().replace('import {model}', 'import {model,rightModel}').replace('resources:[start,model,number]', 'resources:[start,model,rightModel,number]'))
    (root/'src/node.ts').write_text(text)


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None)->list[dict]:
    rows=[]
    for variant in ('top_void','top_const','direct_type','alias_type','side_effect','symbol_isolation','method_called','method_unused','constructor_called','constructor_unused'):
        for registered in (True,False):
            identifier=f'js.A05.scope.{variant}.{"registered" if registered else "unregistered"}'
            root=project(work/identifier,toolchain);fixture(root,variant,registered)
            actual=cli_summary(run_cli(root,cli_args(root,'quality-check','--config',root/'workflow.jsonc'),kernel,name='quality',toolchain=toolchain))
            target='QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT'
            findings=[item for item in actual['diagnostics'] if item.get('code',item.get('rule_id'))==target]
            actual['target_findings']=findings
            accepted=registered or variant in {'method_unused','constructor_unused'}
            failures=check_cli(actual,accepted=accepted,code=None if accepted else target)
            if not accepted and not any((item.get('details',{}).get('resource_id')=='demo.model' and item.get('source_location',{}).get('line')==2) for item in findings):failures.append('target finding must retain the selected model owner and real import line 2')
            if variant=='symbol_isolation' and any(item.get('details',{}).get('resource_id')=='audit.right' for item in findings):failures.append('right symbol must not inherit left symbol import restrictions')
            expected={'exit_code':0 if accepted else 1}
            rows.append(row(identifier,'A05','Source ownership covers initialization and type edges without merging symbol permissions',expected,actual,failures,root))
    return rows
