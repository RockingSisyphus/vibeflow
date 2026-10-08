import sys, tempfile, shutil, json
from pathlib import Path
ROOT=Path('/home/rockingsisyphus/projects/VibeFlow');sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from tests.fixtures.support.plugins import resource, copy_sdk_inputs
from vibeflow.tooling.application.javascript.audit import JavascriptAuditRequest,audit_javascript_project
from vibeflow.core.flow import GraphConfig,NodeSpec
from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
from vibeflow.tooling.project.descriptor_loader import load_workflow_catalogs
from vibeflow.targets.javascript.quality.rules import run_javascript_rules
import vibeflow.targets.javascript.build.rule_session as service
root=Path(tempfile.mkdtemp(prefix='vibeflow-wide-js-params-',dir='/tmp'));example=root/'example';shutil.copytree(ROOT/'sandbox/javascript/domain_rules',example)
copy_sdk_inputs(ROOT/'sandbox/javascript/domain_rules',example)
project=example/'project';(project/'node_modules').symlink_to('/tmp/vibeflow-s01-s04-independent-tests/javascript-toolchain/node_modules',target_is_directory=True)
source=project/'nodes/transform.ts';source.write_text('export function run(inputs: Readonly<{"example.feature": Readonly<{value: number}>}>) { console.log("probe"); return {output: inputs["example.feature"].value+1}; }\n')
nodefile=resource(project,'node','example.transform');n=json.loads(nodefile.read_text());n['rulesets']=['audit.parameter_probe'];nodefile.write_text(json.dumps(n))
observed={'root':str(root),'cases':[]};original=service.run_rule_check_driver
for name,params in [('empty',{'effect_scope':'none','policy':{}}),('marker',{'effect_scope':'none','policy':{'audit_marker':'selected'}}),('terminal',{'effect_scope':'terminal','policy':{}})]:
  resource(project,'ruleset','audit.parameter_probe').write_text(json.dumps({'kind':'ruleset','id':'audit.parameter_probe','calls':[{'id':'effects','rule_id':'vibeflow.no_side_effects'},{'id':'imports','rule_id':'vibeflow.import_side_effects'}], 'relations':[{'source':'$self','target':name,'kind':'overrides','params':params} for name in ('effects','imports')], 'entrypoints':{'static':['effects'],'import':['imports'],'run':[]}}))
  requests=[]
  def recording(request,**kwargs):
    requests.append(request)
    return original(request,**kwargs)
  service.run_rule_check_driver=recording
  catalogs=load_workflow_catalogs(project,project_config=project/'vibeflow_project.jsonc',workflow_config=project/'configs/model.jsonc')
  policy,_=target_neutral_import_policy(catalogs=catalogs,project_root=project,allowed_external=set(),node_ids=frozenset({'example.transform'}))
  report=run_javascript_rules(GraphConfig(nodes=(NodeSpec('transform','example.transform'),),rulesets=()),catalogs,project_root=project,package_root=project,target='node',import_policy=policy)
  observed['cases'].append({'name':name,'requested_params':params,'execution':[x.to_dict() for x in report.results['example.transform']],'source_driver_requests':requests,'findings':[x.to_dict() for x in report.findings]})
service.run_rule_check_driver=original
Path('/tmp/vibeflow-wide-js-formal-policy.json').write_text(json.dumps(observed,indent=2,ensure_ascii=False,default=str))
print(json.dumps({'root':str(root),'cases':[{'name':x['name'],'findings':[f['rule_id'] for f in x['findings']],'phases':[{ 'phase':e['plan']['entrypoint'],'calls':[{'id':i['id'],'params':i['params']} for i in e['plan']['calls']]} for e in x['execution']], 'requests':[{'topics':r.get('ruleTopics'),'policy_keys':list(r)} for r in x['source_driver_requests']]} for x in observed['cases']]},indent=2,ensure_ascii=False))
