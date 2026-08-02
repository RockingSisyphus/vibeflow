from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sandbox_support import run_node


def execution_model_case(
    sync_result: Any,
    async_result: Any,
    detached_result: Any,
) -> Any:
    sync_payload = sync_result.prepared.payload
    async_payload = async_result.prepared.payload
    detached_payload = detached_result.prepared.payload

    def nodes(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        entry = payload["entry_block"]
        block = next(item for item in payload["blocks"] if item["id"] == entry)
        return {item["id"]: item for item in block["nodes"]}

    def tasks(payload: dict[str, Any]) -> list[dict[str, Any]]:
        entry = payload["entry_block"]
        block = next(item for item in payload["blocks"] if item["id"] == entry)
        return list(block["tasks"])

    sync_nodes = nodes(sync_payload)
    async_nodes = nodes(async_payload)
    detached_nodes = nodes(detached_payload)
    if sync_payload["entry_mode"] != "sync":
        raise AssertionError(sync_payload["entry_mode"])
    if any(
        (
            item["completion"],
            item["schedule"],
            item["executor"],
        )
        != ("immediate", "inline", "current")
        for item in sync_nodes.values()
    ):
        raise AssertionError(sync_nodes)
    if tasks(sync_payload):
        raise AssertionError(tasks(sync_payload))

    if async_payload["entry_mode"] != "async":
        raise AssertionError(async_payload["entry_mode"])
    expected_async = {
        "double": ("suspend", "deferred", "event_loop"),
        "read": ("suspend", "inline", "event_loop"),
    }
    for node_id, expected in expected_async.items():
        item = async_nodes[node_id]
        actual = (
            item["completion"],
            item["schedule"],
            item["executor"],
        )
        if actual != expected:
            raise AssertionError((node_id, actual, expected))
    async_tasks = tasks(async_payload)
    if async_tasks != [
        {
            "id": "block:/:task:double",
            "node_id": "double",
            "schedule": "deferred",
            "executor": "event_loop",
            "result_key": "doubled",
        }
    ]:
        raise AssertionError(async_tasks)

    audit = detached_nodes["audit"]
    if (
        audit["completion"],
        audit["schedule"],
        audit["executor"],
    ) != ("suspend", "detached", "event_loop"):
        raise AssertionError(audit)
    detached_tasks = tasks(detached_payload)
    if detached_tasks != [
        {
            "id": "block:/:task:audit",
            "node_id": "audit",
            "schedule": "detached",
            "executor": "event_loop",
        }
    ]:
        raise AssertionError(detached_tasks)
    all_nodes = [
        *sync_nodes.values(),
        *async_nodes.values(),
        *detached_nodes.values(),
    ]
    if any(item["executor"] == "thread" for item in all_nodes):
        raise AssertionError("JS AOT unexpectedly planned a thread executor")

    sync_runtime = run_node(
        sync_result.entry,
        """
assert(typeof workflow.runWorkflow === "function", "sync entry is missing");
assert(!("runWorkflowAsync" in workflow), "sync build leaked async entry");
const value = workflow.runWorkflow({ x: 10, a: 8, b: 3 });
assert(!(value instanceof Promise), "sync entry returned a Promise");
assert(typeof value?.then === "undefined", "sync result is thenable");
assert(value.result === 15, JSON.stringify(value));
process.stdout.write(JSON.stringify({
  result: value,
  isPromise: value instanceof Promise,
}));
""",
    )
    async_runtime = run_node(
        async_result.entry,
        """
assert(
  typeof workflow.runWorkflowAsync === "function",
  "async entry is missing",
);
assert(!("runWorkflow" in workflow), "async build leaked sync entry");
let releaseRead;
let readCalls = 0;
let settled = false;
const pending = workflow.runWorkflowAsync(
  { x: 6, key: "held" },
  {
    capabilities: {
      "sandbox.storage": {
        read: request => {
          readCalls += 1;
          assert(request.key === "held", JSON.stringify(request));
          return new Promise(resolve => {
            releaseRead = () => resolve({ value: "released" });
          });
        },
      },
    },
  },
);
assert(pending instanceof Promise, "async entry did not return a Promise");
pending.then(() => { settled = true; });
await new Promise(resolve => setImmediate(resolve));
assert(readCalls === 1, `read calls: ${readCalls}`);
assert(!settled, "workflow completed before the suspending Capability");
releaseRead();
const value = await pending;
assert(value.doubled === 12, JSON.stringify(value));
assert(value.value === "released", JSON.stringify(value));
process.stdout.write(JSON.stringify({
  result: value,
  readCalls,
  settled,
  isPromise: pending instanceof Promise,
}));
""",
    )
    return {
        "plans": {
            "sync": {
                node_id: {
                    key: item[key]
                    for key in ("completion", "schedule", "executor")
                }
                for node_id, item in sync_nodes.items()
            },
            "asyncTasks": async_tasks,
            "detachedTasks": detached_tasks,
        },
        "runtime": {
            "sync": sync_runtime,
            "async": async_runtime,
        },
    }


def nested_async_case(result: Any) -> Any:
    payload = result.prepared.payload
    inner = next(
        block
        for block in payload["blocks"]
        if block.get("path") == ["outer", "inner"]
    )
    if inner["tasks"] != [
        {
            "id": "block:/outer/inner:task:double",
            "node_id": "double",
            "schedule": "deferred",
            "executor": "event_loop",
            "result_key": "doubled",
        },
        {
            "id": "block:/outer/inner:task:audit",
            "node_id": "audit",
            "schedule": "detached",
            "executor": "event_loop",
        },
    ]:
        raise AssertionError(inner["tasks"])

    runtime = run_node(
        result.entry,
        """
const trace = [];
const value = await workflow.runWorkflowAsync(
  { x: 7 },
  {
    trace: "full",
    onTrace: event => trace.push(event),
    capabilities: {
      "sandbox.audit": {
        record: async request => {
          assert(request.label === "nested-async", JSON.stringify(request));
          return { accepted: true };
        },
      },
    },
  },
);
assert(value.doubled === 14, JSON.stringify(value));
const taskEvents = trace
  .filter(event => [
    "async_result",
    "async_result_join",
    "async_detached",
    "async_detached_done",
  ].includes(event.kind))
  .map(event => ({
    kind: event.kind,
    nodePath: event.nodePath,
    blockPath: event.blockPath,
  }));
for (const event of taskEvents) {
  assert(
    event.nodePath === "outer.inner.double"
      || event.nodePath === "outer.inner.audit",
    JSON.stringify(taskEvents),
  );
  assert(event.blockPath === "/outer/inner", JSON.stringify(taskEvents));
}
let timeout;
try {
  await workflow.runWorkflowAsync(
    { x: 3 },
    {
      detachedTimeoutMs: 5,
      capabilities: {
        "sandbox.audit": { record: () => new Promise(() => {}) },
      },
    },
  );
} catch (error) {
  timeout = {
    code: error.code,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
assert(timeout.code === "VF_ASYNC_FLUSH_TIMEOUT", JSON.stringify(timeout));
assert(timeout.nodePath === "outer.inner.audit", JSON.stringify(timeout));
assert(timeout.blockPath === "/outer/inner", JSON.stringify(timeout));
const recovered = await workflow.runWorkflowAsync(
  { x: 4 },
  {
    capabilities: {
      "sandbox.audit": {
        record: async () => ({ accepted: true }),
      },
    },
  },
);
assert(recovered.doubled === 8, JSON.stringify(recovered));
process.stdout.write(JSON.stringify({
  value,
  taskEvents,
  timeout,
  recovered,
}));
""",
    )
    return {
        "tasks": inner["tasks"],
        "runtime": runtime,
    }


def edge_role_case(result: Any) -> Any:
    entry_block = result.prepared.plan.block(
        result.prepared.plan.entry_block
    )
    roles = {
        (route.source, route.target): (route.schedule, route.transfer)
        for route in entry_block.routes
    }
    if roles.get(("seed", "consume")) != (False, True):
        raise AssertionError(f"invalid transfer-only route: {roles}")
    if roles.get(("poison", "consume")) != (True, False):
        raise AssertionError(f"invalid schedule-only route: {roles}")
    runtime = run_node(
        result.entry,
        """
const trace = [];
const result = await workflow.runWorkflow(
  { x: 10 },
  { trace: "full", onTrace: event => trace.push(event) },
);
assert(result.result === 22, JSON.stringify(result));
const nodes = trace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodeId);
assert(
  JSON.stringify(nodes) ===
    '["start","seed","delay","poison","consume","end"]',
  JSON.stringify(nodes),
);
process.stdout.write(JSON.stringify({ result, nodes }));
""",
    )
    return {
        "roles": {
            f"{source}->{target}": role
            for (source, target), role in roles.items()
        },
        "runtime": runtime,
    }


def detached_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
let completed = false;
let receivedSignal = false;
const trace = [];
const controller = new AbortController();
const options = {
  signal: controller.signal,
  trace: "full",
  onTrace: event => trace.push(event),
  capabilities: {
    "sandbox.audit": {
      record: async (request, context) => {
        assert(request.label === "detached-complete", JSON.stringify(request));
        receivedSignal = context.signal === controller.signal;
        await new Promise(resolve => setTimeout(resolve, 10));
        completed = true;
        return { accepted: true };
      },
    },
  },
};
const result = await workflow.runWorkflowAsync({ x: 7 }, options);
assert(result.result === 7, JSON.stringify(result));
assert(completed, "runWorkflow returned before detached cleanup");
assert(receivedSignal, "Capability did not receive the invocation signal");
const kinds = trace.map(event => event.kind);
assert(kinds.includes("async_detached"), JSON.stringify(kinds));
assert(kinds.includes("async_detached_done"), JSON.stringify(kinds));
let timeout;
try {
  await workflow.runWorkflowAsync(
    { x: 9 },
    {
      detachedTimeoutMs: 10,
      capabilities: {
        "sandbox.audit": {
          record: () => new Promise(() => {}),
        },
      },
    },
  );
} catch (error) {
  timeout = { code: error.code, nodePath: error.nodePath };
}
assert(timeout.code === "VF_ASYNC_FLUSH_TIMEOUT", JSON.stringify(timeout));
assert(timeout.nodePath === "audit", JSON.stringify(timeout));
const recovered = await workflow.runWorkflowAsync({ x: 11 }, {
  capabilities: {
    "sandbox.audit": {
      record: async () => ({ accepted: true }),
    },
  },
});
assert(recovered.result === 11, JSON.stringify(recovered));
let releaseLeft;
let releaseRight;
let leftCalls = 0;
let rightCalls = 0;
let leftResolved = false;
let rightResolved = false;
const leftTrace = [];
const rightTrace = [];
const leftRun = workflow.runWorkflowAsync(
  { x: 21 },
  {
    trace: "full",
    onTrace: event => leftTrace.push(event),
    capabilities: {
      "sandbox.audit": {
        record: () => {
          leftCalls += 1;
          return new Promise(resolve => { releaseLeft = resolve; });
        },
      },
    },
  },
).then(value => {
  leftResolved = true;
  return value;
});
const rightRun = workflow.runWorkflowAsync(
  { x: 34 },
  {
    trace: "boundary",
    onTrace: event => rightTrace.push(event),
    capabilities: {
      "sandbox.audit": {
        record: () => {
          rightCalls += 1;
          return new Promise(resolve => { releaseRight = resolve; });
        },
      },
    },
  },
).then(value => {
  rightResolved = true;
  return value;
});
await new Promise(resolve => setImmediate(resolve));
assert(leftCalls === 1 && rightCalls === 1, "detached tasks were not isolated");
assert(!leftResolved && !rightResolved, "a detached call returned too early");
releaseLeft({ accepted: true });
const concurrentLeft = await leftRun;
assert(leftResolved && !rightResolved, "right task leaked into left cleanup");
releaseRight({ accepted: true });
const concurrentRight = await rightRun;
assert(rightResolved, "right detached task did not complete");
assert(concurrentLeft.result === 21, JSON.stringify(concurrentLeft));
assert(concurrentRight.result === 34, JSON.stringify(concurrentRight));
assert(
  leftTrace.some(event => event.kind === "async_detached_done"),
  JSON.stringify(leftTrace),
);
assert(
  JSON.stringify(rightTrace.map(event => event.kind)) ===
    '["run_start","run_end"]',
  JSON.stringify(rightTrace),
);
process.stdout.write(JSON.stringify({
  result,
  completed,
  receivedSignal,
  timeout,
  recovered,
  concurrent: {
    left: concurrentLeft,
    right: concurrentRight,
    leftCalls,
    rightCalls,
  },
}));
""",
        timeout=45,
    )


def nested_override_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const trace = [];
const result = await workflow.runWorkflow(
  { x: 5 },
  { trace: "full", onTrace: event => trace.push(event) },
);
assert(result.result === 19, JSON.stringify(result));
assert(result.defaultResult === 11, JSON.stringify(result));
const nodePaths = trace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodePath);
assert(nodePaths.includes("outer.inner.math"), JSON.stringify(nodePaths));
assert(nodePaths.includes("outer.sibling.math"), JSON.stringify(nodePaths));
const nodesetPaths = trace
  .filter(event => event.kind === "nodeset_enter")
  .map(event => event.nodePath);
assert(nodesetPaths.includes("outer"), JSON.stringify(nodesetPaths));
assert(nodesetPaths.includes("outer.inner"), JSON.stringify(nodesetPaths));
assert(nodesetPaths.includes("outer.sibling"), JSON.stringify(nodesetPaths));
process.stdout.write(JSON.stringify({ result, nodePaths, nodesetPaths }));
""",
    )


def loop_max_error_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const trace = [];
let failure;
try {
  await workflow.runWorkflow(
    { x: 1 },
    { trace: "full", onTrace: event => trace.push(event) },
  );
} catch (error) {
  failure = {
    instance: error instanceof workflow.VibeFlowWorkflowError,
    code: error.code,
    workflowId: error.workflowId,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
  };
}
assert(failure.instance, JSON.stringify(failure));
assert(failure.code === "VF_MAX_STEPS", JSON.stringify(failure));
assert(failure.workflowId === "loop_max_failure", JSON.stringify(failure));
assert(failure.nodePath === "loop", JSON.stringify(failure));
assert(failure.blockPath === "/", JSON.stringify(failure));
const iterations = trace.filter(event => event.kind === "loop_iteration");
const started = trace
  .filter(event => event.kind === "node_start")
  .map(event => ({ id: event.nodeId, path: event.nodePath }));
assert(iterations.length === 2, JSON.stringify(iterations));
assert(!started.some(event => event.path === "end"), JSON.stringify(started));
process.stdout.write(JSON.stringify({
  failure,
  iterations: iterations.map(event => event.iteration),
  started,
}));
""",
    )


def runtime_error_case(
    entry: Path,
    *,
    workflow_id: str,
    expected_code: str,
    expected_cause: str = "",
) -> Any:
    return run_node(
        entry,
        f"""
const trace = [];
let failure;
try {{
  await workflow.runWorkflow(
    {{ x: 5 }},
    {{ trace: "full", onTrace: event => trace.push(event) }},
  );
}} catch (error) {{
  failure = {{
    instance: error instanceof workflow.VibeFlowWorkflowError,
    code: error.code,
    workflowId: error.workflowId,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
    cause: error.cause?.message ?? "",
  }};
}}
assert(failure.instance, JSON.stringify(failure));
assert(failure.code === {json.dumps(expected_code)}, JSON.stringify(failure));
assert(failure.workflowId === {json.dumps(workflow_id)}, JSON.stringify(failure));
assert(failure.nodePath === "invalid", JSON.stringify(failure));
assert(failure.blockPath === "/", JSON.stringify(failure));
assert(
  failure.cause === {json.dumps(expected_cause)},
  JSON.stringify(failure),
);
const nodes = trace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodeId);
assert(!nodes.includes("end"), JSON.stringify(nodes));
process.stdout.write(JSON.stringify({{ failure, nodes }}));
""",
    )


__all__ = [
    "detached_case",
    "edge_role_case",
    "execution_model_case",
    "loop_max_error_case",
    "nested_override_case",
    "runtime_error_case",
]
