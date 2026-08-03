from __future__ import annotations

from pathlib import Path

from tests.targets.javascript.test_aot_core import (
    _linear_plan,
    _node,
    _provider,
    _requirement,
    _run_esm,
    _write_emitted,
)


_NESTED_SOURCE = """
export function start() { return {}; }
export function end() { return {}; }
export function unused() { throw new Error("nodeset binding must not run"); }
export async function delayed(inputs) {
  await new Promise(resolve => setTimeout(resolve, 1));
  return { out: inputs.number.value * 2 };
}
export async function reject() {
  await Promise.resolve();
  throw new Error("inner synthetic failure");
}
export async function hang() { return new Promise(() => {}); }
export function value(inputs) { return { out: inputs.number.value * 2 }; }
export function tick() { return {}; }
export function after() { globalThis.__vfCalls.push("after"); return {}; }
export function rootAfter() { globalThis.__vfCalls.push("root-after"); return {}; }
"""


def _nested_result_plan(
    *,
    implementation: str,
    schedule: str = "result_key",
) -> dict[str, object]:
    leaf = {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.leaf",
        "entry_mode": "async",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": "answer", "cardinality": "exactly_one", "as": "answer"}
        ],
        "nodes": [
            _node("leaf_start", "start", terminal=True),
            _node(
                "work",
                implementation,
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
                completion="suspend",
                async_mode=schedule,
                result_key="out",
            ),
            _node(
                "leaf_end",
                "end",
                requires=[_requirement("answer")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "leaf_start", "target": "work"},
            {"source": "work", "target": "leaf_end"},
        ],
        "order": ["leaf_start", "work", "leaf_end"],
        "max_steps": 10,
    }
    outer = {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.outer",
        "entry_mode": "async",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": "answer", "cardinality": "exactly_one", "as": "answer"}
        ],
        "nodes": [
            _node("outer_start", "start", terminal=True),
            {
                **_node(
                    "inner",
                    "unused",
                    requires=[_requirement("number")],
                    provides=[_provider("out", "answer")],
                ),
                "is_nodeset": True,
                "subplan": leaf,
            },
            _node("after", "after", requires=[_requirement("answer")]),
            _node(
                "outer_end",
                "end",
                requires=[_requirement("answer")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "outer_start", "target": "inner"},
            {"source": "inner", "target": "after"},
            {"source": "after", "target": "outer_end"},
        ],
        "order": ["outer_start", "inner", "after", "outer_end"],
        "max_steps": 10,
    }
    return _linear_plan(
        middle={
            **_node(
                "outer",
                "unused",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_nodeset": True,
            "subplan": outer,
        },
        entry_mode="async",
    )


def _nested_detached_plan() -> dict[str, object]:
    leaf = {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.detached.leaf",
        "entry_mode": "async",
        "inputs": [{"key": "number", "type": "number", "required": True}],
        "outputs": [
            {"type": "answer", "cardinality": "exactly_one", "as": "answer"}
        ],
        "nodes": [
            _node("leaf_start", "start", terminal=True),
            _node(
                "side",
                "hang",
                completion="suspend",
                async_mode="detached",
            ),
            _node(
                "value",
                "value",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            _node(
                "leaf_end",
                "end",
                requires=[_requirement("answer")],
                terminal=True,
            ),
        ],
        "routes": [
            {"source": "leaf_start", "target": "side"},
            {"source": "leaf_start", "target": "value"},
            {"source": "value", "target": "leaf_end"},
        ],
        "order": ["leaf_start", "side", "value", "leaf_end"],
        "max_steps": 10,
    }
    outer = _nested_result_plan(implementation="delayed")["nodes"][1]["subplan"]
    outer = dict(outer)
    outer["nodes"] = list(outer["nodes"])
    outer["nodes"][1] = {
        **outer["nodes"][1],
        "subplan": leaf,
    }
    return _linear_plan(
        middle={
            **_node(
                "outer",
                "unused",
                requires=[_requirement("number")],
                provides=[_provider("out", "answer")],
            ),
            "is_nodeset": True,
            "subplan": outer,
        },
        entry_mode="async",
    )


def _nested_max_steps_plan() -> dict[str, object]:
    leaf = {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.steps.leaf",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("leaf_start", "start", terminal=True),
            _node("tick", "tick"),
        ],
        "routes": [
            {"source": "leaf_start", "target": "tick"},
            {"source": "tick", "target": "tick"},
        ],
        "order": ["leaf_start", "tick"],
        "max_steps": 3,
    }
    outer = {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.steps.outer",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("outer_start", "start", terminal=True),
            {
                **_node("inner", "unused"),
                "is_nodeset": True,
                "subplan": leaf,
            },
            _node("after", "after"),
            _node("outer_end", "end", terminal=True),
        ],
        "routes": [
            {"source": "outer_start", "target": "inner"},
            {"source": "inner", "target": "after"},
            {"source": "after", "target": "outer_end"},
        ],
        "order": ["outer_start", "inner", "after", "outer_end"],
        "max_steps": 10,
    }
    return {
        "abi_version": "vibeflow.workflow.v3",
        "workflow_id": "nested.steps",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [],
        "nodes": [
            _node("root_start", "start", terminal=True),
            {
                **_node("outer", "unused"),
                "is_nodeset": True,
                "subplan": outer,
            },
            _node("root_after", "rootAfter"),
            _node("root_end", "end", terminal=True),
        ],
        "routes": [
            {"source": "root_start", "target": "outer"},
            {"source": "outer", "target": "root_after"},
            {"source": "root_after", "target": "root_end"},
        ],
        "order": ["root_start", "outer", "root_after", "root_end"],
        "max_steps": 10,
    }


def test_nested_nodeset_deferred_result_has_qualified_task_trace(
    tmp_path: Path,
) -> None:
    workflow = _write_emitted(
        tmp_path,
        _nested_result_plan(implementation="delayed"),
        _NESTED_SOURCE,
    )

    result = _run_esm(
        workflow,
        """
const trace = [];
const value = await workflow.runWorkflowAsync(
  { number: 6 },
  { trace: "full", onTrace: event => trace.push(event) },
);
const tasks = trace
  .filter(event => event.kind === "async_result" || event.kind === "async_result_join")
  .map(event => ({
    kind: event.kind,
    nodePath: event.nodePath,
    blockPath: event.blockPath,
  }));
console.log(JSON.stringify({ value, tasks, calls: globalThis.__vfCalls }));
""",
    )

    assert result == {
        "value": {"answer": 12},
        "tasks": [
            {
                "kind": "async_result",
                "nodePath": "outer.inner.work",
                "blockPath": "/outer/inner",
            },
            {
                "kind": "async_result_join",
                "nodePath": "outer.inner.work",
                "blockPath": "/outer/inner",
            },
        ],
        "calls": ["after"],
    }


def test_nested_nodeset_reject_stops_outer_scheduling_and_preserves_path(
    tmp_path: Path,
) -> None:
    workflow = _write_emitted(
        tmp_path,
        _nested_result_plan(implementation="reject"),
        _NESTED_SOURCE,
    )

    result = _run_esm(
        workflow,
        """
let failure;
try {
  await workflow.runWorkflowAsync({ number: 1 });
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
    cause: error.cause?.message,
  };
}
console.log(JSON.stringify({ failure, calls: globalThis.__vfCalls }));
""",
    )

    assert result == {
        "failure": {
            "code": "VF_NODE_FAILED",
            "nodePath": "outer.inner.work",
            "blockPath": "/outer/inner",
            "cause": "inner synthetic failure",
        },
        "calls": [],
    }


def test_nested_nodeset_cancel_abandons_task_and_stops_outer_scheduling(
    tmp_path: Path,
) -> None:
    workflow = _write_emitted(
        tmp_path,
        _nested_result_plan(implementation="hang"),
        _NESTED_SOURCE,
    )

    result = _run_esm(
        workflow,
        """
const trace = [];
const controller = new AbortController();
setTimeout(() => controller.abort("stop nested task"), 5);
let failure;
try {
  await workflow.runWorkflowAsync(
    { number: 1 },
    { signal: controller.signal, trace: "full", onTrace: event => trace.push(event) },
  );
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
const task = trace.find(event => event.kind === "async_result");
console.log(JSON.stringify({
  failure,
  task: {
    nodePath: task?.nodePath,
    blockPath: task?.blockPath,
  },
  calls: globalThis.__vfCalls,
}));
""",
    )

    # Cancellation is observed by the outer nodeset await boundary, while the
    # task trace identifies the concrete suspended child task.
    assert result == {
        "failure": {
            "code": "VF_ABORTED",
            "nodePath": "outer",
            "blockPath": "/",
        },
        "task": {
            "nodePath": "outer.inner.work",
            "blockPath": "/outer/inner",
        },
        "calls": [],
    }


def test_nested_detached_cleanup_timeout_preserves_task_location(
    tmp_path: Path,
) -> None:
    workflow = _write_emitted(tmp_path, _nested_detached_plan(), _NESTED_SOURCE)

    result = _run_esm(
        workflow,
        """
const trace = [];
let failure;
try {
  await workflow.runWorkflowAsync(
    { number: 3 },
    {
      detachedTimeoutMs: 5,
      trace: "full",
      onTrace: event => trace.push(event),
    },
  );
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
const task = trace.find(event => event.kind === "async_detached");
console.log(JSON.stringify({
  failure,
  task: {
    nodePath: task?.nodePath,
    blockPath: task?.blockPath,
  },
}));
""",
    )

    assert result == {
        "failure": {
            "code": "VF_ASYNC_FLUSH_TIMEOUT",
            "nodePath": "outer.inner.side",
            "blockPath": "/outer/inner",
        },
        "task": {
            "nodePath": "outer.inner.side",
            "blockPath": "/outer/inner",
        },
    }


def test_nested_max_steps_preserves_path_and_stops_parent_scheduling(
    tmp_path: Path,
) -> None:
    workflow = _write_emitted(tmp_path, _nested_max_steps_plan(), _NESTED_SOURCE)

    result = _run_esm(
        workflow,
        """
let failure;
try {
  await workflow.runWorkflowAsync({});
} catch (error) {
  failure = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
console.log(JSON.stringify({ failure, calls: globalThis.__vfCalls }));
""",
    )

    assert result == {
        "failure": {
            "code": "VF_MAX_STEPS",
            "nodePath": "outer.inner.tick",
            "blockPath": "/outer/inner",
        },
        "calls": [],
    }
