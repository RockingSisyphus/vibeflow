"""Formal CLI observations for shared libraries and repeated JavaScript Nodesets."""
import argparse
from collections import Counter
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[4]


def write_project(root,toolchain,*,nodes,libraries,repeats):
    from tests.fixtures.support.plugins import write_plugin
    root.mkdir(parents=True)
    for name in ('nodes','base_lib'):(root/name).mkdir()
    (root/'node_modules').symlink_to(toolchain/'node_modules',target_is_directory=True)
    for name in ('package.json','package-lock.json'):
        (root/name).write_bytes((toolchain/name).read_bytes())
    resources=[]
    for i in range(libraries):
        (root/'base_lib'/f'lib{i}.ts').write_text(f'export function add{i}(value:number):number {{return value+{i+1};}}\n')
        resources.append({'kind':'base_lib','id':f'perf.lib.{i}','rulesets':['vibeflow.base_lib'],
            'implementations':[{'language':'typescript','targets':['node'],'source':{'kind':'file','ref':f'base_lib/lib{i}.ts','export':f'add{i}'}}]})
    for i in range(nodes):
        text='\n'.join(f'import {{add{j}}} from "../base_lib/lib{j}.ts";' for j in range(libraries))
        text+=f'\nexport function run(){{let value={i};'
        text+=''.join(f'value=add{j}(value);' for j in range(libraries))
        text+=f'if(value!=={i+sum(range(1,libraries+1))}) throw new Error("arithmetic");return {{}};}}\n'
        (root/'nodes'/f'step{i}.ts').write_text(text)
        resources.append({'kind':'node','type_key':f'perf.step.{i}','contract':{},'base_libs':[f'perf.lib.{j}' for j in range(libraries)],
            'rulesets':['vibeflow.process','perf.proof'],'implementations':[{'language':'typescript','targets':['node'],
                'source':{'kind':'file','ref':f'nodes/step{i}.ts','export':'run'}}]})
    (root/'nodes/boundary.ts').write_text('export function run(){return {};}\n')
    resources.append({'kind':'node','type_key':'perf.boundary','flow_kind':'terminal','contract':{},'rulesets':['vibeflow.io'],
        'implementations':[{'language':'typescript','targets':['node'],'source':{'kind':'file','ref':'nodes/boundary.ts','export':'run'}}]})
    (root/'proof.ts').write_text('export function check(context){if(!context.facts.source_files.length)throw new Error("missing source facts");return {records:{proof:{type_id:"perf.proof.v1",value:{files:context.facts.source_files.length}}}};}\n')
    resources.extend([{'kind':'rule','id':'perf.proof','scope':'source','outputs':{'proof':'perf.proof.v1'},
        'implementations':[{'language':'typescript','source':{'kind':'file','ref':'proof.ts','export':'check'}}]},
        {'kind':'ruleset','id':'perf.proof','calls':[{'id':'check','rule_id':'perf.proof'}],
            'entrypoints':{'import':[],'static':['check'],'run':[]}}])
    write_plugin(root,resources,target='javascript',plugin_id='perf.resources')
    def call(name,kind):return {'id':name,'type_used':kind,'display_name':name,'description':'Fixed performance fixture.'}
    body=[call('start','perf.boundary'),*[call(f'step{i}',f'perf.step.{i}') for i in range(nodes)],call('end','perf.boundary')]
    body[-1]['similar_to']={'node':'start','relationship':'copy','reason':'Empty boundaries.'}
    def pipeline(calls):return {'nodes':calls,'edges':[[a['id'],b['id']] for a,b in zip(calls,calls[1:])]}
    (root/'body.jsonc').write_text(json.dumps({'type_key':'perf.body','display_name':'Body','description':'Shared body.',
        'requires':[],'provides':[],'pipeline':pipeline(body)}))
    calls=[call('start','perf.boundary'),*[call(f'body{i}','perf.body') for i in range(repeats)],call('end','perf.boundary')]
    calls[-1]['similar_to']={'node':'start','relationship':'copy','reason':'Empty boundaries.'}
    (root/'workflow.jsonc').write_text(json.dumps({'nodeset_imports':[{'path':'body.jsonc'}],
        'plugins':[{'source':{'kind':'file','ref':'code_plugin.ts','export':'plugin'}}],
        'rulesets':['vibeflow.workflow'],'pipeline':pipeline(calls)}))
    (root/'vibeflow_config.jsonc').write_text('{"roots":[{"id":"perf","path":"."}]}')
    (root/'vibeflow_project.jsonc').write_text('{"project_target":"javascript","javascript":{"package_root":".","external_packages":[]}}')


def observe(args):
    sys.path[:0]=[str(args.kernel/'src'),str(args.kernel)]
    from vibeflow.tooling.application.cli import main
    from vibeflow.targets.javascript.build import toolchain,plugin_session
    counts=Counter(); patches=[]
    def wrap(owner,name,label):
        original=getattr(owner,name)
        def traced(*a,**kw):
            counts[label]+=1
            previous=len(a[0].views) if label=='view_capture' else 0
            result=original(*a,**kw)
            if label=='view_capture':counts['view_created']+=len(a[0].views)-previous
            return result
        setattr(owner,name,traced);patches.append((owner,name,original))
    import hashlib
    original_hash = hashlib.sha256
    counts['rule_identity_hash'] = 0
    def hashing(*a,**kw):
        if sys._getframe(1).f_code.co_filename.endswith('/build/rule_session.py'):
            counts['rule_identity_hash'] += 1
        return original_hash(*a,**kw)
    hashlib.sha256 = hashing
    try:
        from vibeflow.targets.shared.facts import FactStore
        wrap(FactStore,'capture','view_capture')
    except ImportError:pass
    wrap(toolchain,'_run_driver','driver_request')
    wrap(plugin_session.JavascriptPluginSession,'evaluate_rule','worker_evaluation')
    from vibeflow.targets.javascript.build import driver_session
    wrap(driver_session.DriverSession,'__init__','driver_start')
    # The driver JSONL responses carry the actual Program session counters.
    program_log = args.report.with_suffix(".programs.jsonl")
    os.environ["VIBEFLOW_PROGRAM_PROBE"] = str(program_log)
    os.environ["NODE_OPTIONS"] = "--import=" + str(Path(__file__).with_name("program_probe.mjs"))
    start=perf_counter()
    with args.report.with_suffix('.stdout').open('w') as out,args.report.with_suffix('.stderr').open('w') as err,redirect_stdout(out),redirect_stderr(err):
        code=main(['validate','--workspace',str(args.project/'vibeflow_config.jsonc'),'--config',str(args.project/'workflow.jsonc')])
    args.report.write_text(json.dumps({'exit_code':code,'seconds':perf_counter()-start,'counts':dict(counts),'program_builds':len(program_log.read_text().splitlines()) if program_log.exists() else 0},indent=2)+'\n')
    return code


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path,default=ROOT);parser.add_argument('--toolchain',type=Path)
    parser.add_argument('--work',type=Path);parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--project',type=Path);parser.add_argument('--observe',action='store_true')
    parser.add_argument('--baseline',action='store_true');parser.add_argument('--timing-repeats',type=int,default=3)
    args=parser.parse_args()
    if args.observe:return observe(args)
    sys.path.insert(0,str(ROOT))
    cases=[]
    for nodes,libraries,repeats in ((4,1,1),(8,4,1),(8,4,4)):
        name=f'n{nodes}-l{libraries}-r{repeats}';project=args.work/name
        write_project(project,args.toolchain,nodes=nodes,libraries=libraries,repeats=repeats)
        observations=[]
        for i in range(args.timing_repeats):
            report=args.work/f'{name}-{i}.json'
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            subprocess.run([sys.executable,'-B',str(Path(__file__)), '--observe','--kernel',str(args.kernel),'--project',str(project),'--report',str(report)],check=False,env=env)
            observations.append(json.loads(report.read_text()))
        cases.append({'id':name,'median_seconds':statistics.median(item['seconds'] for item in observations),'observations':observations})
    failures=[]
    if not args.baseline:
        if any(item['counts'].get('rule_identity_hash',0) for case in cases for item in case['observations']):failures.append('Rule identity still hashes source on dispatch')
        one,many=cases[1]['observations'][0],cases[2]['observations'][0]
        for counter in ('worker_evaluation','driver_request'):
            if one['counts'].get(counter,0)!=many['counts'].get(counter,0):failures.append('Repeated calls increased '+counter)
        if one['program_builds']!=many['program_builds']:failures.append('Repeated calls rebuilt Programs')
    args.report.write_text(json.dumps({'cases':cases,'failures':failures},indent=2)+'\n')
    return 0 if not failures and all(item['exit_code']==0 for case in cases for item in case['observations']) else 1


if __name__=='__main__':raise SystemExit(main())
