from __future__ import annotations

import operator
import time
from concurrent.futures import Future, TimeoutError, ThreadPoolExecutor
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
from .runtime_options import RuntimeOptions, runtime_hook_table, runtime_options as normalize_runtime_options
from .runtime_trace import RuntimeTrace


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
        self.runtime_options = normalize_runtime_options(runtime_options)
        self.graph = graph
        self.registry = registry
        self._plugin_registry = plugin_registry
        self._runtime_plugins = plugin_registry.runtime_plugins() if plugin_registry is not None else ()
        self._runtime_hooks = runtime_hook_table(self._runtime_plugins, self.runtime_options)
        self.compiled = GraphCompiler().compile(graph, registry=registry, plugin_registry=plugin_registry)
        self._plan = build_execution_plan(graph, self.compiled, registry=registry, node_config_overrides=node_config_overrides)
        self.trace = RuntimeTrace()
        self._node_runs: dict[str, int] = {node.name: 0 for node in graph.nodes}
        self._frames = self._plan.frames
        self._nodeset_runtimes: dict[str, PipelineRuntime] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._async_results: dict[str, tuple[NodeFrame, Future[Mapping[str, object]]]] = {}
        self._detached: list[tuple[NodeFrame, Future[Mapping[str, object]]]] = []
        self._detached_timeout = False
        self._run_dir = Path(run_dir) if run_dir is not None else Path("runs") / "vibeflow"

    @classmethod
    def _from_plan(cls, parent: "PipelineRuntime", plan: ExecutionPlan) -> "PipelineRuntime":
        runtime = cls.__new__(cls)
        runtime.graph = plan.graph
        runtime.registry = parent.registry
        runtime._plugin_registry = parent._plugin_registry
        runtime._runtime_plugins = parent._runtime_plugins
        runtime._runtime_hooks = parent._runtime_hooks
        runtime.compiled = plan.compiled
        runtime._plan = plan
        runtime.trace = RuntimeTrace()
        runtime._node_runs = {name: 0 for name in plan.order}
        runtime._frames = plan.frames
        runtime._nodeset_runtimes = {}
        runtime._executor = None
        runtime._async_results = {}
        runtime._detached = []
        runtime._detached_timeout = False
        runtime._run_dir = parent._run_dir
        runtime.runtime_options = parent.runtime_options
        return runtime

    def run(self, initial: Mapping[str, Any] | None = None) -> Context:
        self._reset_run_state()
        context = Context(dict(initial or {}))
        try:
            self._record_run_boundary("run_start")
            self._call_runtime_plugins("before_run", context.to_dict())
            if self.runtime_options.execution == "block":
                self._run_block_steps(context)
            else:
                self._run_steps(context)
            self._flush_async_results(context)
            self._flush_detached()
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._record_run_boundary("run_end")
            self._call_runtime_plugins("after_run", context.to_dict(), self.trace.to_dict())
        except Exception as exc:
            self._flush_detached()
            self.trace.stop_reason = self.trace.stop_reason or "node_failed"
            self.trace.exception = str(exc)
            self._write_trace(context)
            self._shutdown_executor()
            raise
        self._write_trace(context)
        self._shutdown_executor()
        return context

    def _reset_run_state(self) -> None:
        self.trace = RuntimeTrace()
        self._node_runs = {name: 0 for name in self._plan.order}
        self._async_results = {}
        self._detached = []
        self._detached_timeout = False

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

    def _run_block_steps(self, context: Context) -> None:
        self._assert_block_eligible()
        ready = self._initial_ready_nodes(context)
        if len(ready) != 1:
            raise PipelineRuntimeError("block execution requires exactly one ready start node")
        node_name = ready[0]
        for _ in range(self._plan.max_steps):
            if not self._requirements_available(node_name, context):
                self.trace.stop_reason = "no_ready_nodes"
                return
            outputs = self._run_node(node_name, context)
            self.trace.step_count += 1
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
            active = self._activated_edges(node_name, outputs, context)
            if len(active) != 1:
                raise PipelineRuntimeError(f"block execution requires exactly one active edge from '{node_name}'")
            edge = active[0]
            self._record_edge(edge)
            node_name = edge.target
        self.trace.stop_reason = "max_steps"
        raise PipelineRuntimeError(f"pipeline exceeded max_steps={self._plan.max_steps}")

    def _assert_block_eligible(self) -> None:
        for name in self._plan.order:
            outgoing = self._frames[name].outgoing
            if len(outgoing) <= 1:
                continue
            if not all(edge.when for edge in outgoing):
                raise PipelineRuntimeError(f"block execution only supports conditional multi-edge routes: {name}")

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
        for key in self._frames[node_name].requires:
            if not context.exists(key) and key in self._async_results:
                self._join_async_result(key, context)
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
        if frame.async_mode:
            return self._run_async_node(frame, context)
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
            outputs = self._execute_pure_outputs(frame, inputs)
            for key, value in outputs.items():
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

    def _execute_pure_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        node = frame.node
        if node is None:
            raise PipelineRuntimeError(f"node '{frame.name}' has no bound callable")
        outputs = node.run_pure(inputs, frame.params)
        if not isinstance(outputs, Mapping):
            raise PipelineRuntimeError(f"node '{frame.name}' must return a mapping")
        unexpected = set(outputs) - set(frame.provides)
        if unexpected:
            raise PipelineRuntimeError(f"node '{frame.name}' returned undeclared outputs: {sorted(unexpected)}")
        missing = set(frame.provides) - set(outputs)
        if missing:
            raise PipelineRuntimeError(f"node '{frame.name}' missed declared outputs: {sorted(missing)}")
        return outputs

    def _run_async_node(self, frame: NodeFrame, context: Context) -> Mapping[str, object]:
        if frame.async_mode == "result_key" and frame.result_key not in frame.provides:
            raise PipelineRuntimeError(f"async node '{frame.name}' result_key must be declared in provides")
        inputs = {key: context.get(key) for key in frame.requires}
        self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
        future = self._executor_for_async().submit(self._execute_async_outputs, frame, inputs)
        self._mark_node_run(frame.name)
        if frame.async_mode == "detached":
            self._detached.append((frame, future))
            self._record_runtime_event("async_detached", frame.name, frame.node_type, input_summary=summarize_mapping(inputs))
            return {}
        self._async_results[frame.result_key] = (frame, future)
        self._record_runtime_event("async_result", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), output_summary={frame.result_key: {"type": "future"}})
        return {}

    def _execute_async_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.is_nodeset:
            return self._run_nodeset_outputs(frame, inputs)
        return self._execute_pure_outputs(frame, inputs)

    def _run_nodeset(self, frame: NodeFrame, context: Context) -> None:
        nodeset = self.graph.nodesets.get(frame.nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown nodeset: {frame.nodeset_name}")
        if set(frame.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' requires must match nodeset '{nodeset.name}' requires")
        if set(frame.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' provides must match nodeset '{nodeset.name}' provides")
        if set(frame.provides) - set(frame.exports):
            raise PipelineRuntimeError(f"nodeset '{nodeset.name}' cannot export undeclared keys: {sorted(set(frame.provides) - set(frame.exports))}")
        outputs = self._run_nodeset_outputs(frame, {key: context.get(key) for key in frame.requires}, cached=True)
        for key, value in outputs.items():
            context.set(key, value)

    def _run_nodeset_outputs(self, frame: NodeFrame, inputs: Mapping[str, object], *, cached: bool = False) -> Mapping[str, object]:
        if frame.subplan is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' has no execution plan")
        if set(frame.provides) - set(frame.exports):
            raise PipelineRuntimeError(f"nodeset '{frame.nodeset_name}' cannot export undeclared keys: {sorted(set(frame.provides) - set(frame.exports))}")
        runtime = self._nodeset_runtime(frame) if cached else PipelineRuntime._from_plan(self, frame.subplan)
        nested_context = runtime.run(inputs)
        return {key: nested_context.get(key) for key in frame.provides}

    def _nodeset_runtime(self, frame: NodeFrame) -> "PipelineRuntime":
        runtime = self._nodeset_runtimes.get(frame.name)
        if runtime is None:
            if frame.subplan is None:
                raise PipelineRuntimeError(f"nodeset node '{frame.name}' has no execution plan")
            runtime = PipelineRuntime._from_plan(self, frame.subplan)
            self._nodeset_runtimes[frame.name] = runtime
        return runtime

    def _executor_for_async(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=4)
        return self._executor

    def _join_async_result(self, key: str, context: Context) -> None:
        frame, future = self._async_results.pop(key)
        try:
            outputs = future.result()
        except Exception as exc:
            self._record_runtime_event("node_failed", frame.name, frame.node_type, failure=str(exc))
            raise
        context.set(key, outputs[key])
        self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping({key: outputs[key]}))
        self._record_runtime_event("async_result_join", frame.name, frame.node_type, output_summary=summarize_mapping({key: outputs[key]}))

    def _flush_async_results(self, context: Context) -> None:
        for key in tuple(self._async_results):
            self._join_async_result(key, context)

    def _flush_detached(self) -> None:
        timeout = self.runtime_options.async_flush_timeout
        for frame, future in self._detached:
            try:
                outputs = future.result(timeout=timeout)
            except TimeoutError:
                self._detached_timeout = True
                self._record_runtime_event("async_detached_timeout", frame.name, frame.node_type, failure="async detached flush timed out")
                continue
            except Exception as exc:
                self._record_runtime_event("async_detached_failed", frame.name, frame.node_type, failure=str(exc))
                continue
            self._record_runtime_event("async_detached_done", frame.name, frame.node_type, output_summary=summarize_mapping(outputs))
        self._detached = []

    def _shutdown_executor(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=not self._detached_timeout, cancel_futures=self._detached_timeout)
            self._executor = None

    def _record_edge(self, edge: EdgeSpec) -> None:
        key = f"{edge.source}->{edge.target}"
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
        methods = self._runtime_hooks.get(hook, ())
        if not methods:
            return
        for plugin_name, method in methods:
            try:
                method(*args)
            except Exception as exc:
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
        if self.runtime_options.trace == "boundary" and kind not in {"run_start", "run_end", "nodeset_enter", "nodeset_exit", "nodeset_failed", "node_failed", "async_detached_failed", "async_detached_timeout"}:
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

def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
