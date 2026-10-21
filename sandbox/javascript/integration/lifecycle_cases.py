"""Application APIs are injected; explicit workflow Nodes establish/close them."""
from __future__ import annotations
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from sandbox_support import BuildCache, PROJECT_ROOT, run_browser_message_loop, run_node


_LIFECYCLE_SCRIPT = """
const afterImport = [...globalThis.__vibeflowSandboxHostCalls];
let active=false;
const math={
  open(){active=true;globalThis.__vibeflowSandboxHostCalls.push("open");return null;},
  double(value){if(!active)throw Error("math session is closed");return value*2;},
  close(){active=false;globalThis.__vibeflowSandboxHostCalls.push("close");return null;},
};
const answer=workflow.runWorkflow({x:8},{capabilities:{"sandbox.math_session":math}});
assert(answer.result===16,JSON.stringify(answer));
assert(JSON.stringify(afterImport)==="[]",JSON.stringify(afterImport));
assert(JSON.stringify(globalThis.__vibeflowSandboxHostCalls)==='["open","close"]',JSON.stringify(globalThis.__vibeflowSandboxHostCalls));
assert(!active,"workflow failed to close its API");
process.stdout.write(JSON.stringify({answer,afterImport,calls:globalThis.__vibeflowSandboxHostCalls}));
"""


def explicit_lifecycle_case(cache: BuildCache) -> dict[str, Any]:
    result=cache.build("explicit_lifecycle","explicit_lifecycle.jsonc")
    payload=run_node(result.entry,_LIFECYCLE_SCRIPT,before_import="globalThis.__vibeflowSandboxHostCalls=[];")
    assert "host_extensions" not in json.loads(result.manifest.read_text())["target_metadata"]
    return payload


def browser_message_loop_case(cache: BuildCache, *, puppeteer_root: Path, profile: str) -> dict[str, Any]:
    if profile=="web-app":
        result=cache.build("browser_message_loop_web","browser_message_loop.jsonc",target="browser",profile=profile,
            html_template=PROJECT_ROOT/"web/browser_session.template.html",app_entry=PROJECT_ROOT/"web/browser_session_app.ts")
        module_entry=None
    elif profile=="esm-module":
        result=cache.build("browser_message_loop_esm","browser_message_loop.jsonc",target="browser",profile=profile)
        shutil.copy2(PROJECT_ROOT/"web/browser_session.template.html",result.out_dir/"index.html")
        script='''import {createRequire} from "node:module";
const require=createRequire(process.argv[1]);
await require("esbuild").build({entryPoints:[process.argv[2]],outfile:process.argv[3],bundle:true,format:"esm",platform:"browser",logLevel:"silent"});'''
        subprocess.run(["node","--input-type=module","-e",script,str(PROJECT_ROOT/"package.json"),
            str(PROJECT_ROOT/"web/browser_session.ts"),str(result.out_dir/"session.mjs")],check=True,capture_output=True,text=True)
        module_entry=result.entry.name
    else:
        raise AssertionError("unsupported browser profile: "+profile)
    payload=run_browser_message_loop(result.out_dir,puppeteer_root=puppeteer_root,module_entry=module_entry)
    payload["profile"],payload["files"]=profile,list(result.files)
    return payload
