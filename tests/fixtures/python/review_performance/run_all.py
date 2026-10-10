#!/usr/bin/env python3
"""Real CLI observations in fresh processes; all caches die with the command."""

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.fixtures.python.review_performance.fixtures import write_project, register_architecture


def scenarios(representative=False):
    for nodes in (8, 32, 80):
        for libraries in (1, 4, 8):
            if representative and (nodes, libraries) != (8, 1):
                continue
            yield f"shared-{nodes}-{libraries}", {'nodes':nodes,'libraries':libraries,'lines':350}, 'export-architecture'
    if representative:
        for command in ('review', 'run'):
            yield 'entry-'+command, {}, command
        yield 'late-export-architecture', {'late':True}, 'export-architecture'
        yield 'loaded-architecture-validate', {'late':True,'preload':True}, 'validate'
        yield 'invalid-validate', {'violation':True}, 'validate'
        return
    for kind in ('nodeset', 'loop'):
        for repeats in (1, 4, 8):
            yield f"{kind}-{repeats}", {'nested':True,'loop':kind=='loop','repeats':repeats}, 'export-architecture'
    for lines in (100, 350, 480):
        yield f"source-{lines}", {'lines':lines}, 'validate'
    for command in ('validate','export-architecture','run'):
        yield 'relative-'+command, {'relative':True}, command
        yield 'cross-root-'+command, {'cross_root':True}, command
    for kind in ('nodeset','loop'):
        yield kind+'-run', {'nested':True,'loop':kind=='loop','repeats':4}, 'run'
    for command in ('validate','quality-check','review','export-architecture','export-ascii','export-mermaid','run'):
        yield f"entry-{command}", {}, command
    for command in ('validate','export-architecture','export-mermaid','run'):
        yield f"late-{command}", {'late':True}, command
    yield 'loaded-architecture-validate', {'late':True,'preload':True}, 'validate'
    for command in ('validate','review','run'):
        yield f"invalid-{command}", {'violation':True}, command


def command_arguments(command, project):
    result = [command, '--workspace', str(project/'vibeflow_config.jsonc')]
    if command != 'quality-check':
        result += ['--config', str(project/'workflow.jsonc')]
    if command in ('validate','quality-check'):
        result += ['--json']
    if command.startswith('export-') or command == 'review':
        suffix = {'export-architecture':'jsonc','export-ascii':'txt','export-mermaid':'mmd'}.get(command,'svg')
        filename = 'ARCHITECTURE.jsonc' if command == 'export-architecture' else 'graph.'+suffix
        result += ['--output', str(project/filename)]
    if command in ('export-mermaid','export-svg'):
        result += ['--expand-nodesets']
    if command == 'run':
        result += ['--input',str(project/'input.json'),'--run-root',str(project/'runs'),'--run-id','observed']
    return result


def verify(identifier, options, command, observation, project, *, baseline):
    failures = []
    invalid = options.get('violation', False)
    if observation['error'] or (observation['exit_code'] != (1 if invalid else 0)):
        failures.append('formal CLI did not return its expected result')
    if invalid:
        payload = json.loads((project/'observation.stdout.txt').read_text())
        health = payload.get('validation',{}) if command == 'review' else payload.get('health',{}) if command == 'run' else payload
        target = [item for item in health.get('errors',()) if item.get('rule_id') == 'BASE_LIB.SIDE_EFFECT_CALL' and item.get('object_id') == 'perf.library.0']
        expected = {'path':str(project/'base_lib/lib0.py'),'line':4,'column':5}
        if len(target) != 1 or target[0].get('severity') != 'error' or target[0].get('source_location') != expected or 'print' not in target[0].get('message',''):
            failures.append('forbidden library print lost its diagnostic, severity, or source location')
        allowed = {'NODE.EFFECT.CALL_FORBIDDEN','BASE_LIB.SIDE_EFFECT_CALL','NODE.BASE_LIB.INDIRECT_VIOLATION'}
        if any(item.get('rule_id') not in allowed for item in health.get('errors',())):
            failures.append('unrelated errors obscured the targeted source failure')
        if command == 'review' and (payload.get('published') is not False or (project/'graph.svg').exists()):
            failures.append('failed review published SVG')
        if command == 'run':
            path = project/'runs/observed/health_report.json'
            written = json.loads(path.read_text()) if path.exists() else {}
            if written != health:
                failures.append('run health artifact differs from its formal health result')
    if not baseline and options.get('late') and (project/'late.marker').exists() != (command == 'run' or options.get('preload', False)):
        failures.append('lazy implementation loaded at the wrong phase')
    if not invalid and command == 'export-architecture':
        text = (project/'ARCHITECTURE.jsonc').read_text()
        if '#d6eaff' not in text or 'perf.library.0' not in text:
            failures.append('architecture lost styles or library identity')
    if not baseline and observation['calls'].get('native_initialization_identity',0):
        failures.append('initialization fingerprint repeated before rule cache lookup')
    calls = observation.get('presentation_calls', {})
    if not baseline and any(calls.get(name,0) for name in ('bind','library_review','rule_plan','compile')):
        failures.append('presentation triggered binding or checks')
    if not baseline and command == 'review' and observation['calls'].get('environment') != 1:
        failures.append('review reloaded the workspace')
    if not invalid and command != 'run' and not baseline:
        actual = sum(item['executions'] for item in observation['rules'] if item['id']=='perf.call')
        expected = options.get('nodes',8) * options.get('repeats',1)
        if actual != expected:
            failures.append(f'call rule executed {actual} times, expected {expected}')
    if not baseline:
        for filename, count in observation.get('parsing_counts',{}).items():
            if str(project) in filename and filename.endswith('.py') and count != 1:
                failures.append(f'shared source parsed {count} times: {filename}')
    return failures


def observe(identifier, options, command, args, index=0):
    project = args.work / (identifier+f'-{index}')
    write_project(project, **{key:value for key,value in options.items() if key != 'preload'})
    # review/quality exercise the registered canonical Architecture document.
    if command in ('review','quality-check') or options.get('preload'):
        prepare = command_arguments('export-architecture',project)
        run_cli(project, prepare, args, 'seed')
        register_architecture(project)
    observation = run_cli(project, command_arguments(command,project),args,
                          preload='perf.late' if options.get('preload') else None)
    failures = verify(identifier, options, command, observation,project,baseline=args.baseline)
    if command == 'review' and not options.get('violation') and observation['exit_code'] == 0:
        failures += inspect_products(project, args)
    return {'id':identifier,'iteration':index,'options':options,'command':command,
            'matched':not failures,'failures':failures,'artifact_root':str(project),**observation}


def inspect_products(project, args):
    """Inspect the canonical JSONC, Mermaid and computed SVG in a browser."""
    failures = []
    document = json.loads('\n'.join(line for line in (project/'ARCHITECTURE.jsonc').read_text().splitlines()
                                    if not line.strip().startswith('//')))
    node = next(item for item in document['workflow']['nodes'] if item['id']=='step0')
    style = node['presentation']
    if style['values']['fill'] != '#d6eaff' or style['values']['shape'] != 'rounded' or style['sources']['fill'] != 'node':
        failures.append('canonical Architecture presentation differs from the declaration')
    descriptor = document['node_types']['perf.step.0']
    if 'group0.py' not in json.dumps(descriptor) or 'perf.calls' not in json.dumps(descriptor):
        failures.append('canonical Architecture lost implementation or ruleset sources')
    mermaid = (project/'graph.mmd').read_text() if (project/'graph.mmd').exists() else ''
    if '#d6eaff' not in mermaid:
        failures.append('review Mermaid lost declared color')
    if not args.renderer:
        return failures+['browser evidence requires --renderer']
    result = subprocess.run(['node',str(ROOT/'tests/fixtures/rule_gaps/resource_browser.mjs'),
                             str(args.renderer),str(project/'graph.svg'),str(project/'graph.png')],
                             capture_output=True,text=True,timeout=60,check=True)
    browser = json.loads(result.stdout)
    (project/'browser.json').write_text(json.dumps(browser,indent=2)+'\n')
    selected = [item for item in browser['nodes'] if 'step0' in item['text']]
    colored = [shape for item in selected for shape in item['shapes'] if shape['fill']=='rgb(214, 234, 255)']
    if not colored or any(shape['width']<=0 or shape['height']<=0 for shape in colored):
        failures.append('final SVG has no visible declared node geometry/color')
    if not any(shape['tag']=='rect' and float(shape.get('rx') or 0)>0 for shape in colored):
        failures.append('final SVG does not use the declared rounded shape')
    return failures


def run_cli(project, arguments, args, name='observation', *, preload=None):
    report = project/(name+'.json')
    env = os.environ.copy()
    paths = [str(ROOT)] if args.installed else [str(args.kernel),str(ROOT)]
    env['PYTHONPATH'] = os.pathsep.join(paths)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if args.renderer:
        env['VIBEFLOW_MERMAID_RENDERER_ROOT'] = str(args.renderer)
    invocation = [sys.executable,'-B','-m','tests.fixtures.python.review_performance.observe_cli',
                  '--report',str(report)]
    if preload:
        invocation += ['--preload',preload]
    invocation += ['--',*arguments]
    result = subprocess.run(invocation,env=env,capture_output=True,text=True,timeout=180)
    if result.returncode or not report.exists():
        raise RuntimeError(f'Observation failed: {result.stdout}\n{result.stderr}')
    return json.loads(report.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--kernel',type=Path,default=ROOT/'src')
    parser.add_argument('--installed',action='store_true')
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--representative',action='store_true')
    parser.add_argument('--renderer',type=Path)
    parser.add_argument('--timing-repeats',type=int,default=3)
    args = parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=True)
    results, errors = [], []
    for identifier, options, command in scenarios(args.representative):
        repeats = args.timing_repeats if identifier in ('shared-8-1','shared-32-4','shared-80-8') else 1
        for iteration in range(repeats):
            try:
                item = observe(identifier,options,command,args,iteration)
                results.append(item)
                print(f"{identifier}/{iteration}: {'PASS' if item['matched'] else item['failures']} ({item['seconds']:.3f}s)",flush=True)
            except Exception as error:
                errors.append({'id':identifier,'iteration':iteration,'error':repr(error)})
                print(f'{identifier}/{iteration}: observation error {error}',flush=True)
    from tests.fixtures.python.review_performance.cache_cases import observe_cases
    for item in observe_cases(args.work/'cache',args.kernel,args.renderer,installed=args.installed):
        results.append(item)
        print(f"{item['id']}: {'PASS' if item['matched'] else item['failures']}",flush=True)
    medians = {key:statistics.median(item['seconds'] for item in results if item['id']==key)
               for key in sorted({item['id'] for item in results})}
    summary = {'schema':'vibeflow.review-performance.batch.v1','baseline':args.baseline,
               'cases':results,'observation_errors':errors,'median_seconds':medians,
               'matched':not errors and all(item['matched'] for item in results)}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(summary,indent=2)+'\n')
    return 0 if summary['matched'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
