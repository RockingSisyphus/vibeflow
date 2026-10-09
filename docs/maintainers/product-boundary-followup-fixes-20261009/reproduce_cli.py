"""Formal CLI before/after observations plus safe Python mutation witnesses."""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import subprocess
import sys
from textwrap import indent


GLOBAL = {
    'global_for': 'for VERSION in [2]:\n    pass',
    'global_for_unpack': 'for VERSION, local in [(2, 3)]:\n    pass',
    'global_with': 'with nullcontext(2) as VERSION:\n    pass',
    'global_import': 'import math as VERSION',
    'global_from_import': 'from math import pi as VERSION',
    'global_definition': 'def VERSION():\n    return 2',
    'global_async_definition': 'async def VERSION():\n    return 2',
    'global_class': 'class VERSION:\n    pass',
    'global_except': 'try:\n    raise ValueError()\nexcept ValueError as VERSION:\n    pass',
    'global_match': 'match 2:\n    case VERSION:\n        pass',
    'global_comprehension_walrus': '[(VERSION := item) for item in [2]]',
}
BRANCH = {
    'if_else_original_input': "if params:\n    inputs = {}\nelse:\n    inputs['x'] = 1",
    'if_else_original_alias': "alias = inputs\nif params:\n    alias = {}\nelse:\n    alias['x'] = 1",
    'expression_else_original_input': '(inputs := {}) if params else inputs.update(x=1)',
    'match_original_input': "match params:\n    case 1:\n        inputs = {}\n    case _:\n        inputs['x'] = 1",
    'except_original_input': "try:\n    value = params['x']\nexcept ValueError:\n    inputs = {}\nexcept KeyError:\n    inputs['x'] = 1",
}
POSITIVE = {
    'global_comprehension_local': ('effects', 'global VERSION\nvalue = [VERSION for VERSION in [2]]'),
    'global_readonly': ('effects', 'global VERSION\nvalue = VERSION'),
    'local_definition': ('effects', 'def VERSION():\n    return 2'),
    'condition_rebind_both_branches': ('input', "if (inputs := {}):\n    inputs['x'] = 1\nelse:\n    inputs['x'] = 1"),
    'conditional_rebind_unknown_afterwards': ('input', "if params:\n    inputs = {}\ninputs['x'] = 1"),
    'match_guard_rebind': ('input', "match params:\n    case 1 if (inputs := {}):\n        pass\n    case _:\n        inputs['x'] = 1"),
    'exception_type_rebind': ('input', "try:\n    raise KeyError()\nexcept ((inputs := {}) or ValueError):\n    pass\nexcept KeyError:\n    inputs['x'] = 1"),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--witnesses', type=Path)
    args = parser.parse_args()
    evidence = Path(__file__).resolve().parent
    original = evidence.parent / 'product-boundary-remediation-review-20261009/fixtures/cli'
    cases = {key: ('effects', 'global VERSION\n' + body, True) for key, body in GLOBAL.items()}
    cases.update({key: ('input', body, True) for key, body in BRANCH.items()})
    cases.update({key: (kind, body, False) for key, (kind, body) in POSITIVE.items()})
    observations = []
    bootstrap = ('import sys,json;sys.path.insert(0,sys.argv[1]);'
                 'from vibeflow.tooling.application.python.cli import main;'
                 'raise SystemExit(main(json.loads(sys.argv[2])))')
    for name, (kind, body, denied) in cases.items():
        root = evidence / 'fixtures' / name
        template = original / ('actual_global_write' if kind == 'effects' else 'direct_write_in_branch')
        root.mkdir(parents=True, exist_ok=True)
        for filename in ('plugin.py', 'vibeflow_config.jsonc', 'vibeflow_project.jsonc', 'workflow.jsonc'):
            shutil.copyfile(template / filename, root / filename)
        text = ('from vibeflow.targets.python.sdk import node\nfrom contextlib import nullcontext\nVERSION = 1\n'
                '@node(type_key="probe.task", rulesets=["probe.selected"], contract={})\n'
                'class Task:\n    def run_pure(self, inputs, params):\n' + indent(body + '\nreturn {}', '        ')
                + '\n@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})\n'
                'class Start:\n    def run_pure(self, inputs, params):\n        return {}\n')
        compile(text, str(root / 'node_resource.py'), 'exec')
        (root / 'node_resource.py').write_text(text)
        argv = ['validate', '--workspace', str(root / 'vibeflow_config.jsonc'),
                '--config', str(root / 'workflow.jsonc'), '--json']
        result = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap,
                                 str(args.product.resolve()), json.dumps(argv)],
                                cwd=root, capture_output=True, text=True, timeout=30)
        payload = json.loads(result.stdout)
        observations.append({'case': name, 'expected_rejected': denied, 'exit': result.returncode,
                             'status': payload.get('status'),
                             'codes': [item.get('code', item.get('rule_id')) for item in payload.get('errors', ())]})
    args.report.write_text(json.dumps(observations, ensure_ascii=False, indent=2) + '\n')
    if args.witnesses:
        witnesses = []
        for name, binding in GLOBAL.items():
            namespace = {'VERSION': 1, 'nullcontext': nullcontext}
            exec(compile('def helper():\n' + indent('global VERSION\n' + binding, '    '), name, 'exec'), namespace)
            namespace['helper']()
            changed = 'VERSION' not in namespace or namespace['VERSION'] != 1
            assert changed, name
            witnesses.append({'case': name, 'actual_module_binding_changed': changed})
        for name, body in BRANCH.items():
            namespace = {}
            exec(compile('def helper(inputs, params):\n' + indent(body, '    '), name, 'exec'), namespace)
            inputs = {}
            namespace['helper'](inputs, {} if name == 'except_original_input' else False)
            assert inputs == {'x': 1}, name
            witnesses.append({'case': name, 'actual_original_input_mutated': True})
        for name in ('match_guard_rebind', 'exception_type_rebind'):
            body = POSITIVE[name][1]
            namespace = {}
            exec(compile('def helper(inputs, params):\n' + indent(body, '    '), name, 'exec'), namespace)
            inputs = {}
            namespace['helper'](inputs, 1)
            assert inputs == {}, name
            witnesses.append({'case': name, 'actual_original_input_unmodified': True})
        args.witnesses.write_text(json.dumps(witnesses, indent=2) + '\n')
    print(json.dumps({'cases': len(observations), 'rejected': sum(bool(x['exit']) for x in observations)}))


if __name__ == '__main__':
    main()
