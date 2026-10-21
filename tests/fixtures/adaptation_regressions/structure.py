"""Independent resources retain explicit source relationships at both check levels."""
from pathlib import Path
from tests.fixtures.adaptation_regressions.common import row,run_cli,write_json
from tests.fixtures.support.projects import register_root

CONTRACT={"provides":[{"key":"result","type":"number","display_name":"Result"}],
          "output_semantics":{"result":["The calculated result."]}}


def write(root,relative,source):
    path=root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(source,encoding="utf-8")


def source_rules(root):
    write_json(root/'root_rules.jsonc',{'rulesets':['vibeflow.root.default'],'rule_params':{
        'vibeflow.root.structure':{'enabled':True},'vibeflow.root.layout':{'directories':[
            {'path':p,'purpose':'Explicit source ownership regression support.'} for p in ('parts','libraries')]}}})


def fixture(root,kind='node',*,registered=True,conventional=False):
    register_root(root);source_rules(root)
    directory='base_lib' if conventional else 'parts'
    write(root,directory+'/util.py','def value():\n    return 7\n')
    support=',implementation_files=['+repr(str(root/directory/'util.py'))+']' if registered else ''
    imports=f'from {directory}.util import value\n'
    libraries=''
    if kind=='base_lib':
        write(root,'base_lib/entry.py','from vibeflow.targets.python.sdk import base_lib\n'+imports+
            "@base_lib(id='audit.library',rulesets=['vibeflow.base_lib']"+support+")\ndef value_from_library():\n    return value()\n")
        imports='from base_lib.entry import value_from_library as value\n';support='';libraries=",base_libs=['audit.library']"
    if kind=='declaration':
        imports='';support='';body='7'
    else:body='value()'
    write(root,'nodes/leaf.py','from vibeflow.targets.python.sdk import node\n'+imports+
        f"@node(id='audit.leaf',node_type='vibeflow.node',contract={CONTRACT!r},rulesets=['vibeflow.process']"+support+libraries+")\n"
        "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':"+body+"}\n")
    write_json(root/'configs/workflow.jsonc',{'rulesets':[],'pipeline':{'nodes':[{
        'id':'leaf','definition_id':'audit.leaf','display_name':'Leaf','description':'Review the independent SDK definition.'}]}})


def findings(payload):
    if not isinstance(payload,dict):return []
    result=[item for key in ('errors','warnings','findings') for item in payload.get(key,())]
    for key in ('source_quality','health','validation'):
        if isinstance(payload.get(key),dict):result.extend(findings(payload[key]))
    for item in payload.get('reports',()):result.extend(findings(item))
    return result


def observe(work:Path,kernel:Path,toolchain=None,renderer=None):
    rows=[]
    variants=(('node-support','node',True,False),('node-support-conventional','node',True,True),
        ('node-unregistered','node',False,False),('library-support','base_lib',True,False),
        ('library-unregistered','base_lib',False,False),('declaration-contribution','declaration',True,False))
    for identifier,kind,registered,conventional in variants:
        root=work/identifier;fixture(root,kind,registered=registered,conventional=conventional)
        for command in ('validate','quality-check'):
            args=[command,'--json','--workspace',str(root.parent/'vibeflow_config.jsonc')]
            if command=='validate':args+=['--config',str(root/'configs/workflow.jsonc')]
            raw=run_cli(root,args,kernel,name=command)
            errors=[x for x in findings(raw['payload']) if x.get('severity')=='error']
            codes=sorted({x.get('code',x.get('rule_id')) for x in errors})
            expected={'exit_code':0 if registered else 1};failures=[]
            if raw['exit_code']!=expected['exit_code']:failures.append(f"unexpected exit {raw['exit_code']}: {codes}")
            if registered and codes:failures.append('declared support was rejected: '+repr(codes))
            if not registered and not set(codes)&{'VF_IMPORT_OWNER','VF_IMPORT_LAYER','QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT','QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT'}:
                failures.append('missing explicit ownership diagnostic')
            rows.append(row('A05.python.'+identifier+'.'+command,'A05','Independent SDK source ownership: '+identifier,
                expected,{'exit_code':raw['exit_code'],'codes':codes,'diagnostics':errors},failures,root))
    from tests.fixtures.adaptation_regressions.structure_extra import observe as extra
    return rows+extra(work/'extra',kernel,toolchain,renderer)
