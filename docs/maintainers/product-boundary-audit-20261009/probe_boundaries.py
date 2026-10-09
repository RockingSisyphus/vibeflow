"""Independent product-boundary examples through SDK -> selected Rules -> CLI.

Only validates declarations and source; never invokes the business Node.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from textwrap import indent

CASES = (
    ("literal_control", "return {}", "", "", "none", "effects"),
    ("bounded_while", "i = 0\nwhile i < 3:\n    i += 1\nreturn {}", "", "", "none", "effects"),
    ("bounded_for_control", "i = 0\nfor value in (0, 1, 2):\n    i += value\nreturn {}", "", "", "none", "effects"),
    ("scalar_client_field", "return {}", "", "def __init__(self):\n    self.client = 1\n", "none", "effects"),
    ("scalar_value_field_control", "return {}", "", "def __init__(self):\n    self.value = 1\n", "none", "effects"),
    ("owned_object_attribute", "box = Box()\nbox.count = 1\nreturn {}", "class Box:\n    pass\n", "", "none", "effects"),
    ("owned_object_setattr", "box = Box()\nsetattr(box, 'count', 1)\nreturn {}", "class Box:\n    pass\n", "", "none", "effects"),
    ("helper_return", "return result()", "def result():\n    return {}\n", "", "none", "effects"),
    ("local_dict_return_control", "result = {}\nreturn result", "", "", "none", "effects"),
    ("ffi_import_in_io", "import ctypes\nreturn {}", "", "", "python_io", "effects"),
    ("memory_buffer_write", "import io\nbuffer = io.StringIO()\nbuffer.write('text')\nreturn {}", "", "", "none", "effects"),
    ("algorithm_recursion", "value = self._factorial(3)\nreturn {}", "", "def _factorial(self, n):\n    return 1 if n <= 1 else n * self._factorial(n - 1)\n", "none", "maintainability"),
    ("literal_return_with_interface", "return {}", "", "", "none", "interface"),
)

def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    product = args.product.resolve()
    bootstrap = ('import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
        'from vibeflow.tooling.application.python.cli import main;code=main(json.loads(sys.argv[2]));'
        'mods={n:str(getattr(m,"__file__","")) for n,m in sys.modules.items() if n=="vibeflow" or n.startswith("vibeflow.")};'
        'expected=str(Path(sys.argv[1])/"vibeflow")+"/";'
        'Path(sys.argv[3]).write_text(json.dumps({"origin":mods["vibeflow"],"foreign":{n:v for n,v in mods.items() if not v.startswith(expected)}}));raise SystemExit(code)')
    rows = []
    for label, body, helpers, extra_methods, scope, rule in CASES:
        root = args.work.resolve() / label
        root.mkdir(parents=True)
        write_json(root / 'vibeflow_config.jsonc', {'roots': [{'id':'probe', 'path':'.'}]})
        write_json(root / 'vibeflow_project.jsonc', {'project_target':'python'})
        write_json(root / 'workflow.jsonc', {'plugins':[{'source':{'kind':'file','ref':'plugin.py'}}], 'pipeline':{
            'inputs':[], 'outputs':[], 'nodes':[
                {'id':'start','type_used':'probe.start','display_name':'Start','description':'Start.'},
                {'id':'task','type_used':'probe.task','display_name':'Task','description':'Boundary probe.'},
                {'id':'end','type_used':'probe.start','display_name':'End','description':'End.'}],
            'edges':[['start','task'],['task','end']]}})
        source = ('from vibeflow.targets.python.sdk import node\n' + helpers +
            '@node(type_key="probe.task", rulesets=["probe.selected"], contract={})\n'
            'class Task:\n' + indent(extra_methods, '    ') +
            '    def run_pure(self, inputs, params):\n' + indent(body, '        ') + '\n'
            '@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})\n'
            'class Start:\n    def run_pure(self, inputs, params):\n        return {}\n')
        compile(source, str(root / 'node_resource.py'), 'exec')
        (root / 'node_resource.py').write_text(source)
        rule_id = {'effects':'vibeflow.no_side_effects','maintainability':'vibeflow.maintainability','interface':'vibeflow.node_interface'}[rule]
        call = {'id':'selected','rule_id':rule_id}
        if rule == 'effects':
            call['params'] = {'effect_scope':scope}
        (root / 'plugin.py').write_text('from vibeflow.targets.python.sdk import Plugin, ruleset\nfrom node_resource import Start, Task\n'
            + 'selected = ruleset(id="probe.selected", calls=' + repr([call]) + ')\n'
            + 'plugin = Plugin(id="probe", resources=[Start, Task, selected], declaration_rulesets=[])\n')
        argv = ['validate','--workspace',str(root / 'vibeflow_config.jsonc'),'--config',str(root / 'workflow.jsonc'),'--json']
        proc = subprocess.run([sys.executable,'-I','-B','-c',bootstrap,str(product),json.dumps(argv),str(root / 'origin.json')],
            cwd=root, capture_output=True, text=True, timeout=30)
        (root / 'stdout.json').write_text(proc.stdout)
        (root / 'stderr.txt').write_text(proc.stderr)
        payload = json.loads(proc.stdout)
        origin = json.loads((root / 'origin.json').read_text())
        assert not origin['foreign'], origin
        rows.append({'case':label,'source':source,'rule':rule_id,'scope':scope,'status':payload.get('status'),
            'exit':proc.returncode,'errors':payload.get('errors',[]),'warnings':payload.get('warnings',[]),
            'origin':origin,'project':str(root)})
    write_json(args.report, {'count':len(rows),'rows':rows})
    print(json.dumps([{'case':row['case'],'status':row['status'],'codes':[item.get('code',item.get('rule_id')) for item in row['errors']]} for row in rows], ensure_ascii=False))

if __name__ == '__main__':
    main()
