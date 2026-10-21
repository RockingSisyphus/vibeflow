"""The public TypeScript AOT build preserves scheduler-only call config."""

import json
import os
from pathlib import Path
import subprocess

from tests.fixtures.support.addition_sandboxes import cli, workspace


def test_public_typescript_build_runs_with_four_dispatch_slots(tmp_path):
    fixture = Path(__file__).resolve().parents[3] / "sandbox/javascript/graph_concurrency"
    toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
    config_workspace = workspace(fixture, tmp_path, toolchain)
    config = tmp_path / "project/configs/concurrent.jsonc"
    data = json.loads(config.read_text())
    data["pipeline"]["nodes"][0]["config"] = {"max_concurrency": 4}
    config.write_text(json.dumps(data))
    nodes = tmp_path / "project/nodes/steps.ts"
    nodes.write_text(nodes.read_text().replace("++started===12", "++started===4"))
    result = json.loads(cli(["build", "--workspace", config_workspace, "--config", config,
        "--out-dir", tmp_path / "built", "--target", "node", "--profile", "single-esm"]).stdout)
    probe = tmp_path / "probe.mjs"
    probe.write_text('import {runWorkflowAsync} from ' + json.dumps(Path(result["entry"]).as_uri()) + ''';
for(let round=0;round<2;round++) {
 let active=0,peak=0;
 const result=await runWorkflowAsync({scenario:'success'},{trace:'full',onTrace:event=>{
   if(event.kind==='node_trace' && event.event==='worker_started') {active++;peak=Math.max(peak,active);}
   if(event.kind==='node_trace' && event.event==='cleanup_finished') active--;
 }});
 if(JSON.stringify(result.report)!==JSON.stringify(Array.from({length:12},(_,i)=>i))) throw Error(JSON.stringify(result));
 if(peak!==4 || active!==0) throw Error('AOT dispatch capacity was lost: '+JSON.stringify({peak,active}));
}
console.log('PASS');
''')
    completed = subprocess.run(["node", str(probe)], capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "PASS"
