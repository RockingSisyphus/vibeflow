"""Independent formal CLI comprehension scope and owned-input controls.

Inspected Node/BaseLib/Plugin project code is validated, never run. Host cases
use none; owned-input cases use global_state so mutable state permission cannot
hide the independent input ownership check. Original review covers five scopes.
"""
from __future__ import annotations
import argparse, ast, hashlib, importlib.metadata, json, subprocess, sys, traceback, zipfile
from pathlib import Path

FORMS = {'list':'[{v} for {v} in ()]', 'set':'{{{v} for {v} in ()}}',
         'dict':'{{{v}: {v} for {v} in ()}}', 'generator':'({v} for {v} in ())'}
POLICY = {'imports':dict.fromkeys(('allowed_roots','banned_roots','allowed_modules','banned_modules'), [])}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def cases():
    rows=[]
    for kind in ('node','base_lib','plugin'):
        for form, template in FORMS.items():
            for target in ('sys','item'):
                rows.append((kind,'host_'+form,target,'none',f'(sys.argv, {template.format(v=target)})',True,'host'))
        for target in ('sys','item'):
            rows.append((kind,'host_first_iterable',target,'none',f'[{target} for {target} in sys.argv]',True,'host'))
        rows.append((kind,'host_direct','none','none','sys.argv',True,'host'))
        rows.append((kind,'host_local_body','sys','none','[sys.argv for sys in ()]',False,'host'))
        for form, template in FORMS.items():
            for target in ('close','item'):
                rows.append((kind,'pure_close_'+form,target,'none',f'(close(), {template.format(v=target)})',False,'pure'))
        rows.append((kind,'pure_close_direct','none','none','close()',False,'pure'))
    for placement in ('method','helper'):
        for form, template in FORMS.items():
            for target in ('inputs','item'):
                rows.append(('node','input_'+placement+'_'+form,target,'global_state',f"(inputs.pop('seed', None), {template.format(v=target)})",True,'input'))
        rows.append(('node','input_'+placement+'_direct','none','global_state',"inputs.pop('seed', None)",True,'input'))
        for target in ('inputs','item'):
            rows.append(('node','input_'+placement+'_first_iterable',target,'global_state',f"[{target} for {target} in inputs.pop('seed', ())]",True,'input'))
            rows.append(('node','input_'+placement+'_local_body',target,'global_state',f"[{target}.pop('seed', None) for {target} in ()]",False,'input'))
    return rows


def project(path, kind, label, scope, expression, family):
    path.mkdir(parents=True)
    write(path/'vibeflow_config.jsonc',{'roots':[{'id':'comprehension','path':'.'}]})
    write(path/'vibeflow_project.jsonc',{'project_target':'python'})
    write(path/'workflow.jsonc',{'plugins':[{'source':{'kind':'file','ref':'plugin.py'}}], 'pipeline':{
        'inputs':[], 'outputs':[], 'nodes':[
            {'id':'start','type_used':'probe.start','display_name':'Start','description':'Starts.'},
            {'id':'task','type_used':'probe.task','display_name':'Task','description':'Checks source.'},
            {'id':'end','type_used':'probe.start','display_name':'End','description':'Ends.'}],
        'edges':[['start','task'],['task','end']]}})
    selected="selected = ruleset(id='probe.effects', calls="+repr([{'id':'effects','rule_id':'vibeflow.no_side_effects','params':{'effect_scope':scope,'policy':POLICY}}])+")\n"
    prefix='import sys\n' if family=='host' else 'from pure_helper import close\n' if family=='pure' else ''
    if family=='pure':
        (path/'pure_helper.py').write_text('def close():\n    return 1\n')
    source=prefix+'def helper():\n    return (lambda: '+expression+')()\n'
    task="\n@node(type_key='probe.task', rulesets="+repr(['probe.effects'] if kind=='node' else [])+( ", base_libs=['probe.library']" if kind=='base_lib' else '')+", contract={})\nclass Task:\n    def run_pure(self, inputs, params):\n"
    if family=='input':
        statements='fn = lambda: '+expression+'\nfn()\n'
        if '_helper_' in label:
            source='def helper(inputs):\n'+''.join('    '+line+'\n' for line in statements.splitlines())
            task+='        helper(inputs)\n'
        else:
            source=''
            task+=''.join('        '+line+'\n' for line in statements.splitlines())
        task+='        return {}\n'
    else:
        task+=('        helper()\n' if kind=='node' else '        calculate()\n' if kind=='base_lib' else '')+'        return {}\n'
    node_text='from vibeflow.targets.python.sdk import node\n'
    if kind=='base_lib':
        node_text+='from library import calculate\n'
        lib='from vibeflow.targets.python.sdk import base_lib\n'+prefix+"@base_lib(id='probe.library', rulesets=['probe.effects'])\ndef calculate():\n    return (lambda: "+expression+")()\n"
        offender=path/'library.py';offender.write_text(lib)
    elif kind=='plugin':
        offender=path/'runtime_resource.py'
        offender.write_text(source+'\ndef create_runtime(context):\n    helper()\n    return Runtime()\n\nclass Runtime:\n    pass\n')
    else:
        node_text+=source
        offender=path/'node_resource.py'
    node_text+=task+"\n@node(type_key='probe.start', flow_kind='terminal', rulesets=[], contract={})\nclass Start:\n    def run_pure(self, inputs, params):\n        return {}\n"
    (path/'node_resource.py').write_text(node_text)
    imports='from vibeflow.targets.python.sdk import Plugin, ruleset\nfrom node_resource import Start, Task\n'
    resources='[Start, Task, selected]';options=''
    if kind=='base_lib':
        imports+='from library import calculate\n';resources='[Start, Task, calculate, selected]'
    if kind=='plugin':
        imports+='from runtime_resource import create_runtime\n';options=", runtime=create_runtime, rulesets=['probe.effects']"
    (path/'plugin.py').write_text(imports+selected+f"plugin=Plugin(id='probe', resources={resources}{options}, declaration_rulesets=[])\n")
    return offender


def findings(payload):
    result=[]
    def visit(value):
        if isinstance(value,dict):
            if value.get('definition_id')=='vibeflow.no_side_effects' and 'source_location' in value and value not in result:
                result.append(value)
            for key,item in value.items():
                if key not in ('source_code','resources','definitions'): visit(item)
        elif isinstance(value,list):
            for item in value: visit(item)
    visit(payload);return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);p=parser.add_mutually_exclusive_group();p.add_argument('--source',type=Path);p.add_argument('--kernel',type=Path)
    parser.add_argument('--work',required=True,type=Path);parser.add_argument('--report',required=True,type=Path);parser.add_argument('--expect',choices=('before','fixed'),required=True)
    args=parser.parse_args();report={'observations':[],'expected_state':args.expect,'probe_error':None,'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    try:
        if args.kernel: product=args.kernel.resolve(strict=True);kind='kernel_zip'
        elif args.source: product=args.source.resolve(strict=True);kind='source_snapshot'
        else:
            distribution=importlib.metadata.distribution('vibeflow');assert distribution.read_text('WHEEL');assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info',{}).get('editable');product=Path(distribution.locate_file('')).resolve(strict=True);kind='installed_wheel'
        report['product']={'kind':kind,'path':str(product)}
        if args.kernel:report['product']['sha256']=hashlib.sha256(product.read_bytes()).hexdigest()
        def product_hashes():
            if args.kernel:
                with zipfile.ZipFile(product) as archive:
                    return {name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()
                            if name.startswith('vibeflow/') and not name.endswith('/')}
            directory=product/'vibeflow'
            return {'vibeflow/'+path.relative_to(directory).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in directory.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo')}
        report['product_files_sha256']=product_hashes()
        bootstrap="import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from vibeflow.tooling.application.python.cli import main;code=main(json.loads(sys.argv[2]));modules={n:str(getattr(m,'__file__','')) for n,m in sys.modules.items() if n=='vibeflow' or n.startswith('vibeflow.')};expected=str(Path(sys.argv[1])/'vibeflow')+'/';Path(sys.argv[3]).write_text(json.dumps({'origin':modules['vibeflow'],'loaded_module_count':len(modules),'foreign_product_modules':{n:p for n,p in modules.items() if not p or not p.startswith(expected)}}));raise SystemExit(code)"
        for kind,label,target,scope,expression,expected,family in cases():
            name='.'.join((kind,label,target));work=args.work.resolve()/name;offender=project(work,kind,label,scope,expression,family)
            argv=['validate','--workspace',str(work/'vibeflow_config.jsonc'),'--config',str(work/'workflow.jsonc'),'--json']
            proc=subprocess.run([sys.executable,'-I','-B','-c',bootstrap,str(product),json.dumps(argv),str(work/'origin.json')],cwd=work,text=True,capture_output=True,timeout=30)
            (work/'stdout.txt').write_text(proc.stdout);(work/'stderr.txt').write_text(proc.stderr)
            payload=json.loads(proc.stdout);write(work/'cli.json',payload);actual=findings(payload);origin=json.loads((work/'origin.json').read_text());assert not origin['foreign_product_modules']
            tree=ast.parse(offender.read_text())
            expression_nodes=[node for node in ast.walk(tree) if (family=='host' and isinstance(node,ast.Attribute) and node.attr=='argv') or (family=='input' and isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='pop')]
            locations=[{'path':str(offender),'line':node.lineno,'column':node.col_offset+1} for node in expression_nodes]
            specific=[finding for finding in actual if 'mutate inputs' in finding['message'] and finding.get('source_location') in locations] if family=='input' else [finding for finding in actual if finding.get('source_location') in locations] if family=='host' else actual
            expected_status='FAIL' if expected else 'PASS';matched=bool(specific)==expected and payload.get('status')==expected_status and proc.returncode==(1 if expected else 0)
            report['observations'].append({'case':name,'kind':kind,'family':family,'form':label,'target':target,'scope':scope,'expression':expression,'source':offender.read_text(),'source_path':str(offender),'expected_diagnostic':expected,'actual_diagnostic':bool(specific),'matched':matched,'status':payload.get('status'),'exit_code':proc.returncode,'findings':actual,'matching_findings':specific,'expected_expression_locations':locations,'product':origin})
        report['product_files_sha256_after']=product_hashes();assert report['product_files_sha256']==report['product_files_sha256_after'], 'Product changed during probe'
        rows=report['observations'];report['summary']={'cases':len(rows),'matched':sum(r['matched'] for r in rows),'mismatches':sum(not r['matched'] for r in rows),'by_family':{family:{'cases':sum(r['family']==family for r in rows),'mismatches':sum(r['family']==family and not r['matched'] for r in rows)} for family in ('host','pure','input')}}
        report['expected_state_observed']=report['summary']['mismatches']==0 if args.expect=='fixed' else report['summary']['mismatches']>0
    except Exception:
        report['probe_error']=traceback.format_exc();report['expected_state_observed']=False
    write(args.report.resolve(),report);print(json.dumps({k:report.get(k) for k in ('summary','probe_error','expected_state_observed')}));return 0 if report['expected_state_observed'] else 1


if __name__=='__main__':raise SystemExit(main())
