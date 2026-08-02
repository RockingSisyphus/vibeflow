from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from vibeflow.targets.javascript.build import BuildRequest, build_aot
from vibeflow.targets.javascript.build.toolchain import (
    AotToolchainError,
    DriverBuildResult,
    ToolchainInfo,
    probe_toolchain,
)
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.errors import AotBuildError
from vibeflow.targets.javascript.frontend.model import AotPlanError, WorkflowSpec

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REAL_TOOLCHAIN_ROOT = (
    REPOSITORY_ROOT / "sandbox" / "javascript" / "minimal" / "project"
)


def _provider(key: str, type_key: str) -> dict[str, str]:
    return {"key": key, "type": type_key}


def _requirement(type_key: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": type_key, "cardinality": cardinality}


def _node(
    node_id: str,
    export: str,
    *,
    module: str = "./nodes.mjs",
    requires: list[dict[str, str]] | None = None,
    provides: list[dict[str, str]] | None = None,
    terminal: bool = False,
    **extra,
) -> dict[str, object]:
    return {
        "id": node_id,
        "type_used": f"test.{export}",
        "implementation": {"kind": "file", "ref": module, "export": export},
        "requires": requires or [],
        "provides": provides or [],
        "flow_kind": "terminal" if terminal else "process",
        "is_terminal": terminal,
        **extra,
    }


def _linear_plan(
    *,
    middle: dict[str, object],
    output_type: str = "answer",
    entry_mode: str = "sync",
) -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.workflow",
        "entry_mode": entry_mode,
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": output_type, "cardinality": "exactly_one", "as": "answer"}
        ],
        "schemas": {
            "number": {"type": "number"},
            output_type: {"type": "number"},
        },
        "nodes": [
            _node("start", "start", terminal=True),
            middle,
            _node(
                "end",
                "end",
                requires=[_requirement(output_type)],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "start", "target": str(middle["id"])},
            {"source": str(middle["id"]), "target": "end"},
        ],
        "order": ["start", str(middle["id"]), "end"],
        "max_steps": 20,
    }


def _write_emitted(tmp_path: Path, plan: dict[str, object], node_source: str) -> Path:
    (tmp_path / "nodes.mjs").write_text(node_source, encoding="utf-8")
    emitted = emit_workflow_module(plan)
    workflow = tmp_path / "workflow.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")
    (tmp_path / "workflow.d.ts").write_text(emitted.declarations, encoding="utf-8")
    return workflow


def _run_esm(workflow: Path, body: str) -> object:
    script = f"""
import {{ pathToFileURL }} from "node:url";
globalThis.__vfCalls = [];
const workflow = await import(pathToFileURL({json.dumps(str(workflow))}).href);
{body}
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def _real_toolchain_project(tmp_path: Path) -> Path:
    if not (REAL_TOOLCHAIN_ROOT / "node_modules/typescript").is_dir():
        pytest.skip("the example TypeScript 7 toolchain has not been installed")
    project = tmp_path / "real-toolchain"
    project.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(REAL_TOOLCHAIN_ROOT / name, project / name)
    (project / "node_modules").symlink_to(
        REAL_TOOLCHAIN_ROOT / "node_modules",
        target_is_directory=True,
    )
    return project


def _empty_real_plan(module: Path) -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.import-policy",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node(
                "run",
                "run",
                module=str(module),
                terminal=True,
            )
        ],
        "routes": [],
        "order": ["run"],
        "max_steps": 5,
    }


def test_emitted_esm_has_no_auto_run_and_is_repeatable_concurrent_and_plain(
    tmp_path: Path,
) -> None:
    plan = _linear_plan(
        middle=_node(
            "double",
            "double",
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
            completion="suspend",
        ),
        entry_mode="async",
    )
    workflow = _write_emitted(
        tmp_path,
        plan,
        """
export function start() { globalThis.__vfCalls.push("start"); return {}; }
export async function double(inputs) {
  const value = inputs.number.value;
  await new Promise(resolve => setTimeout(resolve, value === 2 ? 15 : 1));
  globalThis.__vfCalls.push(`double:${value}`);
  return { out: value * 2 };
}
export function end() { globalThis.__vfCalls.push("end"); return {}; }
""",
    )
    result = _run_esm(
        workflow,
        """
const callsAfterImport = [...globalThis.__vfCalls];
const tracesA = [];
const [a, b] = await Promise.all([
  workflow.runWorkflowAsync({ number: 2 }, { trace: "full", onTrace: event => tracesA.push(event) }),
  workflow.runWorkflowAsync({ number: 5 }),
]);
const again = await workflow.runWorkflowAsync({ number: 7 });
console.log(JSON.stringify({
  callsAfterImport,
  a,
  b,
  again,
  traceStarts: tracesA.filter(item => item.kind === "run_start").length,
  traceEnds: tracesA.filter(item => item.kind === "run_end").length,
}));
""",
    )
    assert result == {
        "callsAfterImport": [],
        "a": {"answer": 4},
        "b": {"answer": 10},
        "again": {"answer": 14},
        "traceStarts": 1,
        "traceEnds": 1,
    }


def test_emitted_esm_is_static_code_without_embedded_graph_interpreter() -> None:
    plan = _linear_plan(
        middle=_node(
            "double",
            "double",
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
        )
    )

    source = emit_workflow_module(plan).source

    for interpreter_marker in (
        "__vfPlan",
        "runPlan",
        "plan.nodes",
        "plan.routes",
        "createVibeFlowWorkflow",
    ):
        assert interpreter_marker not in source
    assert "switch (nodeId)" in source
    assert "case \"double\"" in source
    assert "__vf_execute_w0_n1(inputs, state)" in source
    assert "conditionMatches" in source


def test_emitted_esm_json_schema_const_uses_json_deep_equality(
    tmp_path: Path,
) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.schema-const",
        "inputs": [
            {
                "key": "payload",
                "type": "payload",
                "required": True,
                "schema": {
                    "const": {
                        "name": "Ada",
                        "values": [1, {"enabled": True}],
                    }
                },
            }
        ],
        "outputs": [],
        "nodes": [_node("start", "start", terminal=True)],
        "routes": [],
        "order": ["start"],
        "max_steps": 5,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        "export function start() { return {}; }\n",
    )
    result = _run_esm(
        workflow,
        """
const value = await workflow.runWorkflow({
  payload: {
    values: [1, { enabled: true }],
    name: "Ada",
  },
});
let mismatch;
let nullInput;
try {
  await workflow.runWorkflow({
    payload: {
      values: [{ enabled: true }, 1],
      name: "Ada",
    },
  });
} catch (error) {
  mismatch = error.code;
}
try {
  await workflow.runWorkflow(null);
} catch (error) {
  nullInput = error.code;
}
console.log(JSON.stringify({ value, mismatch, nullInput }));
""",
    )
    assert result == {
        "value": {},
        "mismatch": "VF_INPUT_SCHEMA",
        "nullInput": "VF_INPUT_SCHEMA",
    }


def test_emitted_esm_schema_length_counts_unicode_code_points(tmp_path: Path) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.unicode-length",
        "inputs": [
            {
                "key": "value",
                "type": "text",
                "required": True,
                "schema": {"type": "string", "minLength": 1, "maxLength": 1},
            }
        ],
        "outputs": [],
        "nodes": [_node("start", "start", terminal=True)],
        "routes": [],
        "order": ["start"],
        "max_steps": 2,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        "export function start() { return {}; }\n",
    )

    result = _run_esm(
        workflow,
        """
const accepted = await workflow.runWorkflow({ value: "😀" });
let rejected;
try {
  await workflow.runWorkflow({ value: "ab" });
} catch (error) {
  rejected = error.code;
}
console.log(JSON.stringify({ accepted, rejected }));
""",
    )

    assert result == {"accepted": {}, "rejected": "VF_INPUT_SCHEMA"}


def test_emitted_esm_preserves_magic_public_output_keys(
    tmp_path: Path,
) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.magic-output-key",
        "inputs": [],
        "outputs": [
            {
                "type": "answer",
                "cardinality": "exactly_one",
                "as": "__proto__",
            }
        ],
        "schemas": {
            "answer": {
                "type": "object",
                "properties": {"ok": {"const": True}},
                "required": ["ok"],
                "additionalProperties": False,
            }
        },
        "nodes": [
            _node(
                "answer",
                "answer",
                provides=[_provider("answer", "answer")],
                terminal=True,
            )
        ],
        "routes": [],
        "order": ["answer"],
        "max_steps": 5,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        "export function answer() { return { answer: { ok: true } }; }\n",
    )
    result = _run_esm(
        workflow,
        """
const value = await workflow.runWorkflow({});
console.log(JSON.stringify({
  own: Object.prototype.hasOwnProperty.call(value, "__proto__"),
  keys: Object.keys(value),
  payload: value["__proto__"],
  ordinaryPrototype: Object.getPrototypeOf(value) === Object.prototype,
}));
""",
    )
    assert result == {
        "own": True,
        "keys": ["__proto__"],
        "payload": {"ok": True},
        "ordinaryPrototype": True,
    }


def test_emitted_esm_capabilities_preflight_and_prompt_abort(tmp_path: Path) -> None:
    capability_middle = _node(
        "cap",
        "cap",
        requires=[_requirement("number")],
        provides=[_provider("out", "answer")],
        capabilities=[{"id": "test.math", "operations": ["double"]}],
    )
    capability_middle["completion"] = "suspend"
    plan = _linear_plan(
        middle=capability_middle,
        entry_mode="async",
    )
    plan["capabilities"] = [
        {
            "id": "test.math",
            "operations": {
                "double": {
                    "input_type": "number",
                    "output_type": "answer",
                    "completion": "suspend",
                }
            },
        }
    ]
    workflow = _write_emitted(
        tmp_path,
        plan,
        """
export function start() { return {}; }
export async function cap(inputs, _params, context) {
  const value = inputs.number.value;
  return {
    out: await context.capabilities["test.math"].double(value === 13 ? "bad" : value),
  };
}
export function end() { return {}; }
export function hang() { return new Promise(() => {}); }
""",
    )
    result = _run_esm(
        workflow,
        """
let missing;
try {
  await workflow.runWorkflowAsync({ number: 4 });
} catch (error) {
  missing = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
const value = await workflow.runWorkflowAsync(
  { number: 4 },
  { capabilities: { "test.math": { double: value => value * 2 } } },
);
let failed;
try {
  await workflow.runWorkflowAsync(
    { number: 4 },
    {
      capabilities: {
        "test.math": {
          double() {
            throw new Error("synthetic capability failure");
          },
        },
      },
    },
  );
} catch (error) {
  failed = {
    code: error.code,
    cause: error.cause?.message,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
let inputFailure;
try {
  await workflow.runWorkflowAsync(
    { number: 13 },
    { capabilities: { "test.math": { double: value => value * 2 } } },
  );
} catch (error) {
  inputFailure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
let outputFailure;
try {
  await workflow.runWorkflowAsync(
    { number: 14 },
    { capabilities: { "test.math": { double: () => "bad" } } },
  );
} catch (error) {
  outputFailure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
const capabilityController = new AbortController();
setTimeout(() => capabilityController.abort("stop capability"), 10);
let capabilityAbort;
try {
  await workflow.runWorkflowAsync(
    { number: 15 },
    {
      signal: capabilityController.signal,
      capabilities: {
        "test.math": { double: () => new Promise(() => {}) },
      },
    },
  );
} catch (error) {
  capabilityAbort = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
console.log(JSON.stringify({
  missing,
  value,
  failed,
  inputFailure,
  outputFailure,
  capabilityAbort,
}));
""",
    )
    assert result == {
        "missing": {
            "code": "VF_CAPABILITY_MISSING",
            "nodePath": "",
            "blockPath": "/",
        },
        "value": {"answer": 8},
        "failed": {
            "code": "VF_CAPABILITY_FAILED",
            "cause": "synthetic capability failure",
            "nodePath": "cap",
            "blockPath": "/",
        },
        "inputFailure": {
            "code": "VF_CAPABILITY_INPUT",
            "nodePath": "cap",
            "blockPath": "/",
        },
        "outputFailure": {
            "code": "VF_CAPABILITY_OUTPUT",
            "nodePath": "cap",
            "blockPath": "/",
        },
        "capabilityAbort": {
            "code": "VF_ABORTED",
            "nodePath": "cap",
            "blockPath": "/",
        },
    }

    abort_plan = _linear_plan(
        middle=_node(
            "hang",
            "hang",
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
            completion="suspend",
        ),
        entry_mode="async",
    )
    abort_workflow = tmp_path / "abort-workflow.mjs"
    abort_workflow.write_text(
        emit_workflow_module(abort_plan).source,
        encoding="utf-8",
    )
    started = time.monotonic()
    aborted = _run_esm(
        abort_workflow,
        """
const controller = new AbortController();
setTimeout(() => controller.abort("stop"), 10);
let failure;
try {
  await workflow.runWorkflowAsync({ number: 1 }, { signal: controller.signal });
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
console.log(JSON.stringify({ failure }));
""",
    )
    assert aborted == {
        "failure": {
            "code": "VF_ABORTED",
            "nodePath": "hang",
            "blockPath": "/",
        }
    }
    assert time.monotonic() - started < 1


def test_emitted_esm_exposes_only_each_nodes_declared_capability_operations(
    tmp_path: Path,
) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.capability-minimum-authority",
        "inputs": [],
        "outputs": [],
        "schemas": {
            "request": {"type": "object"},
            "result": {"type": "object"},
        },
        "capabilities": [
            {
                "id": "test.store",
                "operations": {
                    "read": {
                        "input_type": "request",
                        "output_type": "result",
                    },
                    "write": {
                        "input_type": "request",
                        "output_type": "result",
                    },
                },
            }
        ],
        "nodes": [
            _node(
                "reader",
                "reader",
                terminal=True,
                capabilities=[
                    {"id": "test.store", "operations": ["read"]}
                ],
            ),
            _node(
                "writer",
                "writer",
                capabilities=[
                    {"id": "test.store", "operations": ["write"]}
                ],
            ),
        ],
        "routes": [],
        "order": ["reader", "writer"],
        "max_steps": 5,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        """
export function reader(_inputs, _params, context) {
  const store = context.capabilities["test.store"];
  if (typeof store.write !== "undefined") {
    throw new Error("reader received undeclared write authority");
  }
  return {};
}
export function writer() { return {}; }
""",
    )
    result = _run_esm(
        workflow,
        """
const value = await workflow.runWorkflow({}, {
  capabilities: {
    "test.store": {
      read: value => value,
      write: value => value,
    },
  },
});
console.log(JSON.stringify(value));
""",
    )
    assert result == {}


def test_emitted_esm_max_steps_has_root_block_and_next_node_path(
    tmp_path: Path,
) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.max-steps-path",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("start", "start", terminal=True),
            _node("tick", "tick"),
        ],
        "routes": [
            {"source": "start", "target": "tick"},
            {"source": "tick", "target": "tick"},
        ],
        "order": ["start", "tick"],
        "max_steps": 3,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        """
export function start() { return {}; }
export function tick() { return {}; }
""",
    )
    result = _run_esm(
        workflow,
        """
let failure;
try {
  await workflow.runWorkflow({});
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
console.log(JSON.stringify(failure));
""",
    )
    assert result == {
        "code": "VF_MAX_STEPS",
        "nodePath": "tick",
        "blockPath": "/",
    }


def test_emitted_esm_supports_all_join_result_key_and_detached(tmp_path: Path) -> None:
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.parallel",
        "inputs": [],
        "outputs": [{"type": "value", "cardinality": "all", "as": "values"}],
        "schemas": {"value": {"type": "number"}},
        "nodes": [
            _node("start", "start", terminal=True),
            _node("left", "left", provides=[_provider("left", "value")]),
            _node("right", "right", provides=[_provider("right", "value")]),
            _node(
                "join",
                "join",
                requires=[_requirement("value", "all")],
                terminal=True,
                join_policy="all",
            ),
        ],
        "routes": [
            {"source": "start", "target": "left"},
            {"source": "start", "target": "right"},
            {"source": "left", "target": "join"},
            {"source": "right", "target": "join"},
        ],
        "order": ["start", "left", "right", "join"],
        "max_steps": 20,
    }
    workflow = _write_emitted(
        tmp_path,
        plan,
        """
export function start() { return {}; }
export function left() { return { left: 1 }; }
export function right() { return { right: 2 }; }
export function join() { return {}; }
export async function delayed(inputs) {
  await new Promise(resolve => setTimeout(resolve, 5));
  return { out: inputs.number.value + 1 };
}
export async function delayedFlag(inputs) {
  await new Promise(resolve => setTimeout(resolve, 5));
  return { out: inputs.number.value > 0 };
}
export function positive() { globalThis.__vfCalls.push("positive"); return {}; }
export function negative() { globalThis.__vfCalls.push("negative"); return {}; }
export async function detached() {
  await new Promise(resolve => setTimeout(resolve, 5));
  globalThis.__vfCalls.push("detached-done");
  return {};
}
export function boom() {
  throw new Error("synthetic node failure");
}
export function end() { return {}; }
""",
    )
    result = _run_esm(
        workflow,
        """
const values = await workflow.runWorkflow({});
console.log(JSON.stringify(values));
""",
    )
    assert result == {"values": [1, 2]}

    async_plan = _linear_plan(
        middle=_node(
            "delayed",
            "delayed",
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
            async_mode="result_key",
            result_key="out",
            completion="suspend",
        ),
        entry_mode="async",
    )
    (tmp_path / "async-workflow.mjs").write_text(
        emit_workflow_module(async_plan).source,
        encoding="utf-8",
    )
    async_result = _run_esm(
        tmp_path / "async-workflow.mjs",
        """
const value = await workflow.runWorkflowAsync({ number: 9 });
console.log(JSON.stringify(value));
""",
    )
    assert async_result == {"answer": 10}

    conditional_async_plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.async-condition",
        "entry_mode": "async",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": "flag", "cardinality": "exactly_one", "as": "flag"}
        ],
        "schemas": {
            "number": {"type": "number"},
            "flag": {"type": "boolean"},
        },
        "nodes": [
            _node("start", "start", terminal=True),
            _node(
                "check",
                "delayedFlag",
                requires=[_requirement("number")],
                provides=[_provider("out", "flag")],
                async_mode="result_key",
                result_key="out",
                completion="suspend",
            ),
            _node(
                "positive",
                "positive",
                requires=[_requirement("flag", "optional_one")],
                terminal=True,
            ),
            _node(
                "negative",
                "negative",
                requires=[_requirement("flag", "optional_one")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "start", "target": "check"},
            {
                "source": "check",
                "target": "positive",
                "condition": {
                    "key": "out",
                    "operator": "==",
                    "literal": True,
                },
            },
            {
                "source": "check",
                "target": "negative",
                "condition": {
                    "key": "out",
                    "operator": "==",
                    "literal": False,
                },
            },
        ],
        "order": ["start", "check", "positive", "negative"],
        "max_steps": 10,
    }
    (tmp_path / "conditional-async-workflow.mjs").write_text(
        emit_workflow_module(conditional_async_plan).source,
        encoding="utf-8",
    )
    conditional_async = _run_esm(
        tmp_path / "conditional-async-workflow.mjs",
        """
const positive = await workflow.runWorkflowAsync({ number: 1 });
const positiveCalls = [...globalThis.__vfCalls];
globalThis.__vfCalls.length = 0;
const negative = await workflow.runWorkflowAsync({ number: 0 });
console.log(JSON.stringify({
  positive,
  positiveCalls,
  negative,
  negativeCalls: globalThis.__vfCalls,
}));
""",
    )
    assert conditional_async == {
        "positive": {"flag": True},
        "positiveCalls": ["positive"],
        "negative": {"flag": False},
        "negativeCalls": ["negative"],
    }

    detached_plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.detached",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("start", "start", terminal=True),
            _node(
                "side",
                "detached",
                async_mode="detached",
                completion="suspend",
            ),
            _node("end", "end", terminal=True),
        ],
        "routes": [
            {"source": "start", "target": "side"},
            {"source": "side", "target": "end"},
        ],
        "order": ["start", "side", "end"],
        "max_steps": 10,
    }
    (tmp_path / "detached-workflow.mjs").write_text(
        emit_workflow_module(detached_plan).source,
        encoding="utf-8",
    )
    detached_result = _run_esm(
        tmp_path / "detached-workflow.mjs",
        """
const value = await workflow.runWorkflowAsync({});
console.log(JSON.stringify({ value, calls: globalThis.__vfCalls }));
""",
    )
    assert detached_result == {
        "value": {},
        "calls": ["detached-done"],
    }

    failure_plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.detached.failure",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("start", "start", terminal=True),
            _node(
                "side",
                "detached",
                async_mode="detached",
                completion="suspend",
            ),
            _node("fail", "boom"),
        ],
        "routes": [
            {"source": "start", "target": "side"},
            {"source": "start", "target": "fail"},
        ],
        "order": ["start", "side", "fail"],
        "max_steps": 10,
    }
    (tmp_path / "detached-failure-workflow.mjs").write_text(
        emit_workflow_module(failure_plan).source,
        encoding="utf-8",
    )
    failure_result = _run_esm(
        tmp_path / "detached-failure-workflow.mjs",
        """
let code;
try {
  await workflow.runWorkflowAsync({});
} catch (error) {
  code = error.code;
}
console.log(JSON.stringify({ code, calls: globalThis.__vfCalls }));
""",
    )
    assert failure_result == {
        "code": "VF_NODE_FAILED",
        "calls": ["detached-done"],
    }


def test_portable_blocks_expand_child_nodeset_and_legacy_required_fails_closed() -> None:
    child_nodes = [
        _node("child_start", "start", terminal=True),
        _node(
            "double",
            "double",
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
        ),
        _node(
            "child_end",
            "end",
            requires=[_requirement("answer")],
            terminal=True,
        ),
    ]
    portable = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "portable",
        "entry_block": "block:/",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": "answer", "cardinality": "exactly_one", "as": "answer"}
        ],
        "blocks": [
            {
                "id": "block:/",
                "kind": "workflow",
                "inputs": [],
                "outputs": [],
                "nodes": [
                    _node("start", "start", terminal=True),
                    {
                        **_node(
                            "composite",
                            "unused",
                            requires=[_requirement("number")],
                            provides=[_provider("out", "answer")],
                        ),
                        "implementation": {"kind": "catalog", "ref": "composite"},
                        "is_nodeset": True,
                        "child_block": "block:/composite",
                    },
                    _node(
                        "end",
                        "end",
                        requires=[_requirement("answer")],
                        terminal=True,
                    ),
                ],
                "routes": [
                    {"source": "start", "target": "composite", "schedule": True, "transfer": True},
                    {"source": "composite", "target": "end", "schedule": True, "transfer": True},
                ],
                "order": ["start", "composite", "end"],
                "max_steps": 10,
            },
            {
                "id": "block:/composite",
                "kind": "nodeset",
                "inputs": [{"key": "number", "type": "number", "required": True}],
                "outputs": [
                    {"type": "answer", "cardinality": "exactly_one", "as": "answer"}
                ],
                "nodes": child_nodes,
                "routes": [
                    {"source": "child_start", "target": "double", "schedule": True, "transfer": True},
                    {"source": "double", "target": "child_end", "schedule": True, "transfer": True},
                ],
                "order": ["child_start", "double", "child_end"],
                "max_steps": 10,
            },
        ],
        "max_steps": 10,
    }
    normalized = WorkflowSpec.from_portable(portable)
    composite = normalized.nodes[1]
    assert composite.subplan is not None
    assert [node.id for node in composite.subplan.nodes] == [
        "child_start",
        "double",
        "child_end",
    ]
    assert composite.implementation is not None
    assert composite.implementation.module == "composite"

    portable["inputs"][0]["required"] = None
    with pytest.raises(AotPlanError, match="explicitly true or false"):
        WorkflowSpec.from_portable(portable)


def test_process_only_root_is_not_promoted_to_a_workflow_entry(
    tmp_path: Path,
) -> None:
    module = tmp_path / "node.mjs"
    module.write_text("export function run() { return {}; }\n", encoding="utf-8")
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.no-entry",
        "inputs": [],
        "outputs": [],
        "nodes": [_node("run", "run", module=str(module))],
        "routes": [],
        "order": ["run"],
        "max_steps": 5,
    }
    with pytest.raises(AotPlanError) as normalized:
        WorkflowSpec.from_portable(plan)
    assert normalized.value.code == "VF_WORKFLOW_ENTRY"

    with pytest.raises(AotBuildError) as built:
        build_aot(
            BuildRequest(
                plan=plan,
                project_root=tmp_path,
                package_root=tmp_path,
                out_dir=tmp_path / "dist",
                target="node",
                profile="single-esm",
            )
        )
    assert built.value.code == "VF_WORKFLOW_ENTRY"


def test_canonical_portable_loop_accepts_stop_when_carry_and_collect() -> None:
    portable = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "portable.loop",
        "entry_block": "block:/",
        "inputs": [],
        "outputs": [],
        "blocks": [
            {
                "id": "block:/",
                "kind": "workflow",
                "nodes": [
                    _node("start", "start", terminal=True),
                    {
                        **_node("repeat", "unused"),
                        "implementation": {"kind": "catalog", "ref": "repeat"},
                        "is_loop": True,
                        "child_block": "block:/repeat",
                    },
                    _node("end", "end", terminal=True),
                ],
                "routes": [
                    {"source": "start", "target": "repeat"},
                    {"source": "repeat", "target": "end"},
                ],
                "order": ["start", "repeat", "end"],
                "entries": ["start"],
                "max_steps": 20,
            },
            {
                "id": "block:/repeat",
                "kind": "loop",
                "nodes": [
                    _node("body_start", "start", terminal=True),
                    _node("body_end", "end", terminal=True),
                ],
                "routes": [{"source": "body_start", "target": "body_end"}],
                "order": ["body_start", "body_end"],
                "entries": ["body_start"],
                "max_steps": 10,
                "loop": {
                    "body": "test.body",
                    "max_iterations": 5,
                    "stop_after": None,
                    "stop_when": {
                        "key": "loop.done",
                        "operator": "==",
                        "literal": True,
                    },
                    "carry": [
                        {
                            "from": "value.current",
                            "as": "value.current",
                            "update": "value.next",
                        }
                    ],
                    "collect": [
                        {
                            "from": "value.next",
                            "as": "value.history",
                            "mode": "all",
                        }
                    ],
                    "outputs": [
                        {"from": "value.current", "as": "value.final"}
                    ],
                },
            },
        ],
        "max_steps": 20,
    }
    workflow = WorkflowSpec.from_portable(portable)
    repeat = next(node for node in workflow.nodes if node.id == "repeat")
    assert repeat.loop.stop_after == 0
    assert repeat.loop.stop_when_source == "loop.done"
    assert repeat.loop.stop_when_equals is True
    assert repeat.loop.carry[0].to_dict() == {
        "from": "value.current",
        "as": "value.current",
        "update": "value.next",
    }
    assert repeat.loop.collect[0].to_dict() == {
        "from": "value.next",
        "as": "value.history",
        "mode": "all",
    }


def test_emitted_esm_runs_nested_nodeset_and_bounded_or_unbounded_loop(
    tmp_path: Path,
) -> None:
    child = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "nested.child",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [{"type": "answer", "cardinality": "exactly_one", "as": "answer"}],
        "nodes": [
            _node("child_start", "start", terminal=True),
            _node(
                "double",
                "double",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            _node(
                "child_end",
                "end",
                requires=[_requirement("answer")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "child_start", "target": "double"},
            {"source": "double", "target": "child_end"},
        ],
        "order": ["child_start", "double", "child_end"],
        "max_steps": 10,
    }
    nested_plan = _linear_plan(
        middle={
            **_node(
                "composite",
                "unused",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_nodeset": True,
            "subplan": child,
        }
    )
    workflow = _write_emitted(
        tmp_path,
        nested_plan,
        """
export function start() { return {}; }
export function double(inputs) { return { out: inputs.number.value * 2 }; }
export function end() { return {}; }
export function unused() { throw new Error("composite binding must not run"); }
export function increment(inputs) { return { next: inputs.number.value + 1 }; }
""",
    )
    nested = _run_esm(
        workflow,
        """
const value = await workflow.runWorkflow({ number: 6 });
console.log(JSON.stringify(value));
""",
    )
    assert nested == {"answer": 12}

    body = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "loop.body",
        "inputs": [{"key": "current", "type": "number", "required": True}],
        "outputs": [{"type": "next", "cardinality": "exactly_one", "as": "next"}],
        "nodes": [
            _node("body_start", "start", terminal=True),
            _node(
                "increment",
                "increment",
                requires=[_requirement("number")],
                provides=[_provider("next", "next")],
            ),
            _node(
                "body_end",
                "end",
                requires=[_requirement("next")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "body_start", "target": "increment"},
            {"source": "increment", "target": "body_end"},
        ],
        "order": ["body_start", "increment", "body_end"],
        "max_steps": 10,
    }
    loop_plan = _linear_plan(
        middle={
            **_node(
                "loop",
                "unused",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_loop": True,
            "subplan": body,
            "loop": {
                "max_iterations": 5,
                "stop_after": 3,
                "carry": [{"from": "number", "as": "current", "update": "next"}],
                "outputs": [{"from": "current", "as": "out"}],
            },
        }
    )
    (tmp_path / "loop-workflow.mjs").write_text(
        emit_workflow_module(loop_plan).source,
        encoding="utf-8",
    )
    looped = _run_esm(
        tmp_path / "loop-workflow.mjs",
        """
const value = await workflow.runWorkflow({ number: 4 });
console.log(JSON.stringify(value));
""",
    )
    assert looped == {"answer": 7}

    loop_plan["nodes"][1]["loop"]["max_iterations"] = None
    (tmp_path / "unbounded-loop-workflow.mjs").write_text(
        emit_workflow_module(loop_plan).source,
        encoding="utf-8",
    )
    unbounded = _run_esm(
        tmp_path / "unbounded-loop-workflow.mjs",
        """
const value = workflow.runWorkflow({ number: 4 });
console.log(JSON.stringify(value));
""",
    )
    assert unbounded == {"answer": 7}


def _fake_driver(request, *, package_root, node_command="node"):
    out_dir = Path(request["outDir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    entry = out_dir / request["entryName"]
    entry.write_text("export const built = true;\n", encoding="utf-8")
    if request["sourcemap"] == "external":
        (out_dir / f"{request['entryName']}.map").write_text(
            '{"version":3,"sources":[],"mappings":""}\n',
            encoding="utf-8",
        )
    return DriverBuildResult(
        toolchain=ToolchainInfo(
            node="24.0.0",
            typescript="7.0.2",
            esbuild="0.28.1",
            lock_sha256="a" * 64,
            lock_files=("package-lock.json",),
        ),
        outputs=(str(entry),),
        inputs=(),
    )


@pytest.mark.parametrize("profile", ["esm-module", "single-esm", "web-app"])
def test_build_profiles_are_atomic_and_manifest_is_deterministic(
    tmp_path: Path,
    monkeypatch,
    profile: str,
) -> None:
    import vibeflow.targets.javascript.build.builder as builder_module

    project = tmp_path / "project"
    project.mkdir()
    (project / "package.json").write_text('{"private":true}\n', encoding="utf-8")
    (project / "package-lock.json").write_text('{"lockfileVersion":3}\n', encoding="utf-8")
    (project / "nodes.mjs").write_text(
        "export function start(){return {}}; export function value(){return {out:1}}; export function end(){return {}};\n",
        encoding="utf-8",
    )
    app_entry = project / "app.ts"
    app_entry.write_text(
        'import { runWorkflow } from "@vibeflow/workflow"; void runWorkflow;\n',
        encoding="utf-8",
    )
    html = project / "index.template.html"
    html.write_text(
        "<!doctype html><body><!-- VIBEFLOW_APP_ENTRY --></body>\n",
        encoding="utf-8",
    )
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "build",
        "inputs": [],
        "outputs": [{"type": "value", "cardinality": "exactly_one", "as": "value"}],
        "nodes": [
            _node("start", "start", module="nodes.mjs", terminal=True),
            _node("value", "value", module="nodes.mjs", provides=[_provider("out", "value")]),
            _node("end", "end", module="nodes.mjs", requires=[_requirement("value")], terminal=True),
        ],
        "routes": [
            {"source": "start", "target": "value"},
            {"source": "value", "target": "end"},
        ],
        "order": ["start", "value", "end"],
        "max_steps": 10,
    }
    monkeypatch.setattr(builder_module, "run_build_driver", _fake_driver)
    out_dir = tmp_path / f"dist-{profile}"
    request = BuildRequest(
        plan=plan,
        project_root=project,
        package_root=project,
        out_dir=out_dir,
        target="browser" if profile == "web-app" else "node",
        profile=profile,
        html_template=html if profile == "web-app" else None,
        app_entry=app_entry if profile == "web-app" else None,
    )
    first = build_aot(request)
    first_manifest = first.manifest.read_bytes()
    second = build_aot(
        BuildRequest(
            **{
                **request.__dict__,
                "replace": True,
            }
        )
    )
    assert second.manifest.read_bytes() == first_manifest
    manifest = json.loads(second.manifest.read_text(encoding="utf-8"))
    assert manifest["format"] == "vibeflow.aot-build.v1"
    assert "timestamp" not in manifest
    assert manifest["profile"] == profile
    assert second.entry.is_file()
    if profile == "web-app":
        html_output = second.entry.read_text(encoding="utf-8")
        assert "VIBEFLOW_APP_ENTRY" not in html_output
        assert '<script type="module" src="./index.js"></script>' in html_output

    old_manifest = second.manifest.read_bytes()

    def fail_driver(*args, **kwargs):
        raise AotToolchainError("VF_TYPESCRIPT", "synthetic failure")

    monkeypatch.setattr(builder_module, "run_build_driver", fail_driver)
    with pytest.raises(AotBuildError, match="synthetic failure"):
        build_aot(
            BuildRequest(
                **{
                    **request.__dict__,
                    "replace": True,
                }
            )
        )
    assert second.manifest.read_bytes() == old_manifest


def test_toolchain_requires_project_lockfile(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"private":true}\n', encoding="utf-8")
    with pytest.raises(AotToolchainError, match="lock"):
        probe_toolchain(tmp_path)


def test_toolchain_rejects_package_lock_version_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import vibeflow.targets.javascript.build.toolchain as toolchain_module

    (tmp_path / "package.json").write_text('{"private":true}\n', encoding="utf-8")
    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {
                    "": {},
                    "node_modules/typescript": {"version": "7.0.1"},
                    "node_modules/esbuild": {"version": "0.28.1"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        toolchain_module,
        "_run_driver",
        lambda *args, **kwargs: {
            "ok": True,
            "probe": {
                "node": "24.0.0",
                "typescript": "7.0.2",
                "esbuild": "0.28.1",
            },
        },
    )
    with pytest.raises(AotToolchainError, match="does not match"):
        probe_toolchain(tmp_path)


@pytest.mark.parametrize(
    ("source", "expected_code", "external_packages"),
    [
        (
            (
                "export const state: number[] = [];\n"
                "export function run() { state.push(1); return {}; }\n"
            ),
            "VF_IMPORT_SIDE_EFFECT",
            (),
        ),
        (
            'import "esbuild";\nexport function run() { return {}; }\n',
            "VF_IMPORT_SIDE_EFFECT",
            ("esbuild",),
        ),
    ],
)
def test_real_typescript_rejects_mutable_state_and_side_effect_imports(
    tmp_path: Path,
    source: str,
    expected_code: str,
    external_packages: tuple[str, ...],
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(source, encoding="utf-8")
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                external_packages=external_packages,
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert expected_code in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


def test_real_typescript_allows_recursively_frozen_module_constants(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        (
            "export const state = Object.freeze({\n"
            "  count: 0,\n"
            "  values: Object.freeze([] as readonly number[]),\n"
            "});\n"
            "export function run() { return {}; }\n"
        ),
        encoding="utf-8",
    )
    result = build_aot(
        BuildRequest(
            plan=_empty_real_plan(module),
            project_root=project,
            package_root=project,
            out_dir=project / "dist",
            target="node",
            profile="single-esm",
            import_policy={
                "owners": [
                    {"path": str(module), "kind": "node", "id": "test.run"}
                ]
            },
        )
    )
    assert result.entry.is_file()


@pytest.mark.parametrize("register_barrel", [False, True])
def test_real_typescript_rejects_unowned_barrel_and_cross_node_imports(
    tmp_path: Path,
    register_barrel: bool,
) -> None:
    project = _real_toolchain_project(tmp_path)
    first = project / "first.ts"
    barrel = project / "barrel.ts"
    second = project / "second.ts"
    first.write_text(
        'import { helper } from "./barrel.ts";\n'
        "export function run() { void helper; return {}; }\n",
        encoding="utf-8",
    )
    barrel.write_text(
        'export { helper } from "./second.ts";\n',
        encoding="utf-8",
    )
    second.write_text("export const helper = 1;\n", encoding="utf-8")
    owners = [
        {"path": str(first), "kind": "node", "id": "test.run"},
        {"path": str(second), "kind": "node", "id": "test.other"},
    ]
    if register_barrel:
        owners.append(
            {"path": str(barrel), "kind": "node", "id": "test.other"}
        )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(first),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={"owners": owners},
            )
        )
    codes = {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }
    assert (
        "VF_IMPORT_NODE_TO_NODE"
        if register_barrel
        else "VF_IMPORT_OWNER"
    ) in codes


def test_real_typescript_rejects_base_lib_host_io(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    base_lib = project / "base.ts"
    module.write_text(
        'import { read } from "./base.ts";\n'
        "export function run() { void read; return {}; }\n",
        encoding="utf-8",
    )
    base_lib.write_text(
        'export async function read() { return fetch("https://example.invalid"); }\n',
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="browser",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"},
                        {
                            "path": str(base_lib),
                            "kind": "base_lib",
                            "id": "test.base",
                        },
                    ],
                    "node_base_libs": {"test.run": ["test.base"]},
                    "base_lib_dependencies": {"test.base": []},
                },
            )
        )
    assert "VF_BASE_LIB_HOST_IO" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


@pytest.mark.parametrize(
    ("target", "implementation", "effect"),
    [
        pytest.param(
            "browser",
            "return new Date();",
            "Date",
            id="browser-date-construction",
        ),
        pytest.param(
            "node",
            "return Date.now();",
            "Date",
            id="node-date-now",
        ),
        pytest.param(
            "browser",
            "return performance.now();",
            "performance",
            id="browser-performance-now",
        ),
        pytest.param(
            "browser",
            "return Math.random();",
            "Math.random",
            id="browser-math-random",
        ),
        pytest.param(
            "node",
            "return Math.random();",
            "Math.random",
            id="node-math-random",
        ),
        pytest.param(
            "browser",
            "return crypto.getRandomValues(new Uint8Array(8));",
            "crypto",
            id="browser-web-crypto",
        ),
        pytest.param(
            "node",
            "return webcrypto.getRandomValues(new Uint8Array(8));",
            "webcrypto",
            id="node-webcrypto-global",
        ),
        pytest.param(
            "node",
            "return process.hrtime.bigint();",
            "process",
            id="node-process-hrtime",
        ),
    ],
)
def test_real_typescript_rejects_base_lib_nondeterminism_and_host_observation(
    tmp_path: Path,
    target: str,
    implementation: str,
    effect: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    base_lib = project / "base.ts"
    module.write_text(
        'import { effect } from "./base.ts";\n'
        "export function run() { void effect; return {}; }\n",
        encoding="utf-8",
    )
    base_lib.write_text(
        f"export function effect() {{ {implementation} }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target=target,
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"},
                        {
                            "path": str(base_lib),
                            "kind": "base_lib",
                            "id": "test.base",
                        },
                    ],
                    "node_base_libs": {"test.run": ["test.base"]},
                    "base_lib_dependencies": {"test.base": []},
                },
            )
        )
    host_findings = [
        diagnostic
        for diagnostic in caught.value.diagnostics
        if diagnostic.get("code") == "VF_BASE_LIB_HOST_IO"
    ]
    assert host_findings
    assert any(effect in str(finding.get("message")) for finding in host_findings)


@pytest.mark.parametrize("target", ["browser", "node"])
def test_real_typescript_allows_pure_math_base_lib_and_fake_capability(
    tmp_path: Path,
    target: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    base_lib = project / "base.ts"
    module.write_text(
        (
            'import { normalize } from "./base.ts";\n'
            "export function start() { return {}; }\n"
            "export function sample(inputs: any, _params: any, context: any) {\n"
            '  const value = context.capabilities["test.clock"].sample('
            "inputs.number.value);\n"
            "  return { out: normalize(value) };\n"
            "}\n"
            "export function end() { return {}; }\n"
        ),
        encoding="utf-8",
    )
    base_lib.write_text(
        (
            "export function normalize(value: number) {\n"
            "  return Math.max(0, Math.min(100, Math.abs(value)));\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    middle = _node(
        "sample",
        "sample",
        module=str(module),
        requires=[_requirement("number")],
        provides=[_provider("out", "answer")],
        capabilities=[{"id": "test.clock", "operations": ["sample"]}],
    )
    plan = _linear_plan(middle=middle)
    for node in plan["nodes"]:
        node["implementation"]["ref"] = str(module)
    plan["capabilities"] = [
        {
            "id": "test.clock",
            "operations": {
                "sample": {"input_type": "number", "output_type": "answer"}
            },
        }
    ]
    result = build_aot(
        BuildRequest(
            plan=plan,
            project_root=project,
            package_root=project,
            out_dir=project / "dist",
            target=target,
            profile="single-esm",
            import_policy={
                "owners": [
                    {"path": str(module), "kind": "node", "id": "test.nodes"},
                    {
                        "path": str(base_lib),
                        "kind": "base_lib",
                        "id": "test.base",
                    },
                ],
                "node_base_libs": {"test.nodes": ["test.base"]},
                "base_lib_dependencies": {"test.base": []},
            },
        )
    )
    value = _run_esm(
        result.entry,
        """
const value = await workflow.runWorkflow(
  { number: 4 },
  { capabilities: { "test.clock": { sample: input => -input } } },
);
console.log(JSON.stringify(value));
""",
    )
    assert value == {"answer": 4}


def test_real_typescript_never_allows_base_lib_node_builtins(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    base_lib = project / "base.ts"
    module.write_text(
        'import { read } from "./base.ts";\n'
        "export function run() { void read; return {}; }\n",
        encoding="utf-8",
    )
    base_lib.write_text(
        'import { readFile } from "node:fs/promises";\n'
        "export function read() { return readFile; }\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                external_packages=("node:fs",),
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"},
                        {
                            "path": str(base_lib),
                            "kind": "base_lib",
                            "id": "test.base",
                        },
                    ],
                    "node_base_libs": {"test.run": ["test.base"]},
                    "base_lib_dependencies": {"test.base": []},
                    "allowed_external_packages": ["node:fs"],
                },
            )
        )
    assert "VF_BASE_LIB_HOST_IO" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


def test_real_single_esm_rejects_unbundled_worker_resources(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    worker = project / "worker.ts"
    module.write_text(
        (
            "export function run() {\n"
            '  void new Worker(new URL("./worker.ts", import.meta.url), '
            '{ type: "module" });\n'
            "  return {};\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    worker.write_text("self.postMessage('ready');\n", encoding="utf-8")
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="browser",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert {
        "VF_SINGLE_ESM_WORKER",
        "VF_SINGLE_ESM_RESOURCE",
    } <= {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


@pytest.mark.parametrize(
    ("target", "context_type", "use_signal"),
    [
        (
            "browser",
            "{ readonly signal?: AbortSignal }",
            "context.signal?.throwIfAborted();",
        ),
        (
            "node",
            (
                "{ readonly signal?: { readonly aborted: boolean; "
                "readonly reason?: unknown; "
                "addEventListener(...args: any[]): void; "
                "removeEventListener(...args: any[]): void; "
                "throwIfAborted?(): void } }"
            ),
            "if (context.signal?.aborted) throw context.signal.reason;",
        ),
    ],
)
def test_real_typescript_node_context_has_portable_abort_signal(
    tmp_path: Path,
    target: str,
    context_type: str,
    use_signal: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        (
            "export function run(\n"
            "  _inputs: Readonly<Record<never, never>>,\n"
            "  _params: Readonly<Record<never, never>>,\n"
            f"  context: {context_type},\n"
            ") {\n"
            f"  {use_signal}\n"
            "  return {};\n"
            "}\n"
        ),
        encoding="utf-8",
    )
    result = build_aot(
        BuildRequest(
            plan=_empty_real_plan(module),
            project_root=project,
            package_root=project,
            out_dir=project / "dist",
            target=target,
            profile="single-esm",
            import_policy={
                "owners": [
                    {"path": str(module), "kind": "node", "id": "test.run"}
                ]
            },
        )
    )
    declaration_path = next(
        result.out_dir / name
        for name in result.files
        if name.endswith(".d.ts")
    )
    declarations = declaration_path.read_text(encoding="utf-8")
    assert "interface VibeFlowAbortSignal" in declarations
    assert "readonly signal?: VibeFlowAbortSignal" in declarations


@pytest.mark.parametrize(
    ("target", "body"),
    [
        (
            "browser",
            'return (globalThis as any).process.getBuiltinModule("node:fs");',
        ),
        (
            "browser",
            'return (globalThis as any)["process"];',
        ),
        (
            "browser",
            "const host = globalThis as any; return host.process;",
        ),
        (
            "browser",
            "const host = globalThis as any; const key = String(); return host[key];",
        ),
        (
            "browser",
            'return Reflect.get(globalThis, "process");',
        ),
        (
            "browser",
            'return Object.getOwnPropertyDescriptor(globalThis, "process");',
        ),
        (
            "node",
            "return (globalThis as any).document;",
        ),
        (
            "node",
            "const host = globalThis as any; return host.fetch;",
        ),
        (
            "node",
            "const host = globalThis as any; const key = String(); return host[key];",
        ),
        (
            "node",
            'return Reflect.get(globalThis, "document");',
        ),
    ],
)
def test_real_typescript_rejects_target_globals_through_host_object(
    tmp_path: Path,
    target: str,
    body: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        f"export function run() {{ {body} }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target=target,
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert "VF_IMPORT_TARGET_GLOBAL" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


@pytest.mark.parametrize(
    "body",
    [
        'return eval(\'import("./hidden.ts")\');',
        'return new Function(\'return import("./hidden.ts")\')();',
        'const make = Function; return new make("return 1")();',
        'return setTimeout("globalThis.compromised = true", 0);',
    ],
)
def test_real_typescript_rejects_runtime_string_evaluation(
    tmp_path: Path,
    body: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        f"export function run() {{ {body} }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert "VF_IMPORT_DYNAMIC_CODE" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


@pytest.mark.parametrize(
    "body",
    [
        (
            "(run as any).count = ((run as any).count ?? 0) + 1; "
            "return {};"
        ),
        (
            "const state = run; (state as any).count++; "
            "return {};"
        ),
        (
            'Object.defineProperty(run, "count", { value: 1 }); '
            "return {};"
        ),
    ],
)
def test_real_typescript_rejects_module_binding_state_mutation(
    tmp_path: Path,
    body: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        f"export function run() {{ {body} }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert "VF_MODULE_STATE" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


@pytest.mark.parametrize(
    "literal",
    [
        pytest.param("/a/g", id="global"),
        pytest.param("/a/y", id="sticky"),
    ],
)
def test_real_typescript_rejects_module_scoped_stateful_regexp(
    tmp_path: Path,
    literal: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        (
            f"const matcher = {literal};\n"
            'export function run() { return { value: matcher.test("a") }; }\n'
        ),
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    findings = [
        diagnostic
        for diagnostic in caught.value.diagnostics
        if diagnostic.get("code") == "VF_MODULE_STATE"
    ]
    assert findings
    assert "lastIndex" in str(findings[0].get("message"))


def test_real_typescript_function_local_regexp_is_isolated_between_runs(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        (
            "export function start() { return {}; }\n"
            "export function match() {\n"
            "  const matcher = /a/g;\n"
            '  return { out: matcher.test("a") ? 1 : 0 };\n'
            "}\n"
            "export function end() { return {}; }\n"
        ),
        encoding="utf-8",
    )
    plan = _linear_plan(
        middle=_node(
            "match",
            "match",
            module=str(module),
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
        )
    )
    for node in plan["nodes"]:
        node["implementation"]["ref"] = str(module)
    result = build_aot(
        BuildRequest(
            plan=plan,
            project_root=project,
            package_root=project,
            out_dir=project / "dist",
            target="node",
            profile="single-esm",
            import_policy={
                "owners": [
                    {"path": str(module), "kind": "node", "id": "test.nodes"}
                ]
            },
        )
    )
    values = _run_esm(
        result.entry,
        """
const first = await workflow.runWorkflow({ number: 1 });
const second = await workflow.runWorkflow({ number: 1 });
console.log(JSON.stringify([first, second]));
""",
    )
    assert values == [{"answer": 1}, {"answer": 1}]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "(Array.prototype as any).__vfCount = 1;",
            id="assignment",
        ),
        pytest.param(
            "delete (Map.prototype as any).__vfCache;",
            id="delete",
        ),
        pytest.param(
            "++(Object.prototype as any).__vfCount;",
            id="update",
        ),
        pytest.param(
            'Object.defineProperty(Array.prototype, "__vfCount", { value: 1 });',
            id="object-mutator",
        ),
        pytest.param(
            'Reflect.set(Set.prototype, "__vfCount", 1);',
            id="reflect-mutator",
        ),
        pytest.param(
            (
                "const shared = Array.prototype as any; "
                "shared.__vfCount = (shared.__vfCount ?? 0) + 1;"
            ),
            id="local-alias",
        ),
    ],
)
def test_real_typescript_rejects_builtin_prototype_mutation(
    tmp_path: Path,
    body: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        f"export function run() {{ {body} return {{}}; }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    findings = [
        diagnostic
        for diagnostic in caught.value.diagnostics
        if diagnostic.get("code") == "VF_MODULE_STATE"
    ]
    assert findings
    assert "builtin prototype" in str(findings[0].get("message"))


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "(Math as any).__vfCount = 1;",
            id="direct-namespace",
        ),
        pytest.param(
            "(Date as any).__vfCount++;",
            id="direct-constructor",
        ),
        pytest.param(
            (
                "const shared = JSON as any; "
                "shared.__vfCount = (shared.__vfCount ?? 0) + 1;"
            ),
            id="local-alias",
        ),
        pytest.param(
            'Object.defineProperty(Reflect, "__vfCount", { value: 1 });',
            id="object-mutator",
        ),
    ],
)
def test_real_typescript_rejects_builtin_object_mutation(
    tmp_path: Path,
    body: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        f"export function run() {{ {body} return {{}}; }}\n",
        encoding="utf-8",
    )
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    findings = [
        diagnostic
        for diagnostic in caught.value.diagnostics
        if diagnostic.get("code") == "VF_MODULE_STATE"
    ]
    assert findings
    assert "builtin object" in str(findings[0].get("message"))


def test_real_typescript_local_builtin_name_is_isolated_between_runs(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(
        (
            "export function start() { return {}; }\n"
            "export function count() {\n"
            "  const Array = { prototype: { count: 0 } };\n"
            "  const Math = { count: 0 };\n"
            "  Array.prototype.count += 1;\n"
            "  Math.count += 1;\n"
            "  return { out: Array.prototype.count + Math.count };\n"
            "}\n"
            "export function end() { return {}; }\n"
        ),
        encoding="utf-8",
    )
    plan = _linear_plan(
        middle=_node(
            "count",
            "count",
            module=str(module),
            requires=[_requirement("number")],
            provides=[_provider("out", "answer")],
        )
    )
    for node in plan["nodes"]:
        node["implementation"]["ref"] = str(module)
    result = build_aot(
        BuildRequest(
            plan=plan,
            project_root=project,
            package_root=project,
            out_dir=project / "dist",
            target="node",
            profile="single-esm",
            import_policy={
                "owners": [
                    {"path": str(module), "kind": "node", "id": "test.nodes"}
                ]
            },
        )
    )
    values = _run_esm(
        result.entry,
        """
const first = await workflow.runWorkflow({ number: 1 });
const second = await workflow.runWorkflow({ number: 1 });
console.log(JSON.stringify([first, second]));
""",
    )
    assert values == [{"answer": 2}, {"answer": 2}]


@pytest.mark.parametrize(
    "source",
    [
        (
            "function mark<T extends Function>(value: T): T {\n"
            "  (globalThis as any).__decorated = true;\n"
            "  return value;\n"
            "}\n"
            "@mark class Decorated {}\n"
            "export function run() { return {}; }\n"
        ),
        (
            "function makeBase() {\n"
            "  (globalThis as any).__heritage = true;\n"
            "  return class {};\n"
            "}\n"
            "class Derived extends makeBase() {}\n"
            "export function run() { return {}; }\n"
        ),
        (
            "function key() {\n"
            "  (globalThis as any).__computed = true;\n"
            '  return "method";\n'
            "}\n"
            "class Computed { [key()]() {} }\n"
            "export function run() { return {}; }\n"
        ),
        (
            "function key() {\n"
            "  (globalThis as any).__computed = true;\n"
            '  return "field";\n'
            "}\n"
            "export const value = Object.freeze({ [key()]: 1 });\n"
            "export function run() { return {}; }\n"
        ),
    ],
)
def test_real_typescript_rejects_class_definition_side_effects(
    tmp_path: Path,
    source: str,
) -> None:
    project = _real_toolchain_project(tmp_path)
    module = project / "node.ts"
    module.write_text(source, encoding="utf-8")
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_empty_real_plan(module),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="node",
                profile="single-esm",
                import_policy={
                    "owners": [
                        {"path": str(module), "kind": "node", "id": "test.run"}
                    ]
                },
            )
        )
    assert "VF_IMPORT_SIDE_EFFECT" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }


def _host_extension_build_request(
    project: Path,
    *,
    factory_source: str,
    entry_mode: str = "sync",
    target: str = "node",
    profile: str = "single-esm",
) -> BuildRequest:
    node = project / "node.ts"
    extension = project / "host-extension.ts"
    node.write_text("export function run() { return {}; }\n", encoding="utf-8")
    extension.write_text(factory_source, encoding="utf-8")
    plan = _empty_real_plan(node)
    plan["entry_mode"] = entry_mode
    html_template = None
    app_entry = None
    if profile == "web-app":
        html_template = project / "index.template.html"
        html_template.write_text(
            "<!doctype html><body><!-- VIBEFLOW_APP_ENTRY --></body>\n",
            encoding="utf-8",
        )
        app_entry = project / "app.ts"
        app_entry.write_text(
            'import { createWorkflowHost } from "@vibeflow/workflow";\n'
            "void createWorkflowHost;\n",
            encoding="utf-8",
        )
    return BuildRequest(
        plan=plan,
        project_root=project,
        package_root=project,
        out_dir=project / "dist",
        target=target,
        profile=profile,
        host_extensions=(
            {
                "id": "test.host",
                "module": str(extension),
                "export": "createHostExtension",
                "dependencies": [],
                "provides": [],
            },
        ),
        import_policy={
            "owners": [
                {
                    "path": str(node),
                    "kind": "node",
                    "id": "test.run",
                    "export": "run",
                    "completion": "immediate",
                },
                {
                    "path": str(extension),
                    "kind": "host_extension",
                    "id": "test.host",
                    "export": "createHostExtension",
                    "completion": "immediate",
                },
            ],
            "host_extension_dependencies": {"test.host": []},
        },
        html_template=html_template,
        app_entry=app_entry,
    )


@pytest.mark.parametrize(
    "factory_source",
    [
        (
            "export async function createHostExtension() {\n"
            "  return { start() {}, stop() {} };\n"
            "}\n"
        ),
        (
            "export function createHostExtension() {\n"
            "  return Promise.resolve({ start() {}, stop() {} });\n"
            "}\n"
        ),
    ],
)
def test_real_typescript_rejects_async_host_extension_factory(
    tmp_path: Path,
    factory_source: str,
) -> None:
    project = _real_toolchain_project(tmp_path)

    with pytest.raises(AotBuildError) as caught:
        build_aot(
            _host_extension_build_request(
                project,
                factory_source=factory_source,
            )
        )

    assert "VF_COMPLETION_IMMEDIATE_PROMISE" in {
        diagnostic.get("code") for diagnostic in caught.value.diagnostics
    }
    assert any(
        "host_extension 'test.host' factory" in str(
            diagnostic.get("message", "")
        )
        for diagnostic in caught.value.diagnostics
    )


def test_real_typescript_allows_async_host_extension_start_and_stop(
    tmp_path: Path,
) -> None:
    project = _real_toolchain_project(tmp_path)

    result = build_aot(
        _host_extension_build_request(
            project,
            factory_source=(
                "export function createHostExtension() {\n"
                "  return {\n"
                "    async start() { await Promise.resolve(); },\n"
                "    stop() { return Promise.resolve(); },\n"
                "  };\n"
                "}\n"
            ),
        )
    )

    assert result.entry.is_file()


@pytest.mark.parametrize(
    ("target", "profile"),
    [
        ("node", "esm-module"),
        ("node", "single-esm"),
        ("browser", "esm-module"),
        ("browser", "single-esm"),
        ("browser", "web-app"),
    ],
)
def test_real_typescript_builds_async_workflow_host_in_all_profiles(
    tmp_path: Path,
    target: str,
    profile: str,
) -> None:
    project = _real_toolchain_project(tmp_path)

    result = build_aot(
        _host_extension_build_request(
            project,
            factory_source=(
                "export function createHostExtension() {\n"
                "  return { start() {}, stop() {} };\n"
                "}\n"
            ),
            entry_mode="async",
            target=target,
            profile=profile,
        )
    )

    assert result.entry.is_file()
    declaration_files = [
        result.out_dir / name
        for name in result.files
        if name.endswith(".d.ts")
    ]
    assert len(declaration_files) == 1
    declaration = declaration_files[0].read_text(encoding="utf-8")
    assert "runWorkflowAsync(" in declaration
    assert "): Promise<WorkflowOutputs>;" in declaration
