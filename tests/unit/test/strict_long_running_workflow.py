from __future__ import annotations

import json
from pathlib import Path
import subprocess

from vibeflow.aot import emit_workflow_module
from vibeflow.compiler import GraphCompiler
from vibeflow.data_contract import DataProvider, DataRequirement
from vibeflow.graph_config import parse_graph_config
from vibeflow.node import NodeContract, NodeInfo
from vibeflow.registry import NodeRegistry
from vibeflow.runtime import PipelineRuntime


def _provider(key: str, type_key: str) -> dict[str, str]:
    return {
        "key": key,
        "type": type_key,
        "display_name": key,
    }


def _requirement(type_key: str) -> dict[str, str]:
    return {
        "type": type_key,
        "cardinality": "exactly_one",
        "display_name": type_key,
    }


def _run_module(path: Path, body: str) -> dict[str, object]:
    script = f"""
import {{ pathToFileURL }} from "node:url";
globalThis.__calls = [];
const workflow = await import(pathToFileURL({json.dumps(str(path))}).href);
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


def _empty_sync_plan(node_module: Path) -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.host-lifecycle",
        "entry_mode": "sync",
        "inputs": [],
        "outputs": [],
        "schemas": {},
        "capabilities": [],
        "nodes": [
            {
                "id": "run",
                "type_used": "test.noop",
                "implementation": {
                    "ref": str(node_module),
                    "export": "run",
                    "completion": "immediate",
                },
                "requires": [],
                "provides": [],
                "flow_kind": "terminal",
                "is_terminal": True,
            }
        ],
        "routes": [],
        "order": ["run"],
        "max_steps": 5,
    }


class _DoubleNode:
    NODE_INFO = NodeInfo(
        "test.double",
        "Double",
        "test",
        "Doubles a number.",
        "1",
        "process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("number", "exactly_one"),),
        provides=(DataProvider("answer", "answer"),),
    )

    def run_pure(self, inputs, params):
        del params
        return {"answer": inputs["number"]["value"] * 2}


def test_python_port_nodes_receive_transform_and_send(
    tmp_path: Path,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "entry_mode": "async",
                "nodes": [
                    {
                        "id": "receive",
                        "type_used": "vibeflow.io",
                        "provides": [_provider("number", "number")],
                        "io": {
                            "operation": "receive",
                            "port": "math.in",
                        },
                    },
                    {
                        "id": "double",
                        "type_used": "test.double",
                        "requires": [_requirement("number")],
                        "provides": [_provider("answer", "answer")],
                    },
                    {
                        "id": "send",
                        "type_used": "vibeflow.io",
                        "requires": [_requirement("answer")],
                        "io": {
                            "operation": "send",
                            "port": "math.out",
                        },
                    },
                ],
                "edges": [
                    ["receive", "double"],
                    ["double", "send"],
                ],
                "outputs": [
                    {
                        "type": "answer",
                        "cardinality": "exactly_one",
                        "display_name": "answer",
                    }
                ],
            }
        }
    )
    registry = NodeRegistry()
    registry.register(
        "test.double",
        _DoubleNode,
        config_schema={},
        config_defaults={},
    )
    sent: list[dict[str, object]] = []
    runtime = PipelineRuntime(
        graph,
        registry=registry,
        run_dir=tmp_path / "runs",
        capabilities={
            "vibeflow.port": {
                "receive": lambda request: {
                    "value": 6 if request["port"] == "math.in" else 0
                },
                "send": lambda request: sent.append(dict(request)),
            }
        },
    )

    result = runtime.run()

    assert result.get("answer")["value"] == 12
    assert sent == [{"port": "math.out", "value": 12}]
    assert GraphCompiler().compile(graph, registry=registry).flow_kinds == {
        "receive": "io",
        "double": "process",
        "send": "io",
    }


def test_javascript_async_port_workflow_is_explicit_and_auditable(
    tmp_path: Path,
) -> None:
    node_module = tmp_path / "nodes.mjs"
    node_module.write_text(
        """
export function double(inputs) {
  return { answer: inputs.number.value * 2 };
}
""",
        encoding="utf-8",
    )
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.port",
        "entry_mode": "async",
        "inputs": [],
        "outputs": [
            {
                "type": "answer",
                "cardinality": "exactly_one",
                "as": "answer",
            }
        ],
        "schemas": {
            "number": {"type": "number"},
            "answer": {"type": "number"},
            "vibeflow.port.receive.request": {
                "type": "object",
                "required": ["port"],
                "properties": {"port": {"type": "string"}},
                "additionalProperties": False,
            },
            "vibeflow.port.receive.result": {
                "type": "object",
                "required": ["value"],
                "properties": {"value": {}},
                "additionalProperties": False,
            },
            "vibeflow.port.send.request": {
                "type": "object",
                "required": ["port", "value"],
                "properties": {
                    "port": {"type": "string"},
                    "value": {},
                },
                "additionalProperties": False,
            },
            "vibeflow.port.send.result": {"type": "null"},
        },
        "capabilities": [
            {
                "id": "vibeflow.port",
                "operations": {
                    "receive": {
                        "input_type": "vibeflow.port.receive.request",
                        "output_type": "vibeflow.port.receive.result",
                        "completion": "suspend",
                    },
                    "send": {
                        "input_type": "vibeflow.port.send.request",
                        "output_type": "vibeflow.port.send.result",
                        "completion": "immediate",
                    },
                },
            }
        ],
        "nodes": [
            {
                "id": "receive",
                "type_used": "vibeflow.io",
                "implementation": None,
                "requires": [],
                "provides": [{"key": "number", "type": "number"}],
                "flow_kind": "io",
                "is_terminal": True,
                "completion": "suspend",
                "executor": "event_loop",
                "io_operation": "receive",
                "io_port": "math.in",
                "capabilities": [
                    {
                        "id": "vibeflow.port",
                        "operations": ["receive"],
                    }
                ],
            },
            {
                "id": "double",
                "type_used": "test.double",
                "implementation": {
                    "ref": str(node_module),
                    "export": "double",
                    "completion": "immediate",
                },
                "requires": [{"type": "number", "cardinality": "exactly_one"}],
                "provides": [{"key": "answer", "type": "answer"}],
                "flow_kind": "process",
            },
            {
                "id": "send",
                "type_used": "vibeflow.io",
                "implementation": None,
                "requires": [{"type": "answer", "cardinality": "exactly_one"}],
                "provides": [],
                "flow_kind": "io",
                "is_terminal": True,
                "completion": "immediate",
                "io_operation": "send",
                "io_port": "math.out",
                "capabilities": [
                    {
                        "id": "vibeflow.port",
                        "operations": ["send"],
                    }
                ],
            },
        ],
        "routes": [
            {"source": "receive", "target": "double"},
            {"source": "double", "target": "send"},
        ],
        "order": ["receive", "double", "send"],
        "max_steps": 10,
    }
    emitted = emit_workflow_module(plan)
    workflow = tmp_path / "workflow.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")

    result = _run_module(
        workflow,
        """
let sent = null;
const answer = await workflow.runWorkflowAsync({}, {
  capabilities: {
    "vibeflow.port": {
      async receive(request) {
        return { value: request.port === "math.in" ? 9 : 0 };
      },
      send(request) {
        sent = request;
        return null;
      },
    },
  },
});
console.log(JSON.stringify({
  answer,
  sent,
  hasSync: "runWorkflow" in workflow,
  hasAsync: "runWorkflowAsync" in workflow,
}));
""",
    )

    assert result == {
        "answer": {"answer": 18},
        "sent": {"port": "math.out", "value": 18},
        "hasSync": False,
        "hasAsync": True,
    }


def test_host_extension_lifecycle_is_explicit_and_reverse_ordered(
    tmp_path: Path,
) -> None:
    node_module = tmp_path / "node.mjs"
    extension_a = tmp_path / "extension-a.mjs"
    extension_b = tmp_path / "extension-b.mjs"
    node_module.write_text(
        """
export function useCapability(inputs, _params, context) {
  return {
    answer: context.capabilities["test.math"].double(inputs.number.value),
  };
}
""",
        encoding="utf-8",
    )
    extension_a.write_text(
        """
export function createHostExtension(context) {
  globalThis.__calls.push("create:a");
  globalThis.__calls.push(`config:a:${context.config.label}`);
  return {
    capabilities: {
      "test.math": { double(value) { return value * 2; } },
    },
    start() { globalThis.__calls.push("start:a"); },
    stop() { globalThis.__calls.push("stop:a"); },
  };
}
""",
        encoding="utf-8",
    )
    extension_b.write_text(
        """
export function createHostExtension() {
  globalThis.__calls.push("create:b");
  return {
    start() { globalThis.__calls.push("start:b"); },
    stop() { globalThis.__calls.push("stop:b"); },
  };
}
""",
        encoding="utf-8",
    )
    plan = {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.host",
        "entry_mode": "sync",
        "inputs": [
            {
                "key": "number",
                "type": "number",
                "required": True,
                "schema": {"type": "number"},
            }
        ],
        "outputs": [
            {
                "type": "answer",
                "cardinality": "exactly_one",
                "as": "answer",
                "schema": {"type": "number"},
            }
        ],
        "schemas": {
            "number": {"type": "number"},
            "answer": {"type": "number"},
        },
        "capabilities": [
            {
                "id": "test.math",
                "operations": {
                    "double": {
                        "input_type": "number",
                        "output_type": "answer",
                        "completion": "immediate",
                    }
                },
            }
        ],
        "nodes": [
            {
                "id": "run",
                "type_used": "test.use-capability",
                "implementation": {
                    "ref": str(node_module),
                    "export": "useCapability",
                    "completion": "immediate",
                },
                "requires": [{"type": "number", "cardinality": "exactly_one"}],
                "provides": [{"key": "answer", "type": "answer"}],
                "flow_kind": "terminal",
                "is_terminal": True,
                "capabilities": [
                    {"id": "test.math", "operations": ["double"]}
                ],
            }
        ],
        "routes": [],
        "order": ["run"],
        "max_steps": 5,
    }
    emitted = emit_workflow_module(
        plan,
        host_extensions=(
            {
                "id": "test.a",
                "module": str(extension_a),
                "export": "createHostExtension",
                "provides": ["test.math"],
                "dependencies": [],
                "config": {"label": "primary"},
            },
            {
                "id": "test.b",
                "module": str(extension_b),
                "export": "createHostExtension",
                "provides": [],
                "dependencies": ["test.a"],
            },
        ),
    )
    workflow = tmp_path / "host-workflow.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")

    result = _run_module(
        workflow,
        """
const afterImport = [...globalThis.__calls];
const host = workflow.createWorkflowHost();
const afterCreate = [...globalThis.__calls];
await host.start();
const answer = host.runWorkflow({ number: 7 });
await host.stop();
await host.stop();
console.log(JSON.stringify({
  afterImport,
  afterCreate,
  answer,
  calls: globalThis.__calls,
  started: host.started,
}));
""",
    )

    assert result == {
        "afterImport": [],
        "afterCreate": ["create:a", "config:a:primary", "create:b"],
        "answer": {"answer": 14},
        "calls": [
            "create:a",
            "config:a:primary",
            "create:b",
            "start:a",
            "start:b",
            "stop:b",
            "stop:a",
        ],
        "started": False,
    }


def test_async_host_extension_invocation_is_awaitable(
    tmp_path: Path,
) -> None:
    node_module = tmp_path / "node.mjs"
    extension = tmp_path / "extension.mjs"
    node_module.write_text(
        "export function run() { return {}; }\n",
        encoding="utf-8",
    )
    extension.write_text(
        """
export function createHostExtension() {
  return { start() {}, stop() {} };
}
""",
        encoding="utf-8",
    )
    plan = _empty_sync_plan(node_module)
    plan["entry_mode"] = "async"
    emitted = emit_workflow_module(
        plan,
        host_extensions=(
            {
                "id": "test.async",
                "module": str(extension),
                "export": "createHostExtension",
                "provides": [],
                "dependencies": [],
            },
        ),
    )
    assert "async function invoke(inputs, rawOptions = {})" in emitted.source
    workflow = tmp_path / "async-host-workflow.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")

    result = _run_module(
        workflow,
        """
const host = workflow.createWorkflowHost();
const rejectedBeforeStart = host.runWorkflowAsync({});
let beforeStartCode = null;
try {
  await rejectedBeforeStart;
} catch (error) {
  beforeStartCode = error.code;
}
await host.start();
const invocation = host.runWorkflowAsync({});
const answer = await invocation;
await host.stop();
console.log(JSON.stringify({
  beforeStartWasPromise: rejectedBeforeStart instanceof Promise,
  beforeStartCode,
  invocationWasPromise: invocation instanceof Promise,
  answer,
  hasSync: "runWorkflow" in host,
  hasAsync: "runWorkflowAsync" in host,
}));
""",
    )

    assert result == {
        "beforeStartWasPromise": True,
        "beforeStartCode": "VF_HOST_NOT_STARTED",
        "invocationWasPromise": True,
        "answer": {},
        "hasSync": False,
        "hasAsync": True,
    }


def test_host_extension_instances_are_isolated(tmp_path: Path) -> None:
    node_module = tmp_path / "node.mjs"
    extension = tmp_path / "extension.mjs"
    node_module.write_text(
        "export function run() { return {}; }\n",
        encoding="utf-8",
    )
    extension.write_text(
        """
export function createHostExtension(context) {
  const id = (globalThis.__nextHostId = (globalThis.__nextHostId || 0) + 1);
  globalThis.__configs = globalThis.__configs || [];
  globalThis.__configs.push(context.config);
  globalThis.__calls.push(`create:${id}`);
  globalThis.__calls.push(
    `config:${id}:${Object.isFrozen(context.config)}:${Object.isFrozen(context.config.nested)}`
  );
  try {
    context.config.nested.count += 1;
  } catch {
    globalThis.__calls.push(`mutation-blocked:${id}`);
  }
  return {
    start() { globalThis.__calls.push(`start:${id}`); },
    stop() { globalThis.__calls.push(`stop:${id}`); },
  };
}
""",
        encoding="utf-8",
    )
    emitted = emit_workflow_module(
        _empty_sync_plan(node_module),
        host_extensions=(
            {
                "id": "test.isolated",
                "module": str(extension),
                "export": "createHostExtension",
                "provides": [],
                "dependencies": [],
                "config": {"nested": {"count": 1}},
            },
        ),
    )
    workflow = tmp_path / "isolated-hosts.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")

    result = _run_module(
        workflow,
        """
const first = workflow.createWorkflowHost();
const second = workflow.createWorkflowHost();
await first.start();
await second.start();
await first.stop();
await second.stop();
console.log(JSON.stringify({
  calls: globalThis.__calls,
  separateTopLevel: globalThis.__configs[0] !== globalThis.__configs[1],
  separateNested: (
    globalThis.__configs[0].nested !== globalThis.__configs[1].nested
  ),
  counts: globalThis.__configs.map((config) => config.nested.count),
}));
""",
    )

    assert result == {
        "calls": [
            "create:1",
            "config:1:true:true",
            "mutation-blocked:1",
            "create:2",
            "config:2:true:true",
            "mutation-blocked:2",
            "start:1",
            "start:2",
            "stop:1",
            "stop:2",
        ],
        "separateTopLevel": True,
        "separateNested": True,
        "counts": [1, 1],
    }


def test_host_extension_partial_start_failure_cleans_started_extensions(
    tmp_path: Path,
) -> None:
    node_module = tmp_path / "node.mjs"
    extension_a = tmp_path / "extension-a.mjs"
    extension_b = tmp_path / "extension-b.mjs"
    node_module.write_text(
        "export function run() { return {}; }\n",
        encoding="utf-8",
    )
    extension_a.write_text(
        """
export function createHostExtension() {
  return {
    start() { globalThis.__calls.push("start:a"); },
    stop() { globalThis.__calls.push("stop:a"); },
  };
}
""",
        encoding="utf-8",
    )
    extension_b.write_text(
        """
export function createHostExtension() {
  return {
    start() {
      globalThis.__calls.push("start:b");
      throw new Error("start failed");
    },
    stop() { globalThis.__calls.push("stop:b"); },
  };
}
""",
        encoding="utf-8",
    )
    emitted = emit_workflow_module(
        _empty_sync_plan(node_module),
        host_extensions=(
            {
                "id": "test.a",
                "module": str(extension_a),
                "export": "createHostExtension",
                "provides": [],
                "dependencies": [],
            },
            {
                "id": "test.b",
                "module": str(extension_b),
                "export": "createHostExtension",
                "provides": [],
                "dependencies": ["test.a"],
            },
        ),
    )
    workflow = tmp_path / "failed-host.mjs"
    workflow.write_text(emitted.source, encoding="utf-8")

    result = _run_module(
        workflow,
        """
const host = workflow.createWorkflowHost();
let code = null;
try {
  await host.start();
} catch (error) {
  code = error.code;
}
console.log(JSON.stringify({
  code,
  calls: globalThis.__calls,
  started: host.started,
  aborted: host.signal.aborted,
}));
""",
    )

    assert result == {
        "code": "VF_HOST_EXTENSION_START",
        "calls": ["start:a", "start:b", "stop:a"],
        "started": False,
        "aborted": True,
    }
