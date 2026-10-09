"""Structure Rules must use resource ownership, not legacy directory role guesses."""
import json
from pathlib import Path

from .common import run_cli,row
from .js_fixtures import project,config,write,cli_args,cli_summary,check_cli


_CONTRACT='{provides:[{key:"result",type:"number",display_name:"Result"}],output_semantics:{result:["Computed value"]}}'
_START='export const start=defineNode({type_key:"demo.start",flow_kind:"terminal",rulesets:[],contract:{},run(){return {};}});\n'
_NUMBER='export const number=defineDataSchema({type_key:"number",schema:{type:"number"}});\n'


def minimal(root, variant, *, registered=True):
    for path in (root/"src").iterdir():path.unlink()
    config(root,lambda data:data.update(host_extensions=[]))
    imports='import {definePlugin,defineNode,defineDataSchema,defineBaseLib} from "@vibeflow/plugin";\n'
    resources='start,model,number'
    if variant in {"node_support","type_support"}:
        support='implementation_files:["helper.ts"'+(',"types.d.ts"' if variant=="type_support" else '')+'],' if registered else ''
        types='import type {InputNumber} from "./types.d.ts";\n' if variant=="type_support" else ''
        annotation=':InputNumber' if types else ':number'
        source=imports+'import {double} from "./helper.ts";\n'+types+_START+_NUMBER
        source+='export const model=defineNode({type_key:"demo.model",'+support+'rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){const value'+annotation+'=3;return {result:double(value)};}});\n'
        (root/"src/helper.ts").write_text('export function double(value:number):number{return value*2;}\n')
        if types:(root/"src/types.d.ts").write_text('export type InputNumber=number;\n')
    elif variant=="base_support":
        support='implementation_files:["helper.ts"],' if registered else ''
        (root/"src/helper.ts").write_text('export function double(value:number):number{return value*2;}\n')
        (root/"src/math.ts").write_text('import {defineBaseLib} from "@vibeflow/plugin";import {double} from "./helper.ts";\nexport const library=defineBaseLib({id:"demo.math",'+support+'rulesets:["vibeflow.base_lib"],implementation(value:number):number{return double(value);}});\n')
        source=imports+'import {library} from "./math.ts";\n'+_START+_NUMBER
        source+='export const model=defineNode({type_key:"demo.model",base_libs:["demo.math"],rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){return {result:library.implementation(3)};}});\n'
        resources+=',library'
    elif variant in {"declaration","declaration_lifecycle_use","foreign_node","base_upward"}:
        (root/"src/node.ts").write_text('import {defineNode} from "@vibeflow/plugin";\nexport const model=defineNode({type_key:"demo.model",rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){return {result:6};}});\n')
        source=imports+'import {model} from "./node.ts";\n'+_START+_NUMBER
        if variant=="foreign_node":
            (root/"src/foreign.ts").write_text('import {defineNode} from "@vibeflow/plugin";export const foreign=defineNode({type_key:"audit.foreign",rulesets:["vibeflow.process"],contract:{},run(){return {};}});\n')
            node=root/"src/node.ts";node.write_text('import {foreign} from "./foreign.ts";\n'+node.read_text().replace('return {result:6};','foreign.run({},{});return {result:6};'))
            source='import {foreign} from "./foreign.ts";\n'+source;resources+=',foreign'
        elif variant=="base_upward":
            (root/"src/math.ts").write_text('import {defineBaseLib} from "@vibeflow/plugin";import {model} from "./node.ts";export const library=defineBaseLib({id:"demo.math",rulesets:["vibeflow.base_lib"],implementation(){return model.run({},{});}});\n')
            source='import {library} from "./math.ts";\n'+source;resources+=',library'
            # A selected source with an upward edge, without a recursive execution path.
            model=root/"src/node.ts";model.write_text(model.read_text().replace('rulesets:["vibeflow.process"]','base_libs:["demo.math"],rulesets:["vibeflow.process"]'))
    elif variant=="host_support":
        (root/"src/host.ts").write_text('import {defineHostExtension} from "@vibeflow/plugin";import {session} from "./helper.ts";export const host=defineHostExtension({id:"audit.host",targets:["node","browser"],provides:[],'+('implementation_files:["helper.ts"],' if registered else '')+'rulesets:["vibeflow.host_extension"],createHost(){return session();}});\n')
        (root/"src/helper.ts").write_text('export function session(){return {start(){},stop(){}};}\n')
        source=imports+'import {host} from "./host.ts";\n'+_START+_NUMBER+'export const model=defineNode({type_key:"demo.model",rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){return {result:6};}});\n'
        resources+=',host';config(root,lambda data:data.update(host_extensions=[{"id":"audit.host"}]))
    elif variant=="plugin_support":
        (root/"src/helper.ts").write_text('export function lifecycle(){return {beforeNode(){},afterNode(){},dispose(){}};}\n')
        source=imports+'import {lifecycle} from "./helper.ts";\n'+_START+_NUMBER+'export const model=defineNode({type_key:"demo.model",rulesets:["vibeflow.process"],contract:'+_CONTRACT+',run(){return {result:6};}});\n'
    else:raise ValueError(variant)
    lifecycle='runtime(){return lifecycle();},'+('implementation_files:["helper.ts"],' if registered else '') if variant=="plugin_support" else 'runtime(){return {beforeNode(){},afterNode(){},dispose(){}};},' if variant=="declaration" else 'runtime(){return model.run({},{});},' if variant=="declaration_lifecycle_use" else ''
    lifecycle_rules='[]' if variant=="declaration_lifecycle_use" else '["vibeflow.plugin"]'
    source+='export const plugin=definePlugin({id:"demo",resources:['+resources+'],'+lifecycle+'rulesets:'+lifecycle_rules+',declaration_rulesets:["vibeflow.plugin_declaration"]});\n'
    (root/"src/plugin.ts").write_text(source)


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None):
    rows=[]
    for variant in ("node_support","base_support","declaration","host_support","plugin_support","type_support"):
        identifier=f"js.A05.structure.{variant}.registered";root=project(work/identifier,toolchain);minimal(root,variant)
        observed=cli_summary(run_cli(root,cli_args(root,"quality-check","--config",root/"workflow.jsonc"),kernel,name="quality",toolchain=toolchain))
        failures=check_cli(observed)
        rows.append(row(identifier,"A05","Registered resource support and plugin contributions remain legal in project quality",
            {"exit_code":0},observed,failures,root))
    for variant in ("node_support","base_support","host_support","plugin_support"):
        identifier=f"js.A05.structure.{variant}.unregistered";root=project(work/identifier,toolchain);minimal(root,variant,registered=False)
        observed=cli_summary(run_cli(root,cli_args(root,"validate"),kernel,name="validate",toolchain=toolchain))
        failures=check_cli(observed,accepted=False,code="VF_IMPORT_OWNER")
        rows.append(row(identifier,"A05","Removing support registration is rejected by the selected resource import Rule",
            {"exit_code":1,"target_code":"VF_IMPORT_OWNER"},observed,failures,root))
    for variant in ("foreign_node","base_upward"):
        identifier=f"js.A05.structure.{variant}";root=project(work/identifier,toolchain);minimal(root,variant)
        observed=cli_summary(run_cli(root,cli_args(root,"validate"),kernel,name="validate",toolchain=toolchain))
        target_code="VF_IMPORT_NODE_TO_NODE" if variant=="foreign_node" else "VF_IMPORT_LAYER"
        failures=check_cli(observed,accepted=False,code=target_code)
        rows.append(row(identifier,"A05","Business Node edges and BaseLib upward imports are not resource support permissions",
            {"exit_code":1,"target_code":target_code},observed,failures,root))
    identifier="js.A05.structure.declaration_lifecycle_use";root=project(work/identifier,toolchain);minimal(root,"declaration_lifecycle_use")
    observed=cli_summary(run_cli(root,cli_args(root,"quality-check","--config",root/"workflow.jsonc"),kernel,name="quality",toolchain=toolchain))
    failures=check_cli(observed,accepted=False,code="QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT")
    rows.append(row(identifier,"A05","A contribution import does not grant the lifecycle factory permission to call its Node",
        {"exit_code":1,"target_code":"QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT"},observed,failures,root))
    return rows
