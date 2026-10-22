"""Resource support uses explicit ownership; Plugin support belongs to its package."""
import shutil
from pathlib import Path
from .common import run_cli,row
from .js_fixtures import project,config,write,cli_args,cli_summary,check_cli

_CONTRACT='{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["Computed value"]}}'
_START='export const start=defineNode({node_type:"vibeflow.node",id:"demo.start",flow_kind:"terminal",rulesets:[],contract:{},run(){return {};}});\n'
_NUMBER='export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});\n'


def minimal(root, variant, *, registered=True):
    (root/'root_rules.jsonc').write_text('{"rulesets":["vibeflow.root.resource_usage"]}')
    config(root, lambda data: data.update(base_lib={'modules':['demo.math'] if variant in {'base_support','base_upward'} else []}))
    for name in ('nodes','base_lib','plugins'):
        shutil.rmtree(root/name)
        (root/name).mkdir()
    package=root/'plugins/demo';package.mkdir()
    imports='import {defineNode} from "@vibeflow/plugin";\n'
    model='export const model=defineNode({node_type:"vibeflow.node",id:"demo.model",rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){return {result:6};}});\n'
    plugin='import {definePlugin,defineDataSchema} from "@vibeflow/plugin";\n'+_NUMBER
    lifecycle='runtime(){return {beforeNode(){},afterNode(){},dispose(){}};},' if variant=='declaration' else ''
    if variant in {'node_support','type_support'}:
        support='implementation_files:["helper.ts"'+(',"types.d.ts"' if variant=='type_support' else '')+'],' if registered else ''
        types='import type {InputNumber} from "./types.d.ts";\n' if variant=='type_support' else ''
        model=types+'import {double} from "./helper.ts";\n'+model.replace('rulesets:[',support+'rulesets:[').replace('result:6','result:double(3)')
        (root/'nodes/helper.ts').write_text('export function double(value:number):number{return value*2;}\n')
        if types:(root/'nodes/types.d.ts').write_text('export type InputNumber=number;\n')
    elif variant=='base_support':
        support='implementation_files:["helper.ts"],' if registered else ''
        (root/'base_lib/helper.ts').write_text('export function double(value:number):number{return value*2;}\n')
        (root/'base_lib/math.ts').write_text('import {defineBaseLib} from "@vibeflow/plugin";import {double} from "./helper.ts";\nexport const library=defineBaseLib({id:"demo.math",'+support+'rulesets:["vibeflow.base_lib"],implementation(value:number):number{return double(value);}});\n')
        model='import {library} from "../base_lib/math.ts";\n'+model.replace('rulesets:[','base_libs:["demo.math"],rulesets:[').replace('result:6','result:library.implementation(3)')
    elif variant=='foreign_node':
        (root/'nodes/foreign.ts').write_text(imports+'export const foreign=defineNode({node_type:"vibeflow.node",id:"audit.foreign",rulesets:[],contract:{},run(){return {};}});\n')
        model='import {foreign} from "./foreign.ts";\n'+model.replace('return {result:6};','foreign.run({},{});return {result:6};')
    elif variant=='base_upward':
        (root/'base_lib/math.ts').write_text('import {defineBaseLib} from "@vibeflow/plugin";import {model} from "../nodes/node.ts";export const library=defineBaseLib({id:"demo.math",rulesets:["vibeflow.base_lib"],implementation(){return model.run({},{});}});\n')
        model=model.replace('rulesets:[','base_libs:["demo.math"],rulesets:[')
    elif variant=='plugin_support':
        (package/'helper.ts').write_text('export function lifecycle(){return {beforeNode(){},afterNode(){},dispose(){}};}\n')
        plugin='import {lifecycle} from "./helper.ts";\n'+plugin
        lifecycle='runtime(){return lifecycle();},'+('implementation_files:["helper.ts"],' if registered else '')
    elif variant=='declaration_lifecycle_use':
        plugin='import {model} from "../../nodes/node.ts";\n'+plugin
        lifecycle='runtime(){return model.run({},{});},'
    elif variant!='declaration':raise ValueError(variant)
    (root/'nodes/boundary.ts').write_text(imports+_START)
    (root/'nodes/node.ts').write_text(imports+model)
    (package/'plugin.ts').write_text(plugin+'export const plugin=definePlugin({id:"demo",resources:[number],'+lifecycle+'rulesets:["vibeflow.plugin"],declaration_rulesets:["vibeflow.plugin_declaration"]});\n')


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None):
    rows=[]
    for variant in ('node_support','base_support','declaration','plugin_support','type_support'):
        identifier=f'js.A05.structure.{variant}.registered';root=project(work/identifier,toolchain);minimal(root,variant)
        observed=cli_summary(run_cli(root,cli_args(root,'validate'),kernel,name='validate',toolchain=toolchain))
        rows.append(row(identifier,'A05','Declared independent support and atomic Plugin packages remain legal',{'exit_code':0},observed,check_cli(observed),root))
    for variant in ('node_support','base_support','plugin_support'):
        identifier=f'js.A05.structure.{variant}.unregistered';root=project(work/identifier,toolchain);minimal(root,variant,registered=False)
        observed=cli_summary(run_cli(root,cli_args(root,'validate'),kernel,name='validate',toolchain=toolchain))
        accepted=variant=='plugin_support'  # Package-private files need no second installation/ownership declaration.
        rows.append(row(identifier,'A05','Independent support requires declaration; Plugin support is package-owned',{'exit_code':0 if accepted else 1},observed,check_cli(observed,accepted=accepted,code=None if accepted else 'RESOURCE.REFERENCE.UNDECLARED'),root))
    for variant in ('foreign_node','base_upward','declaration_lifecycle_use'):
        identifier=f'js.A05.structure.{variant}';root=project(work/identifier,toolchain);minimal(root,variant)
        observed=cli_summary(run_cli(root,cli_args(root,'validate'),kernel,name='validate',toolchain=toolchain))
        code={'foreign_node':'RESOURCE.REFERENCE.UNDECLARED','base_upward':'RESOURCE.REFERENCE.UNDECLARED','declaration_lifecycle_use':'PLUGIN.PACKAGE.IMPORT'}[variant]
        rows.append(row(identifier,'A05','Ownership cannot grant cross-business or package-boundary imports',{'exit_code':1,'target_code':code},observed,check_cli(observed,accepted=False,code=code),root))
    return rows
