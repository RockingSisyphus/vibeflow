"""Real independent declarations isolate symbol permissions and project sharing."""
from pathlib import Path
from tests.fixtures.adaptation_regressions.common import row,run_cli,write_json
from tests.fixtures.adaptation_regressions.structure import CONTRACT,findings,write,source_rules


def workspace(root,*,cross_root=False):
    roots=[{'id':'app','path':'app'}]+([{'id':'peer','path':'peer'}] if cross_root else [])
    write_json(root/'vibeflow_config.jsonc',{'roots':roots});write_json(root/'project_rules.jsonc',{'rulesets':[]})
    for item in roots:
        app=root/item['path'];write_json(app/'vibeflow_project.jsonc',{'project_target':'python'});source_rules(app)
    return root/'app'


def workflow(app,name,definitions,plugins=()):
    path=app/'configs'/(name+'.jsonc')
    write_json(path,{'plugins':list(plugins),'rulesets':[],'pipeline':{'nodes':[{
        'id':'leaf'+str(i),'definition_id':key,'display_name':'Leaf '+str(i),'description':'Explicit source permission.'}
        for i,key in enumerate(definitions)]}})
    return path


def shared_fixture(root,*,denied):
    app=workspace(root)
    write(app,'parts/util.py','def value():\n    return 7\n')
    second={'provides':[{'key':'result2','type':'number','display_name':'Second result'}],
            'output_semantics':{'result2':['A separately named result.']}}
    write(app,'nodes/shared.py','from vibeflow.targets.python.sdk import node\nfrom parts.util import value\n'
        f"@node(id='audit.first',node_type='vibeflow.node',contract={CONTRACT!r},rulesets=['vibeflow.process'],implementation_files=['../parts/util.py'])\n"
        "class First:\n    def run_pure(self,inputs,params):\n        return {'result':value()}\n"
        f"@node(id='audit.second',node_type='vibeflow.node',contract={second!r},rulesets=['vibeflow.process'])\n"
        "class Second:\n    def run_pure(self,inputs,params):\n        return {'result2':"+('value()' if denied else '7')+"}\n")
    return workflow(app,'workflow',('audit.first','audit.second'))


def library_fixture(root,*,cross_root=False,both=False,denied=False):
    app=workspace(root,cross_root=cross_root)
    library_root=root if cross_root else app
    write(library_root,'base_lib/math.py',"from vibeflow.targets.python.sdk import base_lib\n@base_lib(id='audit.library',rulesets=['vibeflow.base_lib'])\ndef value():\n    return 7\n")
    for selection in (('allowed','denied') if both else (('denied',) if denied else ('allowed',))):
        libs=[] if selection=='denied' else ['audit.library']
        write(app,'nodes/'+selection+'.py','from vibeflow.targets.python.sdk import node\nfrom base_lib.math import value\n'
            f"@node(id='audit.{selection}',node_type='vibeflow.node',contract={CONTRACT!r},rulesets=['vibeflow.process'],base_libs={libs!r})\n"
            "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':value()}\n")
        workflow(app,selection,('audit.'+selection,))
    if cross_root:
        # The shared library has an actual second consumer, not a private-root escape.
        peer=root/'peer'
        write(peer,'nodes/leaf.py',(app/'nodes'/('denied.py' if denied else 'allowed.py')).read_text().replace("base_libs=[]","base_libs=['audit.library']"))
        workflow(peer,'workflow',('audit.denied' if denied else 'audit.allowed',))
    return app


def lifecycle_fixture(root,*,denied):
    app=workspace(root)
    write(app,'nodes/leaf.py','from vibeflow.targets.python.sdk import node\n'
        f"@node(id='audit.leaf',node_type='vibeflow.node',contract={CONTRACT!r},rulesets=[])\n"
        "class Leaf:\n    def run_pure(self,inputs,params):\n        return {'result':7}\n")
    write(app,'plugins/audit/helper.py','def value():\n    return 7\n')
    write(app,'plugins/audit/plugin.py','from vibeflow.targets.python.sdk import Plugin\n'+
        ('from nodes.leaf import Leaf\n' if denied else 'from .helper import value\n')+
        'class Compiler:\n    def before_compile(self,graph):\n        self.value='+('Leaf' if denied else 'value()')+'\n'
        'def compiler(context):\n    return Compiler()\n'
        "plugin=Plugin(id='audit.lifecycle',resources=[],compiler=compiler,declaration_rulesets=[])\n")
    return workflow(app,'workflow',('audit.leaf',),[{'source':{'kind':'file','ref':'plugins/audit/plugin.py'}}])


def checked(root,config,kernel,identifier,*,command='validate',denied=False,suffix='nodes/allowed.py',codes=()):
    args=[command,'--json','--workspace',str(root/'vibeflow_config.jsonc')]
    if command=='validate':args+=['--config',str(config)]
    raw=run_cli(root,args,kernel,name=identifier+'-'+command)
    errors=[x for x in findings(raw['payload']) if x.get('severity')=='error']
    actual_codes=sorted({x.get('code',x.get('rule_id')) for x in errors})
    targets=[x for x in errors if x.get('code',x.get('rule_id')) in codes]
    exact=bool(targets) and all(x.get('source_path',x.get('source_location',{}).get('path'))==str(config.parent.parent/suffix)
        and x.get('source_location',{}).get('line')==2 for x in targets)
    lifecycle=identifier.startswith('lifecycle')
    actual={'exit_code':raw['exit_code'],'codes':actual_codes,'target_exact':exact,'diagnostics':errors}
    expected={'exit_code':1 if denied else 0};failures=[]
    if raw['exit_code']!=expected['exit_code']:failures.append(f"unexpected exit {raw['exit_code']}: {actual_codes}")
    if denied and not lifecycle and not exact:failures.append('ownership failure lost its resource source and import line')
    if denied and lifecycle and not any('outside its package' in x.get('message','') for x in errors):failures.append('missing package boundary diagnostic')
    if not denied and errors:failures.append('allowed ownership rejected: '+repr(actual_codes))
    if identifier=='workflow-isolation-mixed':
        actual['workflow_states']={Path(x['config']).stem:x['status'] for x in raw['payload'].get('reports',())}
        if actual['workflow_states']!={'allowed':'PASS','denied':'FAIL'}:failures.append('selected workflow permissions were not isolated')
    return row('A05.python.'+identifier+'.'+command,'A05','Explicit ownership: '+identifier,expected,actual,failures,root)


def observe(work:Path,kernel:Path,toolchain=None,renderer=None):
    rows=[]
    for denied in (False,True):
        name='shared-denied' if denied else 'shared-symbol-isolated';root=work/name;config=shared_fixture(root,denied=denied)
        for command in ('validate','quality-check'):
            rows.append(checked(root,config,kernel,name,command=command,denied=denied,suffix='nodes/shared.py',
                codes=('VF_IMPORT_LAYER','QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT')))
        name='cross-root-denied' if denied else 'cross-root-allowed';root=work/name;app=library_fixture(root,cross_root=True,denied=denied)
        for command in ('validate','quality-check'):
            rows.append(checked(root,app/'configs'/('denied.jsonc' if denied else 'allowed.jsonc'),kernel,name,command=command,denied=denied,
                suffix='nodes/denied.py' if denied else 'nodes/allowed.py',codes=('VF_IMPORT_LAYER','QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT')))
    root=work/'workflow-isolation';app=library_fixture(root,both=True)
    for name in ('allowed','denied'):
        rows.append(checked(root,app/'configs'/(name+'.jsonc'),kernel,'workflow-isolation-'+name,denied=name=='denied',suffix='nodes/'+name+'.py',codes=('VF_IMPORT_LAYER','QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT',)))
    rows.append(checked(root,app/'configs/allowed.jsonc',kernel,'workflow-isolation-mixed',command='quality-check',denied=True,
        suffix='nodes/denied.py',codes=('QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT',)))
    for denied in (False,True):
        name='lifecycle-contribution-denied' if denied else 'lifecycle-library-allowed';root=work/name;config=lifecycle_fixture(root,denied=denied)
        rows.append(checked(root,config,kernel,name,command='quality-check',denied=denied))
    return rows
