"""Hold independent Capability calls, then exercise a permanent Port Host."""
from pathlib import Path
import json
import sys
sys.dont_write_bytecode = True

FIXTURE = Path(__file__).resolve().parent
REPOSITORY = FIXTURE.parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src"), str(REPOSITORY / "sandbox/javascript/integration")]
from tests.fixtures.support.addition_sandboxes import main, workspace
from sandbox_support import run_node
from vibeflow.targets.javascript.build.driver_session import check_scope
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot


@check_scope
def run(work, *, toolchain=None):
    workspace_path = workspace(FIXTURE, work, toolchain)
    def build(name, target="node", profile="single-esm"):
        return build_project_aot(ProjectBuildRequest(workspace=workspace_path, config=work / "project/configs" / (name + ".jsonc"), out_dir=work / (name + "-" + target), target=target, profile=profile))
    driver = json.dumps((FIXTURE / "scenario_driver.mjs").as_uri())
    finite = build("finite")
    first = run_node(finite.entry, f'import {{finite}} from {driver}; const result=await finite(workflow); process.stdout.write(JSON.stringify(result));')
    stream = build("stream")
    browser = build("stream", "browser", "esm-module")
    assert browser.files and browser.entry.is_file()
    manifest = json.loads(stream.manifest.read_text())
    assert manifest["host_extensions"] == ["addition.port_host"]
    second = run_node(stream.entry, f'import {{stream}} from {driver}; const result=await stream(workflow,globalThis.__vibeflowSandboxPortState); process.stdout.write(JSON.stringify(result));', before_import='''
let waiting;
globalThis.__vibeflowSandboxPortState={inputs:[{a:2,b:3},{a:10,b:20}],received:[],sent:[],calls:[],waitingReady:new Promise(resolve=>{waiting=resolve;}),resolveWaiting:()=>waiting()};
''')
    return {"status": "PASS", "observations": [{"case": "finite", **first}, {"case": "stream", "browserFiles": list(browser.files), **second}]}


if __name__ == "__main__":
    main(run, "JavaScript async addition", javascript=True)
