"""SDK/AOT monitoring through actual Node.js, including a blocked event loop."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from vibeflow.tooling.application.javascript.build import ProjectBuildRequest, build_project_aot


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = '''import {definePlugin, defineNode, defineDataSchema} from "@vibeflow/plugin";
export const start = defineNode({type_key: "monitor.start", flow_kind: "terminal", contract: {}, rulesets: ["vibeflow.io"], run() {return {};}});
export const calculate = defineNode({type_key: "monitor.calculate", rulesets: ["vibeflow.python_io"], contract: {
  requires: [{type: "monitor.number", cardinality: "exactly_one", display_name: "Input value"}],
  provides: [{key: "result", type: "monitor.result", display_name: "Result"}],
  input_semantics: {"monitor.number": ["Input number"]}, output_semantics: {result: ["Input plus one"]}
}, run(inputs, params, context) {
  const info = [{metrics: {loss: .125}}, {message: "训练第10轮"}];
  context.updateInfo(info);
  info[0].metrics.loss = 999;
  console.log("js-business-stdout");
  console.error("js-business-stderr");
  const deadline = Date.now() + 250;
  while (Date.now() < deadline) { /* Deliberately block the main event loop. */ }
  if (inputs["monitor.number"].value < 0) throw new Error("sandbox JS failed");
  return {result: inputs["monitor.number"].value + 1};
}});
export const end = defineNode({type_key: "monitor.end", flow_kind: "terminal", contract: {}, rulesets: ["vibeflow.io"], run() {return {};}});
export const input = defineDataSchema({type_key: "monitor.number", schema: {type: "number"}});
export const output = defineDataSchema({type_key: "monitor.result", schema: {type: "number"}});
export const plugin = definePlugin({id: "monitor.plugin", resources: [start, calculate, end, input, output]});
'''


def write_project(work, toolchain):
    project = work / "project"
    project.mkdir(parents=True)
    project.joinpath("node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for name in ("package.json", "package-lock.json", "tsconfig.json"):
        shutil.copy2(ROOT / "sandbox/javascript/minimal/project" / name, project / name)
    (project / "vibeflow_project.jsonc").write_text('{"project_target":"javascript"}')
    (project / "plugin.ts").write_text(PLUGIN)
    (work / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "monitor", "path": "project"}]}))
    pipeline = {"entry_mode": "sync", "inputs": [{"key": "value", "type": "monitor.number", "display_name": "Value", "required": True}],
                "nodes": [{"id": name, "type_used": "monitor." + name, "display_name": name.title(),
                           "description": "Runtime monitoring " + name} for name in ("start", "calculate", "end")],
                "edges": [["start", "calculate"], ["calculate", "end"]],
                "outputs": [{"type": "monitor.result", "as": "result", "display_name": "Result", "cardinality": "exactly_one"}]}
    pipeline["nodes"][2]["similar_to"] = {"node": "start", "relationship": "copy", "reason": "Both boundaries return an empty output"}
    (project / "workflow.jsonc").write_text(json.dumps({"plugins": [{"source": {"kind": "file", "ref": "plugin.ts"}}],
                                                     "rulesets": ["vibeflow.workflow"], "pipeline": pipeline}))
    return project


def observe(work, toolchain):
    project = write_project(work, toolchain)
    workspace = work / "vibeflow_config.jsonc"
    built = build_project_aot(ProjectBuildRequest(workspace, project / "workflow.jsonc", work / "dist", "node", "single-esm"))
    script = work / "run.mjs"
    script.write_text('''import {readFileSync} from "node:fs";
import {pathToFileURL} from "node:url";
const workflow = await import(pathToFileURL(process.argv[2]));
const root = process.argv[3];
const file = root + "/monitor.json";
const records = [];
for (const [name, value] of [["success", 3], ["failure", -1], ["reset", 4]]) {
  let output, failure;
  const heartbeats = [];
  try {
    output = workflow.runWorkflow({value}, {runDir: root + "/" + name, statusFile: file, statusIntervalMs: 20,
      onStatus(status) {
        if (status.state === "running") setTimeout(() => {}, 1);
        heartbeats.push(status);
      }});
  } catch (error) {failure = error.message;}
  records.push({id: name, output, failure, record: JSON.parse(readFileSync(file, "utf8")),
    reset: heartbeats[0].info.length === 0,
    business: readFileSync(root + "/" + name + "/business.log", "utf8"),
    kernel: readFileSync(root + "/" + name + "/vibeflow.log", "utf8")});
}
console.log("REPORT " + JSON.stringify(records));
''')
    live = []
    status_file = work / "runs/monitor.json"
    with (work / "stdout.txt").open("w") as stdout, (work / "stderr.txt").open("w") as stderr:
        process = subprocess.Popen(["node", str(script), str(built.entry), str(work / "runs")],
                                   cwd=work, stdout=stdout, stderr=stderr)
        while process.poll() is None:
            if status_file.exists():
                live.append(json.loads(status_file.read_text()))
            time.sleep(.005)
        exit_code = process.wait()
    result = subprocess.CompletedProcess([], exit_code, (work / "stdout.txt").read_text(), (work / "stderr.txt").read_text())
    running_updates = len({record["updated_at"] for record in live if record["state"] == "running"})
    records = json.loads(next(line[len("REPORT "):] for line in result.stdout.splitlines() if line.startswith("REPORT ")))
    cases = []
    for record in records:
        state = "failed" if record["id"] == "failure" else "succeeded"
        checks = {"state": record["record"]["state"] == state, "reset": record["reset"],
                  "info_snapshot": record["record"]["info"][0]["metrics"]["loss"] == .125,
                  "business": all(text in record["business"] for text in ("js-business-stdout", "js-business-stderr")),
                  "kernel": '"kind":"run_start"' in record["kernel"] and "js-business-stdout" not in record["kernel"],
                  "terminal": "js-business-stdout" in result.stdout and "js-business-stderr" in result.stderr,
                  "blocked_event_loop_heartbeat": running_updates >= 6}
        checks["result"] = bool(record.get("failure")) if state == "failed" else record["output"] == {"result": 4 if record["id"] == "success" else 5}
        cases.append({"id": record["id"], "matched": all(checks.values()), "checks": checks, "record": record["record"]})
    return {"schema": "vibeflow.javascript-runtime-observation.v1", "cases": cases,
            "matched": result.returncode == 0 and all(case["matched"] for case in cases), "entry": str(built.entry), "live_running_updates": running_updates}


def observe_browser(work, toolchain, renderer):
    from sandbox.javascript.integration.sandbox_support import run_browser
    project = write_project(work, toolchain)
    built = build_project_aot(ProjectBuildRequest(work / "vibeflow_config.jsonc", project / "workflow.jsonc",
                                                work / "web", "browser", "single-esm"))
    expected = json.dumps({"result": 4, "states": ["starting", "running", "succeeded"],
                           "info": [{"metrics": {"loss": .125}}, {"message": "训练第10轮"}]},
                          ensure_ascii=False, separators=(",", ":"))
    (built.out_dir / "index.html").write_text('''<button id="run">Run</button><pre id="output"></pre>
<script type="module">
import {runWorkflow} from "./''' + built.entry.name + '''";
document.querySelector("#run").onclick = () => {
  const records = [];
  const value = runWorkflow({value: 3}, {onStatus: status => records.push(status)});
  document.querySelector("#output").textContent = JSON.stringify({result: value.result,
    states: records.map(record => record.state), info: records.at(-1).info});
};
</script>''')
    actual = run_browser(built.out_dir, puppeteer_root=renderer, expected=expected)
    return {"id": "real_browser", "matched": actual["after"] == expected,
            "record": json.loads(actual["after"]), "entry": str(built.entry)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--renderer", type=Path)
    args = parser.parse_args()
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    result = observe(work, args.toolchain.resolve())
    if args.renderer is not None:
        result["browser"] = observe_browser(work / "browser", args.toolchain.resolve(), args.renderer.resolve())
        result["matched"] = result["matched"] and result["browser"]["matched"]
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["matched"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
