"""Build current-ABI SDK chains and measure fresh Runtime preparation."""
from pathlib import Path
import argparse
import cProfile
import json
import statistics
import sys
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))


def run(work, count, rounds):
    from vibeflow.block_compiler import WORKFLOW_ABI_VERSION
    from vibeflow.tooling.application.python.build import PythonBuildRequest, build_python_aot
    from vibeflow.tooling.application.python.bundle import load_bundle
    from vibeflow.tooling.project.workspace_loader import load_workspace_config

    workspace = work / f'chain-{count}'
    workspace.mkdir()
    project = workspace / 'project'
    project.mkdir()
    (workspace / 'vibeflow_config.jsonc').write_text(json.dumps({'roots': [{'id': 'probe', 'path': 'project'}]}))
    (project / 'vibeflow_project.jsonc').write_text('{"project_target":"python"}')
    (project / 'root_rules.jsonc').write_text('{"rulesets":[]}')
    (project / 'nodes').mkdir()
    (project / 'plugins/probe').mkdir(parents=True)
    source = ['from vibeflow.targets.python.sdk import Plugin,node,data_schema',
        '@node(node_type="vibeflow.node",id="boundary",flow_kind="terminal",contract={},rulesets=[])',
        'class Boundary:', ' def run_pure(self,inputs,params):return {}']
    for index in range(count):
        contract = {'requires': [{'type': f'value.{index}', 'cardinality': 'exactly_one', 'display_name': 'Input'}],
            'provides': [{'key': f'result{index}', 'type': f'value.{index+1}', 'display_name': 'Result'}],
            'input_semantics': {f'value.{index}': ['Previous result']},
            'output_semantics': {f'result{index}': ['Add one']}}
        source.extend([f'@node(node_type="vibeflow.node",id="step{index}",contract={contract!r},rulesets=[])',
            f'class Step{index}:', f' def run_pure(self,inputs,params):return {{"result{index}":inputs["value.{index}"]["value"]+1}}'])
    (project / 'plugins/probe/plugin.py').write_text('from vibeflow.targets.python.sdk import Plugin,data_schema\nplugin=Plugin(id="probe",resources=[data_schema(type_key=f"value.{i}",schema={"type":"number"}) for i in range(' + str(count+1) + ')])')
    (project / 'nodes/steps.py').write_text('\n'.join(source))
    ids = ['start', *[f'step{i}' for i in range(count)], 'end']
    config = project / 'workflow.jsonc'
    config.write_text(json.dumps({'plugins': [{'source': {'kind': 'file', 'ref': 'plugins/probe/plugin.py'}}], 'rulesets': [], 'pipeline': {
        'inputs': [{'key': 'number', 'type': 'value.0', 'required': True, 'display_name': 'Number'}],
        'outputs': [{'type': f'value.{count}', 'as': 'number', 'cardinality': 'exactly_one', 'display_name': 'Result'}],
        'nodes': [{'id': key, 'definition_id': 'boundary' if key in {'start', 'end'} else key,
                   'display_name': key, 'description': 'Current SDK chain'} for key in ids],
        'edges': [ids[i:i+2] for i in range(len(ids)-1)]}}))
    built = build_python_aot(PythonBuildRequest(load_workspace_config(workspace / 'vibeflow_config.jsonc'),
        config, work / f'built-{count}', preview_root=work / 'preview'))
    started = time.perf_counter()
    bundle = load_bundle(built.out_dir)
    load_ms = (time.perf_counter()-started)*1000

    def call(value):
        started = time.perf_counter()
        runtime = bundle.create_runtime(run_dir=work / 'runs' / uuid.uuid4().hex,
            runtime_options={'execution': 'compiled', 'trace': 'off'})
        prepared = time.perf_counter()
        result = runtime.run({'number': value})
        ended = time.perf_counter()
        assert result.get('number')['value'] == value+count
        return {'prepare_ms': (prepared-started)*1000, 'run_ms': (ended-prepared)*1000,
                'total_ms': (ended-started)*1000}

    call(0)
    profile = cProfile.Profile()
    profile.enable()
    for index in range(5):
        call(index)
    profile.disable()
    measured = {'_descriptor', '_registry', 'bindings', 'decode_resource', 'bind_python_workflow'}
    counts = [{'function': row.code.co_name, 'calls': row.callcount} for row in profile.getstats()
              if not isinstance(row.code, str) and row.code.co_name in measured]
    samples = [call(index) for index in range(rounds)]
    return {'abi': WORKFLOW_ABI_VERSION, 'node_definitions': count+1, 'load_ms': load_ms,
        'runtime_instances_reused': False, 'profile_counts': counts, 'samples': samples,
        'medians_ms': {key: statistics.median(row[key] for row in samples) for key in samples[0]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nodes', type=int, nargs='+', default=[1, 32, 138])
    parser.add_argument('--rounds', type=int, default=20)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.rounds < 1 or any(count < 1 for count in args.nodes):
        parser.error('nodes and rounds must be positive')
    with tempfile.TemporaryDirectory(prefix='python-aot-preparation-') as name:
        rows = [run(Path(name), count, args.rounds) for count in args.nodes]
    report = {'scope': 'Current SDK chains; separate profiling and latency samples; no old bundle compatibility.', 'rows': rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
