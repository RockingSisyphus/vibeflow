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


def linear_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const result = await workflow.runWorkflow({ x: 10, a: 8, b: 3 });
assert(result.result === 15, `unexpected result: ${JSON.stringify(result)}`);
assert(Object.keys(result).join(",") === "result", "public envelope leaked");
process.stdout.write(JSON.stringify(result));
""",
    )


def optional_input_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const supplied = await workflow.runWorkflow({ x: 10, offset: 7 });
const omitted = await workflow.runWorkflow({ x: 10 });
assert(supplied.result === 17, JSON.stringify(supplied));
assert(omitted.result === 10, JSON.stringify(omitted));
assert(Object.keys(omitted).join(",") === "result", "optional envelope leaked");
process.stdout.write(JSON.stringify({ supplied, omitted }));
""",
    )


def repeat_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const first = await workflow.runWorkflow({ x: 1, a: 2, b: 3 });
const second = await workflow.runWorkflow({ x: 20, a: -5, b: 7 });
assert(first.result === 0, "first invocation was wrong");
assert(second.result === 8, "second invocation was polluted");
process.stdout.write(JSON.stringify({ first, second }));
""",
    )


def concurrent_trace_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const leftTrace = [];
const rightTrace = [];
const [left, right] = await Promise.all([
  workflow.runWorkflow(
    { x: 4, a: 9, b: 2 },
    { trace: "full", onTrace: event => leftTrace.push(event) },
  ),
  workflow.runWorkflow(
    { x: 100, a: 1, b: 80 },
    { trace: "boundary", onTrace: event => rightTrace.push(event) },
  ),
]);
assert(left.result === 11 && right.result === 21, "concurrent outputs differ");
const leftKinds = leftTrace.map(event => event.kind);
const rightKinds = rightTrace.map(event => event.kind);
const leftNodes = leftTrace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodeId);
assert(leftKinds.at(0) === "run_start", JSON.stringify(leftKinds));
assert(leftKinds.at(-1) === "run_end", JSON.stringify(leftKinds));
assert(
  JSON.stringify(leftNodes) === '["start","add","subtract","end"]',
  JSON.stringify(leftNodes),
);
assert(
  JSON.stringify(rightKinds) === '["run_start","run_end"]',
  JSON.stringify(rightKinds),
);
process.stdout.write(JSON.stringify({
  left,
  right,
  leftKinds,
  rightKinds,
}));
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


def fanout_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const result = await workflow.runWorkflow({ x: 10 });
assert(result.added === 11, JSON.stringify(result));
assert(result.subtracted === 9, JSON.stringify(result));
process.stdout.write(JSON.stringify(result));
""",
    )


def branch_case(entry: Path, value: int, expected: str) -> Any:
    return run_node(
        entry,
        f"""
const trace = [];
const result = await workflow.runWorkflow(
  {{ x: {value} }},
  {{ trace: "full", onTrace: event => trace.push(event) }},
);
assert(result.message === {json.dumps(expected)}, JSON.stringify(result));
const nodes = trace
  .filter(event => event.kind === "node_start")
  .map(event => event.nodeId);
const selected = {json.dumps("positive" if value >= 0 else "negative")};
const rejected = {json.dumps("negative" if value >= 0 else "positive")};
assert(nodes.includes(selected), JSON.stringify(nodes));
assert(!nodes.includes(rejected), JSON.stringify(nodes));
process.stdout.write(JSON.stringify({{ result, nodes }}));
""",
    )


def nodeset_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const trace = [];
const result = await workflow.runWorkflow(
  { x: 12, a: 5, b: 4 },
  { trace: "boundary", onTrace: event => trace.push(event) },
);
assert(result.result === 13, JSON.stringify(result));
const kinds = trace.map(event => event.kind);
assert(kinds.includes("nodeset_enter"), JSON.stringify(kinds));
assert(kinds.includes("nodeset_exit"), JSON.stringify(kinds));
process.stdout.write(JSON.stringify({ result, kinds }));
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


def loop_stop_when_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const trace = [];
const result = await workflow.runWorkflow(
  { x: 1 },
  { trace: "full", onTrace: event => trace.push(event) },
);
const iterations = trace.filter(event => event.kind === "loop_iteration");
assert(result.result === 4, JSON.stringify(result));
assert(JSON.stringify(result.history) === "[2,3,4]", JSON.stringify(result));
assert(result.iterations === 3, JSON.stringify(result));
assert(iterations.length === 3, JSON.stringify(iterations));
process.stdout.write(JSON.stringify({
  result,
  iterations: iterations.map(event => event.iteration),
}));
""",
    )


def async_capability_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const calls = [];
const result = await workflow.runWorkflowAsync(
  { x: 6, key: "alpha" },
  {
    capabilities: {
      "sandbox.storage": {
        read: async request => {
          calls.push(request);
          return { value: `stored:${request.key}` };
        },
      },
    },
  },
);
assert(result.doubled === 12, JSON.stringify(result));
assert(result.value === "stored:alpha", JSON.stringify(result));
assert(calls.length === 1 && calls[0].key === "alpha", JSON.stringify(calls));
process.stdout.write(JSON.stringify({ result, calls }));
""",
    )


def port_math_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const received = [];
const sent = [];
const result = await workflow.runWorkflowAsync({}, {
  capabilities: {
    "vibeflow.port": {
      async receive(request) {
        received.push(request);
        return { value: 5 };
      },
      send(request) {
        sent.push(request);
        return null;
      },
    },
  },
});
assert(result.result === 17, JSON.stringify(result));
assert(
  JSON.stringify(received) === '[{"port":"sandbox.math.in"}]',
  JSON.stringify(received),
);
assert(
  JSON.stringify(sent) ===
    '[{"port":"sandbox.math.out","value":17}]',
  JSON.stringify(sent),
);
process.stdout.write(JSON.stringify({ result, received, sent }));
""",
    )


def capability_isolation_case(entry: Path) -> Any:
    return run_node(
        entry,
        """
const makeOptions = prefix => ({
  capabilities: {
    "sandbox.storage": {
      read: async request => ({ value: `${prefix}:${request.key}` }),
    },
  },
});
const [left, right] = await Promise.all([
  workflow.runWorkflowAsync({ x: 2, key: "same" }, makeOptions("left")),
  workflow.runWorkflowAsync({ x: 9, key: "same" }, makeOptions("right")),
]);
assert(left.value === "left:same", JSON.stringify(left));
assert(right.value === "right:same", JSON.stringify(right));
assert(left.doubled === 4 && right.doubled === 18, "async state leaked");
process.stdout.write(JSON.stringify({ left, right }));
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
            liveSignal = context.signal === live.signal;
            queueMicrotask(() => live.abort(new Error("cancel in flight")));
            return new Promise(() => {});
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
assert(liveCancelled.nodePath === "read", JSON.stringify(liveCancelled));
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
    "branch_case",
    "capability_error_case",
    "capability_isolation_case",
    "concurrent_trace_case",
    "fanout_case",
    "import_case",
    "input_error_case",
    "linear_case",
    "loop_case",
    "loop_stop_when_case",
    "nodeset_case",
    "optional_input_case",
    "repeat_case",
]
