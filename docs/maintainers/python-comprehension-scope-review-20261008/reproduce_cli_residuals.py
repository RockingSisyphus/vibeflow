"""Validate synthetic projects only; compare source and selected archives."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from textwrap import indent


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--product', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    args = p.parse_args()
    repo = Path(__file__).resolve().parents[3]
    builder = repo / 'dist/python-comprehension-scope-validation-20261008/comprehension_cli_probe.py'
    spec = importlib.util.spec_from_file_location('cli_fixture_builder', builder)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    cases = []
    for kind in ('node', 'base_lib', 'plugin'):
        for target in ('sys', 'item'):
            cases.append((kind, 'alias_escape_' + target, 'none',
                          '(list(alias := ' + target + ' for ' + target + ' in ()), alias.argv)', False, None))
    for declaration in ('nonlocal', 'global'):
        for via_helper in (False, True):
            body = ('alias = {}\n' if declaration == 'nonlocal' else '')
            body += 'def inner():\n    ' + declaration + ' alias\n    alias = inputs\ninner()\n'
            body += 'sink(alias)\n' if via_helper else 'alias.pop("seed", None)\n'
            cases.append(('node', declaration + ('_helper' if via_helper else '_direct'), 'global_state', 'None', True, body))
    rows = []
    bootstrap = ('import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);'
        'from vibeflow.tooling.application.python.cli import main;code=main(json.loads(sys.argv[2]));'
        'modules={n:str(getattr(m,"__file__","")) for n,m in sys.modules.items() if n=="vibeflow" or n.startswith("vibeflow.")};'
        'expected=str(Path(sys.argv[1])/"vibeflow")+"/";'
        'Path(sys.argv[3]).write_text(json.dumps({"origin":modules["vibeflow"],"foreign":{n:v for n,v in modules.items() if not v.startswith(expected)}}));raise SystemExit(code)')
    for kind, label, scope, expression, expected, body in cases:
        root = args.work.resolve() / (kind + '.' + label)
        offender = helper.project(root, kind, label, scope, expression, 'input' if body else 'host')
        if body:
            text = offender.read_text()
            text = text.replace('        fn = lambda: None\n        fn()\n', indent(body, '        '))
            text = 'def sink(payload):\n    payload.pop("seed", None)\n' + text
            offender.write_text(text)
        argv = ['validate', '--workspace', str(root / 'vibeflow_config.jsonc'), '--config', str(root / 'workflow.jsonc'), '--json']
        proc = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, str(args.product.resolve()), json.dumps(argv), str(root / 'origin.json')], cwd=root, capture_output=True, text=True, timeout=30)
        (root / 'stdout.json').write_text(proc.stdout)
        (root / 'stderr.txt').write_text(proc.stderr)
        payload = json.loads(proc.stdout)
        findings = helper.findings(payload)
        origin = json.loads((root / 'origin.json').read_text())
        assert not origin['foreign'], origin
        actual = any('mutate inputs' in f['message'] for f in findings) if body else bool(findings)
        rows.append({'case':label, 'kind':kind, 'expected':expected, 'actual':actual,
            'matched':actual == expected, 'exit':proc.returncode, 'status':payload.get('status'),
            'source':offender.read_text(), 'findings':findings, 'origin':origin, 'project':str(root)})
    report = {'count':len(rows), 'mismatches':sum(not x['matched'] for x in rows), 'rows':rows}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:report[k] for k in ('count','mismatches')}))


if __name__ == '__main__':
    main()
