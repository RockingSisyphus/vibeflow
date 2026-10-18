"""Public CLI and AOT bundle acceptance for ordinary graph concurrency."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode=True
FIXTURE=Path(__file__).resolve().parent
ROOT=FIXTURE.parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from tests.fixtures.support.addition_sandboxes import cli,workspace,main
from vibeflow.tooling.application.python.build import PythonBuildRequest,build_python_aot
from vibeflow.tooling.application.python.bundle import load_bundle


def run(work,*,toolchain=None):
    workspace(FIXTURE,work)
    config=work/'project/configs/concurrent.jsonc'
    input_file=work/'input.json';input_file.write_text(json.dumps({'scenario':'success'}))
    rows=[]
    for execution in ('plan','block','compiled'):
        result=json.loads(cli(['run','--workspace',work/'vibeflow_config.jsonc','--config',config,
            '--input',input_file,'--execution',execution,'--run-root',work/'runs','--run-id',execution]).stdout)
        assert result['status'] in ('PASS','CONCERNS'),result
        trace=[json.loads(line) for line in (work/'runs'/execution/'runtime_trace.jsonl').read_text().splitlines()]
        assert sum(item['kind']=='worker_started' for item in trace)==12
        assert sum(item['kind']=='cleanup_finished' for item in trace)==12
        rows.append({'execution':execution,'status':'PASS','workers':12})
    build_python_aot(PythonBuildRequest(work/'vibeflow_config.jsonc',config,work/'bundle'))
    result=load_bundle(work/'bundle').run({'scenario':'success'},run_root=work/'aot-runs')
    assert result.context.get('report')['value']==list(range(12))
    rows.append({'execution':'aot','status':'PASS','workers':12})
    return {'status':'PASS','observations':rows}


if __name__=='__main__':main(run,'Python ordinary graph concurrency')
