"""Cross-runtime conformance support built around VibeFlow's portable plan.

The Python runtime supplies the reference observation. A conformance case is
compiled once through its real ``ExecutionPlan`` adapter, then that
portable plan is emitted and executed as JavaScript.  The observations below
intentionally compare the public contract and stable trace facts instead of
runtime-private event payloads.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.core.contracts import (
    CARDINALITY_ALL,
    DataEnvelope,
    RunResult,
)
from vibeflow.core import GraphConfig
from vibeflow.block_compiler import SourceRef
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
from vibeflow.tooling.project.graph_config import parse_graph_config


@dataclass(frozen=True)
class PortableConformanceCase:
    name: str
    document: Mapping[str, Any]
    inputs: Mapping[str, Any]
    registry: NodeRegistry
    javascript_source: str
    javascript_exports: Mapping[str, str]
    port_inputs: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorObservation:
    category: str
    node_path: str
    message: str


@dataclass(frozen=True)
class RuntimeObservation:
    public_outputs: Mapping[str, Any]
    node_runs: tuple[tuple[str, int], ...]
    edge_runs: tuple[tuple[str, int], ...]
    task_events: tuple[tuple[str, str], ...]
    port_sends: tuple[Mapping[str, Any], ...]
    error: ErrorObservation | None


@dataclass(frozen=True)
class PortableConformanceResult:
    portable_plan: Mapping[str, Any]
    python: RuntimeObservation
    javascript: RuntimeObservation

    def assert_equivalent(self) -> None:
        assert self.python.public_outputs == self.javascript.public_outputs
        assert self.python.node_runs == self.javascript.node_runs
        assert self.python.edge_runs == self.javascript.edge_runs
        assert self.python.task_events == self.javascript.task_events
        assert self.python.port_sends == self.javascript.port_sends
        assert self.python.error == self.javascript.error


def run_portable_conformance(
    case: PortableConformanceCase,
    *,
    work_dir: Path,
) -> PortableConformanceResult:
    """Run one real graph through Python and emitted JavaScript."""

    graph = parse_graph_config(case.document)
    python_port_queues = {
        str(port): list(values)
        for port, values in case.port_inputs.items()
    }
    python_port_sends: list[dict[str, Any]] = []
    runtime = PipelineRuntime(
        graph,
        registry=case.registry,
        run_dir=work_dir / "python-run",
        runtime_options=RuntimeOptions(trace="full"),
        capabilities=(
            _python_port_capabilities(
                python_port_queues,
                python_port_sends,
            )
            if case.port_inputs
            else None
        ),
    )
    sources = {
        type_key: SourceRef(
            kind="javascript",
            ref="./nodes.mjs",
            export=export_name,
        )
        for type_key, export_name in case.javascript_exports.items()
    }
    portable_plan = runtime._plan.to_workflow_plan(
        workflow_id=case.name,
        source_by_type=sources,
    )

    python_observation = _run_python(
        runtime,
        graph,
        case.inputs,
        port_sends=python_port_sends,
    )
    javascript_observation = _run_javascript(
        portable_plan,
        case.javascript_source,
        case.inputs,
        port_inputs=case.port_inputs,
        work_dir=work_dir / "javascript-run",
    )
    return PortableConformanceResult(
        portable_plan=portable_plan.to_dict(),
        python=python_observation,
        javascript=javascript_observation,
    )


def _run_python(
    runtime: PipelineRuntime,
    graph: GraphConfig,
    inputs: Mapping[str, Any],
    *,
    port_sends: list[dict[str, Any]],
) -> RuntimeObservation:
    result: RunResult | None = None
    error: ErrorObservation | None = None
    try:
        result = runtime.run(inputs)
    except Exception as exc:  # noqa: BLE001 - the observation is the test result
        category = _python_error_category(exc)
        error = _normalized_error(
            category,
            runtime.trace.current_node,
            _root_message(exc),
        )
    return RuntimeObservation(
        public_outputs=_python_public_outputs(graph, result),
        node_runs=_counter_items(runtime.trace.qualified_node_runs),
        edge_runs=_counter_items(runtime.trace.qualified_edge_executions),
        task_events=_python_task_events(runtime.trace.trace_path),
        port_sends=tuple(dict(item) for item in port_sends),
        error=error,
    )


def _run_javascript(
    portable_plan: object,
    node_source: str,
    inputs: Mapping[str, Any],
    *,
    port_inputs: Mapping[str, tuple[Any, ...]],
    work_dir: Path,
) -> RuntimeObservation:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "nodes.mjs").write_text(node_source, encoding="utf-8")
    emission_plan = (
        _javascript_plan_with_port_bindings(portable_plan)
        if port_inputs
        else portable_plan
    )
    emitted = emit_workflow_module(emission_plan)
    workflow_path = work_dir / "workflow.mjs"
    workflow_path.write_text(emitted.source, encoding="utf-8")
    entry_name = (
        "runWorkflowAsync"
        if getattr(portable_plan, "entry_mode", "sync") == "async"
        else "runWorkflow"
    )

    script = f"""
import {{ pathToFileURL }} from "node:url";
const workflow = await import(pathToFileURL({json.dumps(str(workflow_path))}).href);
const trace = [];
const portQueues = Object.fromEntries(
  Object.entries({json.dumps({str(port): list(values) for port, values in port_inputs.items()}, ensure_ascii=False)})
    .map(([port, values]) => [port, [...values]]),
);
const portSends = [];
let publicOutputs = {{}};
let error = null;
try {{
  const options = {{ trace: "full", onTrace: event => trace.push(event) }};
  if (Object.keys(portQueues).length) {{
    options.capabilities = {{
      "vibeflow.port": {{
        async receive(request) {{
          const queue = portQueues[String(request.port)];
          if (!queue?.length) throw new Error(`port '${{request.port}}' has no queued input`);
          return {{ value: queue.shift() }};
        }},
        send(request) {{
          portSends.push({{ port: String(request.port), value: request.value }});
          return null;
        }},
      }},
    }};
  }}
  publicOutputs = await workflow.{entry_name}(
    {json.dumps(dict(inputs), ensure_ascii=False)},
    options,
  );
}} catch (cause) {{
  error = {{
    category: errorCategory(cause?.code),
    node_path: String(cause?.nodePath || ""),
    message: String(cause?.cause?.message || cause?.message || cause),
  }};
}}
const nodeRuns = Object.create(null);
const edgeRuns = Object.create(null);
const taskEventKeys = new Set();
const taskKinds = new Set([
  "async_result",
  "async_result_join",
  "async_result_abandoned",
  "async_detached",
  "async_detached_done",
  "async_detached_failed",
  "async_detached_timeout",
]);
for (const event of trace) {{
  if (
    event.kind === "node_end"
    || event.kind === "async_result"
    || event.kind === "async_detached"
  ) {{
    const key = String(event.nodePath || event.nodeId || "");
    nodeRuns[key] = (nodeRuns[key] || 0) + 1;
  }}
  if (event.kind === "edge_activated") {{
    const prefix = Array.isArray(event.path) && event.path.length
      ? `${{event.path.join(".")}}.`
      : "";
    const key = `${{prefix}}${{event.source}}->${{prefix}}${{event.target}}`;
    edgeRuns[key] = (edgeRuns[key] || 0) + 1;
  }}
  if (taskKinds.has(event.kind)) {{
    taskEventKeys.add(JSON.stringify([
      String(event.kind),
      String(event.nodePath || event.nodeId || ""),
    ]));
  }}
}}
process.stdout.write(JSON.stringify({{
  public_outputs: publicOutputs,
  node_runs: nodeRuns,
  edge_runs: edgeRuns,
  task_events: [...taskEventKeys].map(value => JSON.parse(value)).sort(),
  port_sends: portSends,
  error,
}}));

function errorCategory(code) {{
  if (code === "VF_INPUT_REQUIRED") return "input_required";
  if (code === "VF_INPUT_UNKNOWN") return "input_unknown";
  if (code === "VF_NODE_FAILED" || code === "VF_CAPABILITY_FAILED") return "node_failed";
  if (code === "VF_OUTPUT_CARDINALITY") return "output_cardinality";
  if (code === "VF_MAX_STEPS") return "max_steps";
  if (code === "VF_ABORTED") return "cancelled";
  return String(code || "javascript_error").toLowerCase();
}}
"""
    completed = subprocess.run(
        ["node", "--input-type=module", "--eval", script],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    raw_error = payload.get("error")
    error = (
        _normalized_error(
            str(raw_error["category"]),
            str(raw_error["node_path"]),
            str(raw_error["message"]),
        )
        if isinstance(raw_error, Mapping)
        else None
    )
    return RuntimeObservation(
        public_outputs=dict(payload["public_outputs"]),
        node_runs=_counter_items(payload["node_runs"]),
        edge_runs=_counter_items(payload["edge_runs"]),
        task_events=_task_event_items(payload["task_events"]),
        port_sends=tuple(dict(item) for item in payload["port_sends"]),
        error=error,
    )


def _python_port_capabilities(
    queues: dict[str, list[Any]],
    sends: list[dict[str, Any]],
) -> dict[str, object]:
    def receive(request: Mapping[str, Any]) -> dict[str, Any]:
        port = str(request["port"])
        queue = queues.get(port)
        if not queue:
            raise RuntimeError(f"port '{port}' has no queued input")
        return {"value": queue.pop(0)}

    def send(request: Mapping[str, Any]) -> None:
        sends.append(
            {
                "port": str(request["port"]),
                "value": request["value"],
            }
        )

    return {
        "vibeflow.port": {
            "receive": receive,
            "send": send,
        }
    }


def _javascript_plan_with_port_bindings(portable_plan: object) -> dict[str, Any]:
    """Attach target binding facts absent from the language-neutral IR.

    ``WorkflowPlan`` intentionally describes IO nodes without embedding a JS
    Capability catalog.  The real project builder supplies that catalog from
    descriptors; this test adapter does the same without changing the
    canonical portable plan returned to assertions.
    """

    to_dict = getattr(portable_plan, "to_dict", None)
    if not callable(to_dict):
        raise TypeError("portable conformance plan must support to_dict()")
    payload = json.loads(json.dumps(to_dict(), ensure_ascii=False))
    operations: dict[str, dict[str, str]] = {}
    blocks = payload.get("blocks", [])
    for block in blocks:
        for node in block.get("nodes", []):
            if node.get("type_used") != "vibeflow.io":
                continue
            operation = str(node.get("io_operation", ""))
            node["implementation"] = None
            completion = "suspend" if operation == "receive" else "immediate"
            operations[operation] = {
                "input_type": f"vibeflow.port.{operation}.request",
                "output_type": f"vibeflow.port.{operation}.result",
                "completion": completion,
            }
            node["capabilities"] = [
                {
                    "id": "vibeflow.port",
                    "operations": [operation],
                }
            ]
    payload["capabilities"] = [
        {
            "id": "vibeflow.port",
            "operations": operations,
        }
    ]
    return payload


_TASK_EVENT_KINDS = frozenset(
    {
        "async_result",
        "async_result_join",
        "async_result_abandoned",
        "async_detached",
        "async_detached_done",
        "async_detached_failed",
        "async_detached_timeout",
    }
)


def _python_task_events(trace_path: str) -> tuple[tuple[str, str], ...]:
    path = Path(trace_path)
    if not path.is_file():
        return ()
    events: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = json.loads(line)
        kind = str(raw.get("kind", ""))
        if kind not in _TASK_EVENT_KINDS:
            continue
        events.append(
            (
                kind,
                str(raw.get("qualified_node", raw.get("node", ""))),
            )
        )
    return tuple(sorted(set(events)))


def _task_event_items(values: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(values, list):
        raise TypeError("task_events observation must be a list")
    return tuple(
        sorted(
            {
                (str(item[0]), str(item[1]))
                for item in values
                if isinstance(item, list) and len(item) == 2
            }
        )
    )


def _python_public_outputs(
    graph: GraphConfig,
    result: RunResult | None,
) -> dict[str, Any]:
    if result is None:
        return {}
    outputs: dict[str, Any] = {}
    for spec in graph.outputs:
        if not result.exists(spec.public_name):
            continue
        value = result.get(spec.public_name)
        if spec.cardinality == CARDINALITY_ALL:
            outputs[spec.public_name] = [_business_value(item) for item in value]
        else:
            outputs[spec.public_name] = _business_value(value)
    return outputs


def _business_value(value: Any) -> Any:
    if isinstance(value, DataEnvelope):
        return value.value
    if isinstance(value, Mapping) and {
        "key",
        "type",
        "value",
        "source_node",
    } <= set(value):
        return value["value"]
    return value


def _python_error_category(exc: Exception) -> str:
    message = str(exc)
    if "required workflow input" in message and "is missing" in message:
        return "input_required"
    if "unknown workflow input" in message:
        return "input_unknown"
    if "pipeline output type" in message and "expected" in message:
        return "output_cardinality"
    if "exceeded max_steps" in message:
        return "max_steps"
    return "node_failed"


def _root_message(exc: BaseException) -> str:
    current: BaseException = exc
    seen: set[int] = set()
    while current.__cause__ is not None and id(current) not in seen:
        seen.add(id(current))
        current = current.__cause__
    return str(current).removeprefix("Pipeline runtime error: ")


def _normalized_error(
    category: str,
    node_path: str,
    message: str,
) -> ErrorObservation:
    if category == "output_cardinality":
        node_path = ""
        message = re.sub(
            r"^(?:pipeline|workflow) output",
            "output",
            message,
        )
    return ErrorObservation(
        category=category,
        node_path=node_path,
        message=message,
    )


def _counter_items(values: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    counter = Counter({str(key): int(value) for key, value in values.items()})
    return tuple(sorted(counter.items()))


__all__ = [
    "ErrorObservation",
    "PortableConformanceCase",
    "PortableConformanceResult",
    "RuntimeObservation",
    "run_portable_conformance",
]
