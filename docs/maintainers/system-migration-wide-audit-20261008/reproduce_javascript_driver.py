import json, shutil, tempfile, sys
from pathlib import Path
from dataclasses import replace
ROOT=Path('/home/rockingsisyphus/projects/VibeFlow')
sys.path.insert(0,str(ROOT/'src'))
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest,prepare_project_build
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest,audit_javascript_project
from vibeflow.targets.javascript.build.toolchain import run_rule_check_driver
from vibeflow.targets.javascript.quality.builtin_plugin import javascript_rule_bindings
from vibeflow.core.rules import RuleContext

taskroot=Path(tempfile.mkdtemp(prefix='vibeflow-wide-js-',dir='/tmp'))
example=taskroot/'domain'
shutil.copytree(ROOT/'sandbox/javascript/domain_rules',example)
project=example/'project'
(project/'node_modules').symlink_to(Path('/tmp/vibeflow-s01-s04-independent-tests/javascript-toolchain/node_modules'),target_is_directory=True)
workspace=example/'vibeflow_config.jsonc'; config=project/'configs/model.jsonc'
original=json.loads(config.read_text())
observed={'temporary_root':str(taskroot),'probes':[]}
def call(name,fn):
    try: observed['probes'].append({'name':name,'result':fn(),'status':'returned'})
    except Exception as exc: observed['probes'].append({'name':name,'status':'rejected','code':getattr(exc,'code',''),'message':str(exc),'diagnostics':getattr(exc,'diagnostics',())})
def prepared():
    return prepare_project_build(ProjectBuildRequest(workspace,config,taskroot/'dist','node','single-esm'))
def view(pre):
    w=bound_workflow_view(pre.plan,pre.javascript_bindings)
    return {'inputs':[x.to_dict() for x in w.inputs],'calls':[{k:getattr(n,k) for k in ('id','async_mode','result_key','schedule','executor','completion')} for n in w.nodes]}
p=prepared(); observed['baseline']=view(p)
for required in (None,False):
    data=json.loads(json.dumps(original))
    if required is None: data['pipeline']['inputs'][0].pop('required')
    else:data['pipeline']['inputs'][0]['required']=required
    config.write_text(json.dumps(data))
    call('input_'+str(required),lambda:view(prepared()))
config.write_text(json.dumps(original))
for mode in ('result_key','detached'):
    data=json.loads(json.dumps(original)); data['pipeline']['entry_mode']='async'
    data['pipeline']['nodes'][1]['async']=mode
    if mode=='result_key':data['pipeline']['nodes'][1]['result_key']='feature'
    config.write_text(json.dumps(data))
    call('legacy_async_'+mode,lambda:view(prepared()))
config.write_text(json.dumps(original))
input0=p.plan.inputs[0]
changed=replace(p.plan,inputs=(replace(input0,required=False),))
call('root_input_override_mismatch',lambda:{'emitted_inputs':bound_workflow_view(changed,p.javascript_bindings).to_dict()['inputs'],'entry_block_inputs':[x.to_dict() for b in changed.blocks if b.id==changed.entry_block for x in b.inputs],'declaration':emit_workflow_module(changed,javascript_bindings=p.javascript_bindings).declarations.split('export interface WorkflowInputs {')[1].split('}')[0]})
source=project/'ownership-probe.ts';source.write_text('export function run() { setTimeout(() => {}, 1); Promise.resolve(1); return {}; }\n')
for topics in (['ownership'],['completion'],['imports','purity','ownership']):
    call('source_topics_'+','.join(topics),lambda topics=topics:{'findings':run_rule_check_driver({'typecheckFiles':[str(source)],'ruleTopics':topics,'importPolicy':{'owners':[{'path':str(source),'kind':'node','id':'audit.node','export':'run','completion':'immediate'}]}},package_root=project).findings})
# Actual builtin effects invokes a genuine driver; shared policy is accepted but absent from its driver request and record.
class Cache:
    def __init__(self):self.requests=[]
    def source_check(self,request,**opts):
        self.requests.append(request)
        return run_rule_check_driver(request,**opts)
for policy in ({},{'imports':{'allowed':['node:fs']}},{'forbidden_calls':['console.log']}):
    cache=Cache(); context=RuleContext(facts={'source_files':[str(source)],'sources':[],'import_policy':{'owners':[{'path':str(source),'kind':'node','id':'audit.node','export':'run','completion':'immediate'}]},'analysis_cache':cache,'package_root':str(project),'node_command':'node'},subject={'kind':'node','type_key':'audit.node'},target='javascript')
    returned=javascript_rule_bindings()['vibeflow.no_side_effects'](context,{}, {'effect_scope':'none','policy':policy})
    observed['probes'].append({'name':'effects_policy_'+json.dumps(policy,sort_keys=True),'status':'returned','result':{'record':returned.records['effect_policy'].to_dict(),'findings':[x.to_dict() for x in returned.findings],'request':cache.requests}})
Path('/tmp/vibeflow-wide-js-probe.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2,default=str))
print(json.dumps({'root':str(taskroot),'probes':[{k:v for k,v in item.items() if k!='diagnostics'} for item in observed['probes']]},ensure_ascii=False,indent=2,default=str))
