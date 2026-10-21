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
