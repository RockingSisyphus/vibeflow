"""Cross-runtime conformance support built around VibeFlow's portable plan.

The Python runtime remains the compatibility implementation.  A conformance
case is compiled once through its real ``ExecutionPlan`` adapter, then that
portable plan is emitted and executed as JavaScript.  The observations below
intentionally compare the public contract and stable trace facts instead of
runtime-private event payloads.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from vibeflow.aot import emit_workflow_module
from vibeflow.data_contract import (
    CARDINALITY_ALL,
    DataEnvelope,
    RunResult,
)
from vibeflow.graph_config import GraphConfig, parse_graph_config
from vibeflow.portable import SourceRef
from vibeflow.registry import NodeRegistry
from vibeflow.runtime import PipelineRuntime, RuntimeOptions


@dataclass(frozen=True)
class PortableConformanceCase:
    name: str
    document: Mapping[str, Any]
    inputs: Mapping[str, Any]
    registry: NodeRegistry
    javascript_source: str
    javascript_exports: Mapping[str, str]


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
        assert self.python.error == self.javascript.error


def run_portable_conformance(
    case: PortableConformanceCase,
    *,
    work_dir: Path,
) -> PortableConformanceResult:
    """Run one real graph through Python and emitted JavaScript."""

    graph = parse_graph_config(case.document)
    runtime = PipelineRuntime(
        graph,
        registry=case.registry,
        run_dir=work_dir / "python-run",
        runtime_options=RuntimeOptions(trace="full"),
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

    python_observation = _run_python(runtime, graph, case.inputs)
    javascript_observation = _run_javascript(
        portable_plan,
        case.javascript_source,
        case.inputs,
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
        error=error,
    )


def _run_javascript(
    portable_plan: object,
    node_source: str,
    inputs: Mapping[str, Any],
    *,
    work_dir: Path,
) -> RuntimeObservation:
    work_dir.mkdir(parents=True, exist_ok=True)
    (work_dir / "nodes.mjs").write_text(node_source, encoding="utf-8")
    emitted = emit_workflow_module(portable_plan)
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
let publicOutputs = {{}};
let error = null;
try {{
  publicOutputs = await workflow.{entry_name}(
    {json.dumps(dict(inputs), ensure_ascii=False)},
    {{ trace: "full", onTrace: event => trace.push(event) }},
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
}}
process.stdout.write(JSON.stringify({{
  public_outputs: publicOutputs,
  node_runs: nodeRuns,
  edge_runs: edgeRuns,
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
        error=error,
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
