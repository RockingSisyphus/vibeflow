from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sandbox_support import run_node


def import_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
assert(typeof workflow.runWorkflow === "function", "runWorkflow is missing");
assert(typeof workflow.VibeFlowWorkflowError === "function", "error type is missing");
await new Promise(resolve => setImmediate(resolve));
assert(importFailures.length === 0, JSON.stringify(importFailures));
process.removeListener("unhandledRejection", captureImportFailure);
process.stdout.write(JSON.stringify({
  exports: Object.keys(workflow).sort(),
  imported: true,
  importFailures,
}));
""",
        before_import="""
const importFailures = [];
const captureImportFailure = error => {
  importFailures.push({
    name: error?.name ?? "",
    code: error?.code ?? "",
    message: error?.message ?? String(error),
  });
};
process.on("unhandledRejection", captureImportFailure);
""",
    )


def input_error_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
function shape(error, trace) {
  return {
    instance: error instanceof workflow.VibeFlowWorkflowError,
    code: error.code,
    workflowId: error.workflowId,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
    traceKinds: trace.map(event => event.kind),
  };
}
async function failure(inputs) {
  const trace = [];
  try {
    await workflow.runWorkflow(inputs, {
      trace: "full",
      onTrace: event => trace.push(event),
    });
    return { code: "NO_ERROR" };
  } catch (error) {
    return shape(error, trace);
  }
}
const missing = await failure({ x: 1, a: 2 });
const unknown = await failure({ x: 1, a: 2, b: 3, surprise: 4 });
const schema = await failure({ x: "bad", a: 2, b: 3 });
let trace;
try {
  await workflow.runWorkflow(
    { x: 1, a: 2, b: 3 },
    { trace: "full", onTrace() { throw new Error("trace sink failed"); } },
  );
} catch (error) {
  trace = shape(error, []);
}
assert(missing.code === "VF_INPUT_REQUIRED", JSON.stringify(missing));
assert(unknown.code === "VF_INPUT_UNKNOWN", JSON.stringify(unknown));
assert(schema.code === "VF_INPUT_SCHEMA", JSON.stringify(schema));
assert(trace.code === "VF_TRACE_SINK_FAILED", JSON.stringify(trace));
for (const failure of [missing, unknown, schema, trace]) {
  assert(failure.instance, JSON.stringify(failure));
  assert(failure.workflowId === "linear", JSON.stringify(failure));
  assert(failure.nodePath === "", JSON.stringify(failure));
  assert(failure.blockPath === "/", JSON.stringify(failure));
}
for (const failure of [missing, unknown, schema]) {
  assert(
    !failure.traceKinds.some(kind => kind.startsWith("node_")),
    JSON.stringify(failure),
  );
}
process.stdout.write(JSON.stringify({ missing, unknown, schema, trace }));
""",
    )


def loop_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const trace = [];
const result = await workflow.runWorkflow(
  { x: 4 },
  { trace: "full", onTrace: event => trace.push(event) },
);
const iterations = trace.filter(event => event.kind === "loop_iteration");
assert(result.result === 7, JSON.stringify(result));
assert(result.iterations === 3, JSON.stringify(result));
assert(iterations.length === 3, JSON.stringify(iterations));
process.stdout.write(JSON.stringify({
  result,
  iterationPaths: iterations.map(event => event.nodePath),
}));
""",
    )






def capability_error_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
function shape(error) {
  return {
    instance: error instanceof workflow.VibeFlowWorkflowError,
    code: error.code,
    workflowId: error.workflowId,
    nodePath: error.nodePath,
    blockPath: error.blockPath,
    cause: error.cause?.message ?? "",
  };
}
const missingTrace = [];
let missing;
try {
  await workflow.runWorkflowAsync(
    { x: 1, key: "missing" },
    { trace: "full", onTrace: event => missingTrace.push(event) },
  );
} catch (error) {
  missing = shape(error);
}
let preCalls = 0;
const pre = new AbortController();
pre.abort("already cancelled");
const preTrace = [];
let preCancelled;
try {
  await workflow.runWorkflowAsync(
    { x: 1, key: "pre" },
    {
      signal: pre.signal,
      trace: "full",
      onTrace: event => preTrace.push(event),
      capabilities: {
        "sandbox.storage": {
          read() { preCalls += 1; return { value: "wrong" }; },
        },
      },
    },
  );
} catch (error) {
  preCancelled = shape(error);
}
let liveCalls = 0;
let liveSignal = false;
const live = new AbortController();
const liveTrace = [];
let liveCancelled;
try {
  await workflow.runWorkflowAsync(
    { x: 1, key: "live" },
    {
      signal: live.signal,
      trace: "full",
      onTrace: event => liveTrace.push(event),
      capabilities: {
        "sandbox.storage": {
          read(_request, context) {
            liveCalls += 1;
            liveSignal = context.signal !== live.signal && typeof context.signal.addEventListener === "function";
            queueMicrotask(() => live.abort(new Error("cancel in flight")));
            return new Promise(resolve=>context.signal.addEventListener("abort",()=>resolve({value:"cancelled"}),{once:true}));
          },
        },
      },
    },
  );
} catch (error) {
  liveCancelled = shape(error);
}
let wrongOutput;
try {
  await workflow.runWorkflowAsync(
    { x: 2, key: "wrong" },
    {
      capabilities: {
        "sandbox.storage": {
          read: async () => ({ value: 42 }),
        },
      },
    },
  );
} catch (error) {
  wrongOutput = shape(error);
}
const recovered = await workflow.runWorkflowAsync(
  { x: 3, key: "recovered" },
  {
    capabilities: {
      "sandbox.storage": {
        read: async request => ({ value: `ok:${request.key}` }),
      },
    },
  },
);
assert(missing.code === "VF_CAPABILITY_MISSING", JSON.stringify(missing));
assert(preCancelled.code === "VF_ABORTED" && preCalls === 0, "pre-abort scheduled work");
assert(liveCancelled.code === "VF_ABORTED" && liveCalls === 1, "live abort failed");
assert(liveSignal, "Capability did not receive the invocation signal");
assert(wrongOutput.code === "VF_CAPABILITY_OUTPUT", JSON.stringify(wrongOutput));
assert(recovered.doubled === 6 && recovered.value === "ok:recovered");
for (const failure of [missing, preCancelled, liveCancelled, wrongOutput]) {
  assert(failure.instance, JSON.stringify(failure));
  assert(failure.workflowId === "async_capability", JSON.stringify(failure));
  assert(failure.blockPath === "/", JSON.stringify(failure));
}
assert(missing.nodePath === "", JSON.stringify(missing));
assert(preCancelled.nodePath === "", JSON.stringify(preCancelled));
// Either concurrently running invocation may observe the shared cancellation first.
assert(["read", "double"].includes(liveCancelled.nodePath), JSON.stringify(liveCancelled));
assert(wrongOutput.nodePath === "read", JSON.stringify(wrongOutput));
assert(missingTrace.length === 0, JSON.stringify(missingTrace));
assert(preTrace.length === 0, JSON.stringify(preTrace));
const liveNodes = liveTrace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodeId);
assert(!liveNodes.includes("end"), JSON.stringify(liveNodes));
process.stdout.write(JSON.stringify({
  missing,
  preCancelled,
  preCalls,
  liveCancelled,
  liveCalls,
  liveSignal,
  wrongOutput,
  recovered,
  liveNodes,
}));
""",
    )


__all__ = [
    "async_capability_case",
    "capability_error_case",
    "capability_isolation_case",
    "import_case",
    "input_error_case",
    "loop_case",
]
