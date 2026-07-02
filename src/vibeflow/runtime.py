from __future__ import annotations

import operator
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .compiler import GraphCompiler
from .context import Context
from .execution_plan import ExecutionPlan, NodeFrame, build_execution_plan
from .graph_config import EdgeSpec, GraphConfig, STATUS_PLANNED
from .plugin import PluginRegistry
from .summaries import summarize_mapping
from .registry import NodeRegistry, NodeRegistryError
from .runtime_errors import PipelineRuntimeError
from .runtime_trace import RuntimeTrace
from .runtime_validation import assert_runtime_output_snapshot


@dataclass(frozen=True)
class RuntimeOptions:
    trace: str = "full"
    snapshot_outputs: bool = False
    node_hooks: bool = True

    def __post_init__(self) -> None:
        if self.trace not in {"full", "boundary", "off"}:
            raise ValueError("runtime trace must be one of: full, boundary, off")


class PipelineRuntime:
    def __init__(
        self,
        graph: GraphConfig,
        *,
        registry: NodeRegistry,
        boundary_registry: object | None = None,
        plugin_registry: PluginRegistry | None = None,
        run_dir: str | Path | None = None,
        node_config_overrides: Mapping[str, Mapping[str, object]] | None = None,
        runtime_options: RuntimeOptions | Mapping[str, object] | None = None,
    ) -> None:
        if boundary_registry is not None:
            raise PipelineRuntimeError("boundary_registry is removed; use flowchart nodes")
        if _has_planned(graph):
            raise PipelineRuntimeError("planned nodes/nodesets cannot run")
        self.graph = graph
        self.registry = registry
        self._plugin_registry = plugin_registry
        self._runtime_plugins = plugin_registry.runtime_plugins() if plugin_registry is not None else ()
        self.compiled = GraphCompiler().compile(graph, registry=registry, plugin_registry=plugin_registry)
        self._plan = build_execution_plan(graph, self.compiled, registry=registry, node_config_overrides=node_config_overrides)
        self.trace = RuntimeTrace()
        self._node_runs: dict[str, int] = {node.name: 0 for node in graph.nodes}
        self._frames = self._plan.frames
        self._run_dir = Path(run_dir) if run_dir is not None else Path("runs") / "vibeflow"
        self.runtime_options = _runtime_options(runtime_options)

    @classmethod
    def _from_plan(cls, parent: "PipelineRuntime", plan: ExecutionPlan) -> "PipelineRuntime":
        runtime = cls.__new__(cls)
        runtime.graph = plan.graph
        runtime.registry = parent.registry
        runtime._plugin_registry = parent._plugin_registry
        runtime._runtime_plugins = parent._runtime_plugins
        runtime.compiled = plan.compiled
        runtime._plan = plan
        runtime.trace = RuntimeTrace()
        runtime._node_runs = {name: 0 for name in plan.order}
        runtime._frames = plan.frames
        runtime._run_dir = parent._run_dir
        runtime.runtime_options = parent.runtime_options
        return runtime

    def run(self, initial: Mapping[str, Any] | None = None) -> Context:
        context = Context(dict(initial or {}))
        try:
            self._record_run_boundary("run_start")
            self._call_runtime_plugins("before_run", context.to_dict())
            self._run_steps(context)
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._record_run_boundary("run_end")
            self._call_runtime_plugins("after_run", context.to_dict(), self.trace.to_dict())
        except Exception as exc:
            self.trace.stop_reason = self.trace.stop_reason or "node_failed"
            self.trace.exception = str(exc)
            self._write_trace(context)
            raise
        self._write_trace(context)
        return context

    def _run_steps(self, context: Context) -> None:
        ready = list(self._initial_ready_nodes(context))
        queued = set(ready)
        for _ in range(self._plan.max_steps):
            if not ready:
                self.trace.stop_reason = "no_ready_nodes"
                return
            node_name = ready.pop(0)
            queued.discard(node_name)
            if not self._requirements_available(node_name, context):
                continue
            outputs = self._run_node(node_name, context)
            self.trace.step_count += 1
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
            for edge in self._activated_edges(node_name, outputs, context):
                self._record_edge(edge)
                if edge.target not in queued:
                    ready.append(edge.target)
                    queued.add(edge.target)
        self.trace.stop_reason = "max_steps"
        raise PipelineRuntimeError(f"pipeline exceeded max_steps={self._plan.max_steps}")

    def _initial_ready_nodes(self, context: Context) -> tuple[str, ...]:
        ready = []
        for node_name in self._plan.order:
            frame = self._frames[node_name]
            if frame.incoming:
                continue
            if not frame.is_terminal:
                continue
            if self._requirements_available(node_name, context):
                ready.append(node_name)
        return tuple(ready)

    def _requirements_available(self, node_name: str, context: Context) -> bool:
        return all(context.exists(key) for key in self._frames[node_name].requires)

    def _is_end_terminal(self, node_name: str) -> bool:
        frame = self._frames[node_name]
        if frame.outgoing:
            return False
        return frame.is_terminal

    def _is_terminal_node(self, node_name: str) -> bool:
        return self._frames[node_name].is_terminal

    def _activated_edges(self, node_name: str, outputs: Mapping[str, object], context: Context) -> tuple[EdgeSpec, ...]:
        active = []
        values = {**context.to_dict(), **dict(outputs)}
        for edge in self._frames[node_name].outgoing:
            if not edge.when or _condition_matches(edge.when, values):
                active.append(edge)
        return tuple(active)

    def _run_node(self, node_name: str, context: Context) -> Mapping[str, object]:
        self.trace.current_node = node_name
        frame = self._frames[node_name]
        if frame.is_nodeset:
            return self._run_nodeset_node(frame, context)
        return self._run_pure_node(frame, context)

    def _run_nodeset_node(self, frame: NodeFrame, context: Context) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event("nodeset_enter", frame.name, frame.node_type)
        self._call_runtime_plugins("before_nodeset", frame.name, frame.node_type)
        try:
            self._run_nodeset(frame, context)
            outputs = {key: context.get(key, default=None) for key in frame.provides}
            self._mark_node_run(frame.name)
            self._record_runtime_event("nodeset_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=_elapsed_ms(started))
            self._call_runtime_plugins("after_nodeset", frame.name, frame.node_type)
            return outputs
        except Exception as exc:
            self._record_runtime_event("nodeset_failed", frame.name, frame.node_type, failure=str(exc), elapsed_ms=_elapsed_ms(started))
            raise

    def _run_pure_node(self, frame: NodeFrame, context: Context) -> Mapping[str, object]:
        started = time.perf_counter()
        inputs: dict[str, object] = {}
        try:
            node = frame.node
            if node is None:
                raise PipelineRuntimeError(f"node '{frame.name}' has no bound callable")
            inputs = {key: context.get(key) for key in frame.requires}
            self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
            outputs = node.run_pure(inputs, frame.params)
            if not isinstance(outputs, Mapping):
                raise PipelineRuntimeError(f"node '{frame.name}' must return a mapping")
            unexpected = set(outputs) - set(frame.provides)
            if unexpected:
                raise PipelineRuntimeError(f"node '{frame.name}' returned undeclared outputs: {sorted(unexpected)}")
            missing = set(frame.provides) - set(outputs)
            if missing:
                raise PipelineRuntimeError(f"node '{frame.name}' missed declared outputs: {sorted(missing)}")
            for key, value in outputs.items():
                if self.runtime_options.snapshot_outputs:
                    assert_runtime_output_snapshot(value, contract=node.CONTRACT, node_name=frame.name, key=str(key))
                context.set(str(key), value)
            self._mark_node_run(frame.name)
            self._record_runtime_event("node", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), output_summary=summarize_mapping(outputs), elapsed_ms=_elapsed_ms(started))
            self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
            return outputs
        except NodeRegistryError as exc:
            failure = PipelineRuntimeError(str(exc))
            self._record_runtime_event("node_failed", frame.name, frame.node_type, failure=str(failure), elapsed_ms=_elapsed_ms(started))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event("node_failed", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=_elapsed_ms(started))
            raise

    def _run_nodeset(self, frame: NodeFrame, context: Context) -> None:
        nodeset = self.graph.nodesets.get(frame.nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown nodeset: {frame.nodeset_name}")
        if set(frame.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' requires must match nodeset '{nodeset.name}' requires")
        if set(frame.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' provides must match nodeset '{nodeset.name}' provides")
        if frame.subplan is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' has no execution plan")
        nested_context = PipelineRuntime._from_plan(self, frame.subplan).run({key: context.get(key) for key in frame.requires})
        for key in frame.provides:
            if key not in nodeset.exports:
                raise PipelineRuntimeError(f"nodeset '{nodeset.name}' cannot export undeclared key '{key}'")
            context.set(key, nested_context.get(key))

    def _record_edge(self, edge: EdgeSpec) -> None:
        key = _edge_key(edge.pair)
        self.trace.edge_executions[key] = self.trace.edge_executions.get(key, 0) + 1

    def _mark_node_run(self, node_name: str) -> None:
        self._node_runs[node_name] = self._node_runs.get(node_name, 0) + 1
        self.trace.node_runs[node_name] = self._node_runs[node_name]
        self.trace.exec_order.append(node_name)

    def _write_trace(self, context: Context) -> None:
        payload = self.trace.to_dict()
        context.set("runtime.exec_order", payload["exec_order"])
        context.set("runtime.edge_executions", payload["edge_executions"])
        context.set("runtime.step_count", payload["step_count"])
        context.set("runtime.node_runs", payload["node_runs"])
        context.set("runtime.stop_reason", payload["stop_reason"])
        context.set("runtime.current_node", payload["current_node"])
        context.set("runtime.exception", payload["exception"])
        context.set("runtime.events", payload["events"])

    def _call_runtime_plugins(self, hook: str, *args) -> None:
        if not self._runtime_plugins:
            return
        if not self.runtime_options.node_hooks and hook in {"before_node", "after_node"}:
            return
        for plugin in self._runtime_plugins:
            method = getattr(plugin, hook, None)
            if not callable(method):
                continue
            try:
                method(*args)
            except Exception as exc:
                plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
                raise PipelineRuntimeError(f"runtime plugin '{plugin_name}' {hook} failed: {exc}") from exc

    def _record_runtime_event(
        self,
        kind: str,
        node_name: str,
        node_type: str,
        *,
        input_summary: Mapping[str, object] | None = None,
        output_summary: Mapping[str, object] | None = None,
        elapsed_ms: float | None = None,
        failure: str = "",
    ) -> None:
        if self.runtime_options.trace == "off":
            return
        if self.runtime_options.trace == "boundary" and kind not in {"run_start", "run_end", "nodeset_enter", "nodeset_exit", "nodeset_failed", "node_failed"}:
            return
        event: dict[str, object] = {"kind": kind, "node": node_name, "type": node_type}
        if input_summary is not None:
            event["input_summary"] = dict(input_summary)
        if output_summary is not None:
            event["output_summary"] = dict(output_summary)
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        if failure:
            event["failure"] = failure
        self.trace.events.append(event)

    def _record_run_boundary(self, kind: str) -> None:
        if self.runtime_options.trace == "boundary":
            self._record_runtime_event(kind, "pipeline", "pipeline")


def _runtime_options(value: RuntimeOptions | Mapping[str, object] | None) -> RuntimeOptions:
    if value is None:
        return RuntimeOptions()
    if isinstance(value, RuntimeOptions):
        return value
    return RuntimeOptions(**dict(value))


def _condition_matches(expression: str, values: Mapping[str, object]) -> bool:
    for token, op in (("==", operator.eq), ("!=", operator.ne)):
        if token not in expression:
            continue
        left, right = (part.strip() for part in expression.split(token, 1))
        if not left or not right:
            raise PipelineRuntimeError(f"invalid edge condition: {expression}")
        return bool(op(values.get(left), _literal_value(right)))
    raise PipelineRuntimeError(f"unsupported edge condition: {expression}")


def _has_planned(graph: GraphConfig) -> bool:
    return any(node.status == STATUS_PLANNED for node in graph.nodes) or any(nodeset.status == STATUS_PLANNED or _has_planned(nodeset.graph) for nodeset in graph.nodesets.values())


def _literal_value(value: str) -> object:
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _edge_key(pair: tuple[str, str]) -> str:
    return f"{pair[0]}->{pair[1]}"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
