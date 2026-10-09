"""Read-only native JS Rule driver and local lock-policy observations."""
import argparse
import json
from pathlib import Path
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from vibeflow.targets.javascript.build.toolchain import AotToolchainError, probe_toolchain, run_rule_check_driver
    cases = (
        ('math_static_control', 'Math.max(1, 2)', 'none'),
        ('math_computed_member', 'Math[params.operation](1, 2)', 'none'),
        ('current_time', 'Date.now()', 'none'),
        ('current_time_io_control', 'Date.now()', 'python_io'),
        ('random', 'Math.random()', 'none'),
    )
    rows = []
    for label, expression, scope in cases:
        root = args.work.resolve() / label
        root.mkdir(parents=True)
        source = root / 'node.ts'
        source.write_text('export function run(inputs: object, params: any){const value = ' + expression + ';return {}; }\n')
        request = {'typecheckFiles':[str(source)],'ruleTopics':['host_io'],'ruleParams':{'effect_scope':scope},
            'ruleSubjectId':'probe.task','ruleSubjectKind':'node', 'importPolicy':{
                'owners':[{'path':str(source),'kind':'node','id':'probe.task','export':'run'}]}}
        result = run_rule_check_driver(request, package_root=args.package_root.resolve())
        rows.append({'case':label, 'scope':scope, 'findings':list(result.findings), 'source':source.read_text()})
    locks = []
    for label, files in (('no_lock', {}),('yarn_lock',{'yarn.lock':''}),
                         ('two_locks',{'package-lock.json':'{}','yarn.lock':''})):
        root = args.work.resolve() / label
        root.mkdir(parents=True)
        (root / 'package.json').write_text('{}')
        for name, text in files.items():
            (root / name).write_text(text)
        try:
            probe_toolchain(root, node_command='vibeflow-boundary-probe-no-such-node')
        except AotToolchainError as error:
            locks.append({'case':label, 'code':error.code, 'message':str(error)})
        else:
            raise AssertionError(label)
    data = {'driver_cases':rows, 'lock_api_cases':locks,
        'scope':'Native Rule driver only; lock cases invoke API before real toolchain. No JS business function executed.'}
    args.report.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'js':[{ 'case':row['case'], 'codes':[f['code'] for f in row['findings']]} for row in rows], 'locks':locks},ensure_ascii=False))

if __name__ == '__main__':
    main()
