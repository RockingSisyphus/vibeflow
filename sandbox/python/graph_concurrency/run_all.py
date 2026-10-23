"""Public CLI and AOT bundle acceptance for ordinary graph concurrency."""
from pathlib import Path
import asyncio
import json
import sys
sys.dont_write_bytecode=True
FIXTURE=Path(__file__).resolve().parent
ROOT=FIXTURE.parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.addition_sandboxes import cli,workspace,main
from tests.fixtures.support.graph_concurrency import (
    SUCCESS_CASES, assert_worker_trace, check_topology_cases, write_cases,
)
from vibeflow.tooling.application.python.build import PythonBuildRequest,build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def run(work,*,toolchain=None):
    workspace(FIXTURE,work)
    output = artifact_directory(work)
    write_cases(work)
    rows=check_topology_cases(work)
    for name,scenario,capacity in SUCCESS_CASES:
        config=work/f'project/configs/{name}.jsonc'
        input_file=work/f'{name}-input.json';input_file.write_text(json.dumps({'scenario':scenario}))
        for execution in ('plan','block','compiled'):
            run_id=f'{name}-{execution}'
            result=json.loads(cli(['run','--workspace',work/'vibeflow_config.jsonc','--config',config,
                '--input',input_file,'--execution',execution,'--run-root',output/'runs','--run-id',run_id]).stdout)
            assert result['status'] in ('PASS','CONCERNS'),result
            trace=[json.loads(line) for line in (output/'runs'/run_id/'runtime_trace.jsonl').read_text().splitlines()]
            rows.append({'case':name,'execution':execution,'status':'PASS',
                **assert_worker_trace(trace,capacity)})
        build_python_aot(PythonBuildRequest(work/'vibeflow_config.jsonc',config,output/f'{name}-bundle'))
        bundle=load_bundle(output/f'{name}-bundle')
        rounds=[]
        for _ in range(2):
            result=asyncio.run(bundle.run_async({'scenario':scenario},run_root=output/'aot-runs',runtime_options={'trace':'full'}))
            assert result.context.get('report')['value']==list(range(12))
            trace=[json.loads(line) for line in (result.run_dir/'runtime_trace.jsonl').read_text().splitlines()]
            rounds.append(assert_worker_trace(trace,capacity))
        rows.append({'case':name,'execution':'aot','status':'PASS','rounds':rounds})
    return {'status':'PASS','observations':rows}


if __name__=='__main__':main(run,'Python ordinary graph concurrency')
