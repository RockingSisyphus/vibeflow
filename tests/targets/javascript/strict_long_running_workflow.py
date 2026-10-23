from __future__ import annotations
import asyncio

def _execute(runtime,*args,**kwargs):
    return asyncio.run(runtime.run_async(*args,**kwargs)) if runtime.graph.entry_mode == 'async' else runtime.run(*args,**kwargs)

from tests.fixtures.support.declarations import configured_declaration, native_registry

import json
from pathlib import Path
import subprocess

from tests.targets.javascript.aot_fixtures import emit_fixture
from vibeflow.targets.python.project.compiler import GraphCompiler
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime import PipelineRuntime


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
        "abi_version": 'vibeflow.workflow.v11',
        "workflow_id": "test.host-lifecycle",
        "entry_mode": "sync",
        "inputs": [],
        "outputs": [],
        "schemas": {},
        "capabilities": [],
        "nodes": [
            {
                "id": "run",
                "definition_id": "test.noop",
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


_DoubleNode_DECLARATION = NodeDescriptor(
    "test.double", "Double", "Doubles a number.", "1", "process",
    contract=NodeContractDescriptor(
        requires=(DataRequirement("number", "exactly_one", display_name="number"),),
        provides=(DataProvider("answer", "answer", display_name="answer"),),
        input_semantics={"number": ("number to double",)},
        output_semantics={"answer": ("doubled number",)},
    ),
    rulesets=("vibeflow.process",),
 node_type="vibeflow.node")

class _DoubleNode:

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
                    {"id":"start", "definition_id":"fixture.port.boundary", "display_name":"Start", "description":"Enter port workflow"},
                    {"id":"end", "definition_id":"fixture.port.boundary", "display_name":"End", "description":"Finish port workflow"},
                    {
                        "id": "receive",
                        "definition_id": "fixture.port.receive",
                        "display_name": "Receive number",
                        "description": "Receives the input number from the math input port.",
                        "config": {"port": "math.in"},
                    },
                    {
                        "id": "double",
                        "definition_id": "test.double",
                        "display_name": "Double number",
                        "description": "Doubles the received number for this workflow.",
                    },
                    {
                        "id": "send",
                        "definition_id": "fixture.port.send",
                        "display_name": "Send answer",
                        "description": "Sends the doubled answer through the math output port.",
                        "config": {"port": "math.out"},
                    },
                ],
                "edges": [["start", "receive"], ["send", "end"],
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
    registry = native_registry()
    from tests.fixtures.support.port_nodes import register_ports
    register_ports(registry)
    registry.register(configured_declaration(_DoubleNode_DECLARATION, {}, {}), _DoubleNode)
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

    result = _execute(runtime)

    assert result.get("answer")["value"] == 12
    assert sent == [{"port": "math.out", "value": 12}]
    assert GraphCompiler().compile(graph, registry=registry).flow_kinds == {
        "start": "terminal",
        "end": "terminal",
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
export function boundary(){return {};}
export async function receive(inputs,params,context){const value=await context.capabilities["vibeflow.port"].receive({port:params.port});return {number:value.value};}
export function send(inputs,params,context){context.capabilities["vibeflow.port"].send({port:params.port,value:inputs.answer.value});return {};}
export function double(inputs) {
  return { answer: inputs.number.value * 2 };
}
""",
        encoding="utf-8",
    )
    plan = {
        "abi_version": 'vibeflow.workflow.v11',
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
                "definition_id": "test.receive",
                "implementation": {"ref":str(node_module),"export":"receive"},
                "params":{"port":"math.in"},
                "requires": [],
                "provides": [{"key": "number", "type": "number"}],
                "flow_kind": "io",
                "is_terminal": False,
                "completion": "suspend",
                "executor": "event_loop",
                "capabilities": [
                    {
                        "id": "vibeflow.port",
                        "operations": ["receive"],
                    }
                ],
            },
            {
                "id": "double",
                "definition_id": "test.double",
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
                "definition_id": "test.send",
                "implementation": {"ref":str(node_module),"export":"send"},
                "params":{"port":"math.out"},
                "requires": [{"type": "answer", "cardinality": "exactly_one"}],
                "provides": [],
                "flow_kind": "io",
                "is_terminal": False,
                "completion": "immediate",
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
    plan["nodes"].extend([
        {"id":identifier,"definition_id":"test.boundary","is_terminal":True,"flow_kind":"terminal",
         "implementation":{"ref":str(node_module),"export":"boundary"}} for identifier in ("start","end")])
    plan["routes"].extend([{"source":"start","target":"receive"},{"source":"send","target":"end"}])
    plan["order"] = ["start","receive","double","send","end"]
    emitted = emit_fixture(plan)
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
