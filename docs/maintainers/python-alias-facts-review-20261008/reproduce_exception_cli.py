"""SDK -> RulePlan -> CLI exception-edge probes; validate only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from textwrap import indent

from reproduce_exception_alias import CASES


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--product', type=Path, required=True)
    p.add_argument('--work', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    bootstrap = ('import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
        'from vibeflow.tooling.application.python.cli import main;code=main(json.loads(sys.argv[2]));'
        'modules={n:str(getattr(m,"__file__","")) for n,m in sys.modules.items() if n=="vibeflow" or n.startswith("vibeflow.")};'
        'expected=str(Path(sys.argv[1])/"vibeflow")+"/";'
        'Path(sys.argv[3]).write_text(json.dumps({"origin":modules["vibeflow"],"foreign":{n:v for n,v in modules.items() if not v.startswith(expected)}}));raise SystemExit(code)')
    rows = []
    for label, expression, expected in CASES:
        for via_helper in (False, True):
            root = args.work.resolve() / (label + ('.helper' if via_helper else '.direct'))
            root.mkdir(parents=True)
            write(root / 'vibeflow_config.jsonc', {'roots':[{'id':'probe','path':'.'}]})
            write(root / 'vibeflow_project.jsonc', {'project_target':'python'})
            write(root / 'workflow.jsonc', {'plugins':[{'source':{'kind':'file','ref':'plugin.py'}}], 'pipeline':{
                'inputs':[], 'outputs':[], 'nodes':[
                {'id':'start','type_used':'probe.start','display_name':'Start','description':'Starts.'},
                {'id':'task','type_used':'probe.task','display_name':'Task','description':'Exception probe.'},
                {'id':'end','type_used':'probe.start','display_name':'End','description':'Ends.'}],
                'edges':[['start','task'],['task','end']]}})
            statement = 'sink(alias)' if via_helper else 'alias.pop("seed", None)'
            body = 'alias = {}\ntry:\n' + indent(expression, '    ') + '\nexcept Exception:\n    ' + statement + '\nreturn {}\n'
            source = ('from vibeflow.targets.python.sdk import node\n'
                'def sink(payload):\n    payload.pop("seed", None)\n'
                'def noop():\n    raise ValueError("probe")\n'
                '@node(type_key="probe.task", rulesets=["probe.effects"], contract={})\n'
                'class Task:\n    def run_pure(self, inputs, params):\n' + indent(body, '        ') +
                '@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})\n'
                'class Start:\n    def run_pure(self, inputs, params):\n        return {}\n')
            compile(source, str(root / 'node_resource.py'), 'exec')
            (root / 'node_resource.py').write_text(source)
            (root / 'plugin.py').write_text('from vibeflow.targets.python.sdk import Plugin, ruleset\nfrom node_resource import Start, Task\n'
                'selected=ruleset(id="probe.effects", calls=[{"id":"effects","rule_id":"vibeflow.no_side_effects","params":{"effect_scope":"global_state"}}])\n'
                'plugin=Plugin(id="probe", resources=[Start, Task, selected], declaration_rulesets=[])\n')
            argv = ['validate','--workspace',str(root / 'vibeflow_config.jsonc'),'--config',str(root / 'workflow.jsonc'),'--json']
            proc = subprocess.run([sys.executable,'-I','-B','-c',bootstrap,str(args.product.resolve()),json.dumps(argv),str(root / 'origin.json')], cwd=root, capture_output=True, text=True, timeout=30)
            (root / 'stdout.json').write_text(proc.stdout)
            (root / 'stderr.txt').write_text(proc.stderr)
            payload = json.loads(proc.stdout)
            origin = json.loads((root / 'origin.json').read_text())
            assert not origin['foreign'], origin
            findings = [f for f in payload.get('errors', []) if 'mutate inputs' in f.get('message', '')]
            actual = bool(findings)
            rows.append({'case':label,'via_helper':via_helper,'expected':expected,'actual':actual,'matched':actual == expected,
                'status':payload.get('status'),'exit':proc.returncode,'findings':findings,'all_errors':payload.get('errors', []),
                'source':source,'origin':origin,'project':str(root)})
    report = {'count':len(rows),'mismatches':sum(not r['matched'] for r in rows),'rows':rows}
    write(args.report, report)
    print(json.dumps({k:report[k] for k in ('count','mismatches')}))


if __name__ == '__main__':
    main()
