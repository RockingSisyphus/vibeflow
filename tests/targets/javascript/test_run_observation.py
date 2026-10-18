from tests.targets.javascript.aot_fixtures import emit_fixture, fixture_build_request
"""Actual SDK/AOT monitoring and the portable browser status callback."""

import json
import os
from pathlib import Path
import subprocess

import pytest

from sandbox.javascript.runtime_observation.probe import observe
from tests.targets.javascript.test_aot_core import _linear_plan, _node, _provider, _requirement, _write_emitted
from vibeflow.targets.javascript.resources import read_text


ROOT = Path(__file__).resolve().parents[3]


def test_sdk_node_aot_files_and_blocked_event_loop_heartbeat(tmp_path):
    result = observe(tmp_path, Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"]))
    assert result["matched"], result
    assert result["live_running_updates"] >= 6


@pytest.mark.parametrize("async_mode", [False, True])
def test_portable_context_updates_callbacks_and_failure(tmp_path, async_mode):
    plan = _linear_plan(middle=_node("middle", "middle", requires=[_requirement("number")],
                                    provides=[_provider("answer", "answer")],
                                    completion="suspend" if async_mode else "immediate"),
                        entry_mode="async" if async_mode else "sync")
    source = '''export function start() {return {};}
export function end() {return {};}
export %sfunction middle(inputs, params, context) {
  const info = [{loss: .125}, {nested: {values: [1, null, false]}}];
  context.updateInfo(info); info[1].nested.values[0] = 99;
  if (inputs.number.value < 0) throw new Error("actual failure");
  return {answer: inputs.number.value + 1};
}''' % ("async " if async_mode else "")
    workflow = _write_emitted(tmp_path, plan, source)
    entry = "runWorkflowAsync" if async_mode else "runWorkflow"
    script = f'''import * as workflow from {json.dumps(workflow.as_uri())};
const records = [];
const value = await workflow.{entry}({{number: 4}}, {{onStatus: record => records.push(record)}});
if (value.answer !== 5 || records.at(-1).state !== "succeeded") throw new Error("wrong successful result");
if (records.at(-1).info[1].nested.values[0] !== 1) throw new Error("info alias leaked");
if (!Object.isFrozen(records.at(-1).info[1].nested.values)) throw new Error("snapshot mutable");
try {{ await workflow.{entry}({{number: -1}}, {{onStatus: record => records.push(record)}}); }} catch {{}}
if (records.at(-1).state !== "failed" || typeof records.at(-1).error !== "string") throw new Error("missing failure");
if (records.filter(record => record.state === "starting").some(record => record.info.length)) throw new Error("info not reset");
console.log(JSON.stringify({{states: records.map(record => record.state)}}));'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["states"] == ["starting", "running", "succeeded", "starting", "running", *(["stopping"] if async_mode else []), "failed"]
    assert not (tmp_path / "runs").exists()


@pytest.mark.parametrize("value", ["undefined", "new Map()", "new Date()", "NaN", "Infinity", "1n", "()=>{}"])
def test_js_info_rejects_non_json_without_silent_conversion(tmp_path, value):
    script = read_text("status_helpers.mjs") + f'''
try {{ __vfSnapshotInfo([{{value: {value}}}]); process.exitCode = 2; }}
catch (error) {{ if (!(error instanceof TypeError)) throw error; }}
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_host_session_keeps_running_between_calls_and_finishes_on_stop(tmp_path):
    from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
    from tests.targets.javascript.test_emitter_golden import _emission_cases
    plan, extensions = _emission_cases()["host_extension"]
    emitted = emit_fixture(plan, host_extensions=extensions)
    (tmp_path / "workflow.mjs").write_text(read_text("node_observation.mjs") + "\n" + emitted.source)
    # Preserve the actual workflow's native input/output bindings.
    (tmp_path / "nodes.mjs").write_text('export function start() {return {};} export function end() {return {};} export function calculate(inputs, params, context) {context.updateInfo([{value: inputs.number.value}]); console.log("host-business"); return {out: inputs.number.value};}')
    modules = {node.get("implementation", {}).get("ref") for node in plan["nodes"]}
    assert modules == {"./nodes.mjs"}, modules
    descriptor = extensions[0]
    (tmp_path / descriptor["module"]).write_text('export function createHostExtension() {return {capabilities: {"baseline.clock": {}}, start() {}, stop() {}};}')
    script = f'''import * as workflow from {json.dumps((tmp_path / "workflow.mjs").as_uri())};
import {{readFileSync}} from "node:fs";
const path = {json.dumps(str(tmp_path / "host/status.json"))};
const records = [];
const host = workflow.createWorkflowHost({{runDir: {json.dumps(str(tmp_path / "host"))}, onStatus: status => records.push(status)}});
if (JSON.parse(readFileSync(path)).state !== "starting") throw new Error("host not starting");
await host.start();
host.runWorkflow({{number: 1}}); host.runWorkflow({{number: 2}});
if (JSON.parse(readFileSync(path)).state !== "running") throw new Error("invocation ended host session");
await host.stop();
const final = JSON.parse(readFileSync(path));
if (final.state !== "succeeded" || final.info[0].value !== 2) throw new Error("wrong final host record");
if (records.filter(record => record.state === "starting").length !== 1) throw new Error("multiple sessions");
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "host/business.log").read_text().count("host-business") == 2


@pytest.mark.parametrize("phase", ["create", "start", "stop"])
def test_host_lifecycle_failure_writes_final_failure(tmp_path, phase):
    from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
    from tests.targets.javascript.test_emitter_golden import _emission_cases
    plan, extensions = _emission_cases()["host_extension"]
    emitted = emit_fixture(plan, host_extensions=extensions)
    (tmp_path / "workflow.mjs").write_text(read_text("node_observation.mjs") + "\n" + emitted.source)
    (tmp_path / "nodes.mjs").write_text('export function start() {return {};} export function end() {return {};} export function calculate() {return {out: 1};}')
    throwing = 'throw new Error("lifecycle failed");'
    host = 'export function createHostExtension() {' + (throwing if phase == "create" else '') + 'return {capabilities: {"baseline.clock": {}}, start() {' + (throwing if phase == "start" else '') + '}, stop() {' + (throwing if phase == "stop" else '') + '}};}'
    (tmp_path / "host.mjs").write_text(host)
    script = f'''import * as workflow from {json.dumps((tmp_path / "workflow.mjs").as_uri())};
import {{readFileSync}} from "node:fs";
let failed = false;
try {{ const host = workflow.createWorkflowHost({{runDir: {json.dumps(str(tmp_path / "run"))}}}); await host.start(); await host.stop(); }}
catch {{ failed = true; }}
if (!failed) throw new Error("missing lifecycle failure");
const record = JSON.parse(readFileSync({json.dumps(str(tmp_path / "run/status.json"))}));
if (record.state !== "failed" || typeof record.error !== "string") throw new Error("missing failed record");
'''
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=tmp_path, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
