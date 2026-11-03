"""The same ordinary cooperative application in Node and a real browser UI."""
import json
import shutil

import pytest

from .cooperation import CASES, FAULTS, prepare, set_fault, verify_rows, verify_cancelled
from .support import ROOT, cli, command, write


@pytest.fixture(scope="module")
def cooperative_application(tmp_path_factory,toolchain):
    work=tmp_path_factory.mktemp("cooperative-javascript")
    output=prepare(ROOT / "sandbox/javascript/workflow_cooperation_math",work,"javascript",toolchain)
    modules={}
    for name in ("a","b","c",*FAULTS):
        if name in FAULTS:set_fault(work,"javascript",name)
        built=cli(work,"build","--workspace",work / "vibeflow_config.jsonc","--config",
            work / f"project/configs/{'a' if name in FAULTS else name}.jsonc","--out-dir",output / name,
            "--target","browser","--profile","single-esm")
        modules[name]=json.loads(built.stdout)["entry"]
    imports="\n".join(f"import * as {name} from {json.dumps(path)};" for name,path in modules.items())
    coordinator=(ROOT / "src/vibeflow/targets/javascript/resources/coordination/coordinator.mjs").as_posix()
    entry=write(output / "application.mjs",imports+f'''
import {{Coordinator}} from {json.dumps(coordinator)};
import {{verify}} from {json.dumps((ROOT / "tests/e2e/applications/cooperation.mjs").as_posix())};
const execute=()=>verify(Coordinator,{{{','.join(modules)}}},{json.dumps(CASES)},{json.dumps(FAULTS)});
if(typeof document==="undefined"){{execute().then(value=>console.log(JSON.stringify(value))).catch(error=>{{console.error(error);process.exitCode=1;}});}}
else document.querySelector('#run').addEventListener('click',async()=>{{
 const result=document.querySelector('#result');
 try{{result.textContent=JSON.stringify(await execute());}}catch(error){{result.textContent=JSON.stringify({{error:error.message}});}}
}});
''')
    bundle=output / "application.js"
    command("node","-e","require(process.argv[1]).buildSync(JSON.parse(process.argv[2]))",
        toolchain / "node_modules/esbuild",json.dumps({"entryPoints":[str(entry)],"bundle":True,
            "platform":"browser","format":"iife","outfile":str(bundle)}),cwd=work)
    html=write(output / "index.html",'<meta charset="utf-8"><button id="run">计算协作公式</button><pre id="result"></pre><script src="application.js"></script>')
    shutil.rmtree(work / "project")
    return bundle,html,work


@pytest.mark.parametrize("environment",["node","browser"])
def test_cooperative_application(cooperative_application,browser_runtime,environment):
    bundle,html,work=cooperative_application
    if environment=="node":result=command("node",bundle,cwd=work)
    else:result=command("node",ROOT / "tests/e2e/browser/application.cjs",browser_runtime / "package.json",html,cwd=work)
    report=json.loads(result.stdout)
    verify_rows(report["rows"])
    verify_cancelled(report["cancelled"])
    assert {item["fault"]:item["observed"] for item in report["controls"]}==FAULTS,report
