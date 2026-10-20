"""Build real JS AOT chains and inspect per-invocation versus module preparation."""
from pathlib import Path
import argparse
import json
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))


def run(work, toolchain, count, rounds):
    from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot
    project = work / f'chain-{count}'
    project.mkdir()
    (project / 'node_modules').symlink_to(toolchain / 'node_modules', target_is_directory=True)
    (project / 'package.json').write_text('{"name":"aot-preparation-probe","private":true,"type":"module"}')
    shutil.copy2(ROOT / 'sandbox/javascript/minimal/project/package-lock.json', project / 'package-lock.json')
    (project / 'vibeflow_config.jsonc').write_text(json.dumps({'roots': [{'id': 'probe', 'path': '.'}]}))
    (project / 'vibeflow_project.jsonc').write_text(json.dumps({'project_target': 'javascript',
        'javascript': {'package_root': '.'}, 'quality_enabled': False}))
    source = ['import {defineNode,definePlugin,defineDataSchema} from "@vibeflow/plugin";',
        'export const boundary=defineNode({type_key:"probe.boundary",flow_kind:"terminal",contract:{},rulesets:[],run(){return {};}});']
    for i in range(count+1):
        source.append(f'export const schema{i}=defineDataSchema({{type_key:"value.{i}",schema:{{type:"number"}}}});')
    for i in range(count):
        contract = {'requires': [{'type': f'value.{i}', 'display_name': 'Input', 'cardinality': 'exactly_one'}],
            'provides': [{'key': f'result{i}', 'type': f'value.{i+1}', 'display_name': 'Result'}],
            'input_semantics': {f'value.{i}': ['Previous result']}, 'output_semantics': {f'result{i}': ['Add one']}}
        source.append(f'export const step{i}=defineNode({{type_key:"probe.step{i}",contract:{json.dumps(contract)},'
            f'rulesets:[],run(inputs,params){{return {{result{i}:Number(inputs["value.{i}"].value)+1}};}}}});')
    resources = ['boundary', *[f'schema{i}' for i in range(count+1)], *[f'step{i}' for i in range(count)]]
    source.append('export const plugin=definePlugin({id:"probe",resources:[' + ','.join(resources) + ']});')
    (project / 'plugin.ts').write_text('\n'.join(source))
    config = {'plugins': [{'source': {'kind': 'file', 'ref': 'plugin.ts'}}], 'rulesets': [], 'pipeline': {
        'inputs': [{'key': 'number', 'type': 'value.0', 'display_name': 'Input', 'required': True}],
        'outputs': [{'type': f'value.{count}', 'as': 'number', 'display_name': 'Result', 'cardinality': 'exactly_one'}],
        'nodes': [{'id': 'start', 'type_used': 'probe.boundary', 'display_name': 'Start', 'description': 'Enter chain'},
            *[{'id': f'step{i}', 'type_used': f'probe.step{i}', 'display_name': f'Step {i}', 'description': 'Add one'} for i in range(count)],
            {'id': 'end', 'type_used': 'probe.boundary', 'display_name': 'End', 'description': 'Exit chain'}],
        'edges': [['start', 'step0'], *[[f'step{i}', f'step{i+1}'] for i in range(count-1)], [f'step{count-1}', 'end']]}}
    (project / 'workflow.jsonc').write_text(json.dumps(config))
    built = build_project_aot(ProjectBuildRequest(workspace=project / 'vibeflow_config.jsonc',
        config=project / 'workflow.jsonc', out_dir=work / f'built-{count}', target='node', profile='single-esm',
        preview_root=work / 'preview'))
    entry = Path(built.build.entry)
    completed = subprocess.run(['node', str(Path(__file__).with_name('measure.mjs')), str(entry), str(count), str(rounds)],
        cwd=work, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return json.loads(completed.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain-root', type=Path, required=True)
    parser.add_argument('--nodes', type=int, nargs='+', default=[1, 32, 138])
    parser.add_argument('--rounds', type=int, default=100)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='javascript-aot-preparation-') as name:
        rows = [run(Path(name), args.toolchain_root.resolve(), n, args.rounds) for n in args.nodes]
    report = {'scope': 'Real SDK chain builds; not a port of the supervisor workload, no cross-language latency ratio.', 'rows': rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
