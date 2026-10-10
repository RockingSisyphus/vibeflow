"""Build one composite application per Target and exercise its public ABI."""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from threading import Thread
from time import perf_counter


FIXTURE = Path(__file__).resolve().parent
REPOSITORY = FIXTURE.parents[2]
sys.path[:0] = [str(REPOSITORY), str(REPOSITORY / "src")]

from tests.fixtures.support.comprehensive_math import SCENARIOS, assert_warning_feedback
from vibeflow.targets.javascript.build.driver_session import check_scope
from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def _node_script(path, script):
    path.write_text(script)
    completed = subprocess.run(["node", str(path)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _report(build):
    return {"status": "CONCERNS" if build.prepared.warnings else "PASS", "errors": [],
            "warnings": list(build.prepared.warnings)}


@check_scope
def run(work, *, toolchain, renderer, skip_browser=False):
    shutil.copytree(FIXTURE / "project", work / "project", ignore=shutil.ignore_patterns("node_modules"))
    shutil.copy2(FIXTURE / "vibeflow_config.jsonc", work / "vibeflow_config.jsonc")
    project = work / "project"
    if toolchain:
        (project / "node_modules").symlink_to(toolchain.resolve() / "node_modules", target_is_directory=True)
    else:
        subprocess.run(["npm", "ci"], cwd=project, check=True)
    workspace = work / "vibeflow_config.jsonc"
    config = project / "configs/formula.jsonc"

    def build(target, name):
        return build_project_aot(ProjectBuildRequest(workspace=workspace, config=config,
            out_dir=work / name, target=target, profile="single-esm"))

    module = build("node", "node-build")
    warning_counts = assert_warning_feedback(_report(module))
    assert module.prepared.used_base_libs == ("math.helpers",), module.prepared.used_base_libs
    assert module.prepared.used_capabilities == ("vibeflow.port",), module.prepared.used_capabilities
    driver = FIXTURE / "scenario_driver.mjs"
    node_result = _node_script(work / "verify-node.mjs", f'''
import {{verify}} from {json.dumps(driver.as_uri())};
const workflow = await import({json.dumps(module.entry.as_uri())});
const result = await verify(workflow, {json.dumps(SCENARIOS)});
process.stdout.write(JSON.stringify(result));
''')
    browser_result = {"status": "SKIP"} if skip_browser else None
    if not skip_browser:
        browser_module = build("browser", "browser-build")
        assert_warning_feedback(_report(browser_module))
        shutil.copy2(driver, browser_module.out_dir / "assertions.mjs")
        (browser_module.out_dir / "index.html").write_text('<!doctype html><meta charset="utf-8"><pre id="result"></pre>')
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(browser_module.out_dir)))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/index.html"
            browser_result = _node_script(work / "verify-browser.mjs", f'''
import {{createRequire}} from "node:module";
const require = createRequire({json.dumps(str(renderer / "package.json"))});
const puppeteer = require("puppeteer");
const browser = await puppeteer.launch({{headless: true, args: ["--no-sandbox"]}});
try {{
  const page = await browser.newPage();
  await page.goto({json.dumps(url)});
  const result = await page.evaluate(async (cases) => {{
    const workflow = await import({json.dumps('./' + browser_module.entry.name)});
    const {{verify}} = await import("./assertions.mjs");
    const result = await verify(workflow, cases);
    document.querySelector("#result").textContent = JSON.stringify(result);
    return result;
  }}, {json.dumps(SCENARIOS)});
  if (JSON.parse(await page.$eval("#result", node => node.textContent)).observations[0].result !== {SCENARIOS[0]['result']}) throw new Error("browser result was not displayed");
  process.stdout.write(JSON.stringify(result));
}} finally {{ await browser.close(); }}
''')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    square = project / "nodes/square.ts"
    square.write_text(square.read_text().replace('  return ', '  const padding = "tttttttttt";\n  return ', 1))
    repaired = build("node", "repaired-build")
    assert_warning_feedback(_report(repaired), repaired=True)
    (work / "health.json").write_text(json.dumps(_report(module), ensure_ascii=False, indent=2))
    (work / "repaired-health.json").write_text(json.dumps(_report(repaired), ensure_ascii=False, indent=2))
    report = {"target": "javascript", "status": "REDUCED" if skip_browser else "PASS",
              "warnings": warning_counts,
              "node": node_result, "browser": browser_result, "source_repair": "PASS"}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, help="retain the temporary project and reports here")
    parser.add_argument("--toolchain-root", type=Path, help="reuse installed pinned TypeScript/esbuild dependencies")
    parser.add_argument("--puppeteer-root", type=Path, help="reuse installed Puppeteer dependencies")
    parser.add_argument("--skip-browser", action="store_true", help="explicitly reduced local run")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="vibeflow-javascript-math-") as temporary:
        work = args.work_dir.resolve() if args.work_dir else Path(temporary)
        work.mkdir(parents=True, exist_ok=True)
        renderer = args.puppeteer_root.resolve() if args.puppeteer_root else work / "renderer"
        if not args.skip_browser and not args.puppeteer_root:
            renderer.mkdir()
            for name in ("package.json", "package-lock.json"):
                shutil.copy2(REPOSITORY / "tools/mermaid-renderer" / name, renderer / name)
            subprocess.run(["npm", "ci"], cwd=renderer, check=True)
        started = perf_counter()
        report = run(work, toolchain=args.toolchain_root, renderer=renderer, skip_browser=args.skip_browser)
        report["seconds"] = round(perf_counter() - started, 3)
        (work / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"JavaScript comprehensive math: {report['status']} node_observations={len(report['node']['observations'])} seconds={report['seconds']} report={work / 'report.json'}")


if __name__ == "__main__":
    main()
