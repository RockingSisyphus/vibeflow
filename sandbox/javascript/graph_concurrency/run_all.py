"""Public CLI rejection and Node/Chromium acceptance for ordinary concurrency."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import argparse
import json
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
FIXTURE = Path(__file__).resolve().parent
ROOT = FIXTURE.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from tests.fixtures.support.artifacts import artifact_directory
from tests.fixtures.support.addition_sandboxes import cli, workspace
from tests.fixtures.support.graph_concurrency import (
    SUCCESS_CASES, assert_worker_trace, check_topology_cases, write_cases,
)


def summarize(work, name, execution, rounds, capacity):
    (work / f"{name}-{execution}-trace.json").write_text(json.dumps(rounds, indent=2) + "\n")
    return {"case": name, "execution": execution, "status": "PASS", "rounds": [
        {"outputs": row["outputs"], **assert_worker_trace(row["trace"], capacity)} for row in rounds]}


def run(work, toolchain, puppeteer=None):
    workspace(FIXTURE, work, toolchain)
    output = artifact_directory(work)
    write_cases(work)
    observations = check_topology_cases(work)
    browser_cases = []
    for name, scenario, capacity in SUCCESS_CASES:
        def build(target):
            result = json.loads(cli(["build", "--workspace", work / "vibeflow_config.jsonc",
                "--config", work / f"project/configs/{name}.jsonc", "--out-dir", output / f"{name}-{target}",
                "--target", target, "--profile", "single-esm"]).stdout)
            entry = Path(result["entry"])
            assert entry.is_file(), entry
            return entry

        entry = build("node")
        script = work / f"{name}-probe.mjs"
        script.write_text('import {verify} from ' + json.dumps((FIXTURE / "verify.mjs").as_uri()) + ';\n'
            + 'const module=await import(' + json.dumps(entry.as_uri()) + ');\n'
            + 'console.log(JSON.stringify(await verify(module,' + json.dumps(scenario) + ')));\n')
        done = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=30, cwd=work)
        assert done.returncode == 0, done.stdout + done.stderr
        observations.append(summarize(work, name, "node", json.loads(done.stdout), capacity))
        if puppeteer:
            browser_cases.append({"name": name, "scenario": scenario, "capacity": capacity,
                "entry": '/' + build("browser").relative_to(work).as_posix()})

    if puppeteer:
        shutil.copy2(FIXTURE / "verify.mjs", work / "verify.mjs")
        (work / "index.html").write_text('<!doctype html><title>Graph concurrency acceptance</title>')

        class Assets(SimpleHTTPRequestHandler):
            extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.js': 'text/javascript'}

            def log_message(self, *_args):
                pass

        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Assets, directory=str(work)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = work / "browser.mjs"
            script.write_text('''import {createRequire} from "node:module";
import {pathToFileURL} from "node:url";
const require=createRequire(''' + json.dumps(str(puppeteer / "package.json")) + ''');
const {default:puppeteer}=await import(pathToFileURL(require.resolve("puppeteer")).href);
const browser=await puppeteer.launch({headless:true,executablePath:process.env.PUPPETEER_EXECUTABLE_PATH,
 args:["--no-sandbox","--disable-setuid-sandbox"]});
try {
 const page=await browser.newPage();
 await page.goto(''' + json.dumps(f'http://127.0.0.1:{server.server_port}/index.html') + ''');
 const rows=await page.evaluate(async cases=>{
  const {verify}=await import('/verify.mjs');
  const rows=[];
  for(const item of cases){
   const module=await import(item.entry);
   rows.push({...item,rounds:await verify(module,item.scenario)});
  }
  return rows;
 },''' + json.dumps(browser_cases) + ''');
 console.log(JSON.stringify(rows));
} finally {await browser.close();}
''')
            done = subprocess.run(["node", str(script)], capture_output=True, text=True, timeout=90, cwd=work)
            assert done.returncode == 0, done.stdout + done.stderr
            for row in json.loads(done.stdout):
                observations.append(summarize(work, row["name"], "chromium", row["rounds"], row["capacity"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    else:
        observations.append({"execution": "chromium", "status": "SKIP", "reason": "--puppeteer-root required"})
    return {"status": "PASS" if puppeteer else "REDUCED", "observations": observations}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--toolchain-root', type=Path, required=True)
    parser.add_argument('--puppeteer-root', type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='vibeflow-native-graph-') as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        report = run(work, args.toolchain_root, args.puppeteer_root)
        (work / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(f"JavaScript ordinary graph concurrency: {report['status']} observations={len(report['observations'])}")


if __name__ == '__main__':
    main()
