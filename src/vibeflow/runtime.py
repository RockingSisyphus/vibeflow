from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from .block_compiler import explain_block_compilation, graph_block, loop_block, nodeset_block
from .compiler import GraphCompiler
from .data_contract import (
    CARDINALITY_ALL,
    CARDINALITY_EXACTLY_ONE,
    CARDINALITY_OPTIONAL_ONE,
    DataEnvelope,
    DataProvider,
    DataRequirement,
    RunResult,
    provider_keys,
)
from .execution_plan import ExecutionPlan, NodeFrame, build_execution_plan
from .graph_config import EdgeSpec, GraphConfig, JOIN_POLICY_ALL, JOIN_POLICY_ANY_ACTIVE
from .planned_behavior import load_stub_callable, resolve_stub_module_path, signature_is_run_stub
from .plugin import PluginRegistry
from .registry import NodeRegistry, NodeRegistryError
from .runtime_compiled import run_compiled_steps
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import condition_matches, elapsed_ms, has_planned, planned_items
from .runtime_options import RuntimeOptions, runtime_hook_plan, runtime_options as normalize_runtime_options
from .runtime_trace import RuntimeTrace, RuntimeTraceSink

from .runtime_async_mixin import RuntimeAsyncMixin
from .runtime_loop_mixin import RuntimeLoopMixin
from .runtime_node_mixin import RuntimeNodeMixin
from .runtime_nodeset_mixin import RuntimeNodesetMixin
from .runtime_output_mixin import RuntimeOutputMixin
from .runtime_trace_mixin import RuntimeTraceMixin
from .runtime_types import _RuntimeState
from .summaries import summarize_mapping


class PipelineRuntime(RuntimeLoopMixin, RuntimeNodeMixin, RuntimeNodesetMixin, RuntimeAsyncMixin, RuntimeOutputMixin, RuntimeTraceMixin):
    def __init__(
        self,
        graph: GraphConfig,
        *,
        registry: NodeRegistry,
        boundary_registry: object | None = None,
        plugin_registry: PluginRegistry | None = None,
        run_dir: str | Path | None = None,
        node_config_overrides: Mapping[str, Mapping[str, object]] | None = None,
        global_config: Mapping[str, Any] | None = None,
        runtime_options: RuntimeOptions | Mapping[str, object] | None = None,
    ) -> None:
        self.runtime_options = normalize_runtime_options(runtime_options)
        if boundary_registry is not None:
            raise PipelineRuntimeError("boundary_registry is removed; use flowchart nodes")
        self._assert_planned_runtime_allowed(graph)
        self.graph = graph
        self.registry = registry
        self._plugin_registry = plugin_registry
        self._runtime_plugins = plugin_registry.runtime_plugins() if plugin_registry is not None else ()
        self._hook_plan = runtime_hook_plan(self._runtime_plugins, self.runtime_options)
        self.compiled = GraphCompiler().compile(graph, registry=registry, plugin_registry=plugin_registry)
        self._plan = build_execution_plan(
            graph,
            self.compiled,
            registry=registry,
            node_config_overrides=node_config_overrides,
            global_config=global_config,
            runtime_options=self.runtime_options,
        )
        self.trace = RuntimeTrace()
        self._node_runs: dict[str, int] = {node.name: 0 for node in graph.nodes}
        self._frames = self._plan.frames
        self._nodeset_runtimes: dict[str, PipelineRuntime] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._async_results: dict[str, tuple[NodeFrame, Future[Mapping[str, object]]]] = {}
        self._detached: list[tuple[NodeFrame, Future[Mapping[str, object]]]] = []
        self._detached_timeout = False
        self._abandoned_async_results = False
        self._run_dir = Path(run_dir) if run_dir is not None else Path("runs") / "vibeflow"
        self._trace_sink: RuntimeTraceSink | None = None
        self._trace_path_prefix: tuple[str, ...] = ()

    def _assert_planned_runtime_allowed(self, graph: GraphConfig) -> None:
        if not has_planned(graph):
            return
        items = planned_items(graph)
        if self.runtime_options.allow_planned_stub and all(item.get("behavior") == "python_stub" for item in items):
            return
        if self.runtime_options.allow_planned_stub:
            blocked = [str(item.get("id", "")) for item in items if item.get("behavior") != "python_stub"]
            raise PipelineRuntimeError("only planned python_stub nodes/nodesets can run with allow_planned_stub: " + ", ".join(blocked))
        raise PipelineRuntimeError("planned nodes/nodesets cannot run")

    @classmethod
    def _from_plan(cls, parent: "PipelineRuntime", plan: ExecutionPlan) -> "PipelineRuntime":
        runtime = cls.__new__(cls)
        runtime.graph = plan.graph
        runtime.registry = parent.registry
        runtime._plugin_registry = parent._plugin_registry
        runtime._runtime_plugins = parent._runtime_plugins
        runtime._hook_plan = parent._hook_plan
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
        runtime._abandoned_async_results = False
        runtime._run_dir = parent._run_dir
        runtime._trace_sink = parent._trace_sink
        runtime._trace_path_prefix = parent._trace_path_prefix
        runtime.runtime_options = parent.runtime_options
        return runtime

    def run(self, initial: Mapping[str, Any] | None = None) -> RunResult:
        owns_trace_sink = self._trace_sink is None
        if owns_trace_sink:
            self._trace_path_prefix = ()
            self._trace_sink = RuntimeTraceSink(self._trace_file_path())
            self._trace_sink.open()
        self._reset_run_state()
        state = self._new_state(initial or {})
        try:
            self._record_run_boundary("run_start")
            self._call_runtime_plugins("before_run", dict(initial or {}))
            if self.runtime_options.execution == "compiled":
                run_compiled_steps(self, state)
            elif self.runtime_options.execution == "block":
                self._run_block_steps(state)
            else:
                self._run_steps(state)
            self._abandon_async_results()
            self._flush_detached()
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._finalize_pipeline_outputs(state)
            self._record_run_boundary("run_end")
            self._write_trace(state.result)
            self._call_runtime_plugins("after_run", state.result.to_dict(), self.trace.to_dict())
        except Exception as exc:
            self._abandon_async_results()
            self._flush_detached()
            self.trace.stop_reason = self.trace.stop_reason or "node_failed"
            self.trace.exception = str(exc)
            self._write_trace(state.result)
            self._call_runtime_plugins("run_failed", state.result.to_dict(), self.trace.to_dict(), str(exc))
            self._shutdown_executor()
            raise
        finally:
            if owns_trace_sink and self._trace_sink is not None:
                self._trace_sink.write_summary(self.trace)
                self._trace_sink.close()
                self._trace_sink = None
        self._shutdown_executor()
        return state.result

    def _new_state(self, initial: Mapping[str, Any]) -> _RuntimeState:
        state = _RuntimeState(inboxes={name: [] for name in self._frames})
        input_envelopes = []
        for provider in self.graph.inputs:
            if provider.key not in initial:
                continue
            input_envelopes.append(DataEnvelope(key=provider.key, type=provider.type, value=initial[provider.key], source_node="pipeline.input"))
        for node_name in self._initial_input_nodes():
            frame = self._frames[node_name]
            accepted = {requirement.type for requirement in frame.requires}
            state.inboxes[node_name].extend(envelope for envelope in input_envelopes if envelope.type in accepted)
        return state

    def _initial_input_nodes(self) -> tuple[str, ...]:
        nodes: list[str] = []
        for name in self._plan.order:
            frame = self._frames[name]
            if not frame.requires:
                continue
            if not frame.incoming:
                nodes.append(name)
                continue
            if any(self._is_empty_start(edge.source) for edge in frame.incoming):
                nodes.append(name)
        return tuple(nodes)

    def _is_empty_start(self, node_name: str) -> bool:
        frame = self._frames.get(node_name)
        return bool(frame and frame.is_terminal and not frame.incoming and not frame.requires and not frame.provides)

    def _reset_run_state(self) -> None:
        self.trace = RuntimeTrace(trace_path=str(self._trace_file_path()))
        self._node_runs = {name: 0 for name in self._plan.order}
        self._async_results = {}
        self._detached = []
        self._detached_timeout = False
        self._abandoned_async_results = False

    def _trace_file_path(self) -> Path:
        if self._trace_sink is not None:
            return self._trace_sink.path
        return self._run_dir / "runtime_trace.jsonl"

    def _run_steps(self, state: _RuntimeState) -> None:
        ready = list(self._initial_ready_nodes(state))
        queued = set(ready)
        for _ in range(self._plan.max_steps):
            if not ready:
                self.trace.stop_reason = "no_ready_nodes"
                return
            node_name = ready.pop(0)
            queued.discard(node_name)
            if not self._requirements_available(node_name, state):
                continue
            outputs = self._run_node(node_name, state)
            self.trace.step_count += 1
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
            self._clear_conditional_outgoing(node_name, state)
            active_edges = self._activated_edges(node_name, outputs, state)
            active_pairs = {edge.pair for edge in active_edges}
            for edge in active_edges:
                self._activate_edge(edge, state)
                self._deliver_outputs(edge, outputs, state)
                if edge.target not in queued:
                    ready.append(edge.target)
                    queued.add(edge.target)
            self._deliver_transfer_only_edges(node_name, outputs, state, active_pairs)
        self.trace.stop_reason = "max_steps"
        raise PipelineRuntimeError(f"pipeline exceeded max_steps={self._plan.max_steps}")

    def _run_block_steps(self, state: _RuntimeState) -> None:
        block = graph_block(self._plan)
        if block is not None:
            block.callable(self, state)
            return
        details = _block_compile_error_details(self._plan)
        raise PipelineRuntimeError(f"block execution requires a compiled graph block: {details}")

    def _execute_graph_block(self, block_name: str, block_nodes: tuple[str, ...], state: _RuntimeState) -> tuple[str, Mapping[str, object]]:
        started = time.perf_counter()
        self._record_runtime_event("block_enter", block_name, "block")
        self._call_runtime_plugins("before_block", block_name, block_nodes)
        ready = self._initial_ready_nodes(state)
        if len(ready) != 1:
            raise PipelineRuntimeError("block execution requires exactly one ready start node")
        node_name = ready[0]
        outputs: Mapping[str, object] = {}
        last_node = node_name
        try:
            for _ in range(self._plan.max_steps):
                if not self._requirements_available(node_name, state):
                    self.trace.stop_reason = "no_ready_nodes"
                    return last_node, outputs
                outputs = self._run_node(node_name, state)
                last_node = node_name
                self.trace.step_count += 1
                if self._is_end_terminal(node_name):
                    self.trace.stop_reason = "completed"
                    self._record_runtime_event("block_exit", block_name, "block", output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
                    self._call_runtime_plugins("after_block", block_name, block_nodes)
                    return last_node, outputs
                self._clear_conditional_outgoing(node_name, state)
                active = self._activated_edges(node_name, outputs, state)
                if len(active) != 1:
                    raise PipelineRuntimeError(f"block execution requires exactly one active edge from '{node_name}'")
                edge = active[0]
                self._activate_edge(edge, state)
                self._deliver_outputs(edge, outputs, state)
                self._deliver_transfer_only_edges(node_name, outputs, state, {edge.pair})
                node_name = edge.target
            self.trace.stop_reason = "max_steps"
            raise PipelineRuntimeError(f"pipeline exceeded max_steps={self._plan.max_steps}")
        except Exception as exc:
            self._record_runtime_event("block_failed", block_name, "block", failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("block_failed", block_name, block_nodes, str(exc))
            raise

    def _assert_block_eligible(self) -> None:
        for name in self._plan.order:
            outgoing = self._frames[name].outgoing
            if len(outgoing) <= 1:
                continue
            if not all(edge.when for edge in outgoing):
                raise PipelineRuntimeError(f"block execution only supports conditional multi-edge routes: {name}")

    def _initial_ready_nodes(self, state: _RuntimeState) -> tuple[str, ...]:
        ready = []
        for node_name in self._plan.order:
            frame = self._frames[node_name]
            if frame.incoming:
                continue
            if not frame.is_terminal:
                continue
            if self._requirements_available(node_name, state):
                ready.append(node_name)
        return tuple(ready)

    def _requirements_available(self, node_name: str, state: _RuntimeState) -> bool:
        self._join_async_incoming(node_name, state)
        frame = self._frames[node_name]
        if not self._conditional_gate_satisfied(frame, state):
            return False
        for requirement in frame.requires:
            matches = [envelope for envelope in state.inboxes[node_name] if envelope.type == requirement.type]
            if requirement.cardinality == CARDINALITY_EXACTLY_ONE and not matches:
                return False
        return True

    def _conditional_gate_satisfied(self, frame: NodeFrame, state: _RuntimeState) -> bool:
        if not frame.incoming:
            return True
        if frame.join_policy == JOIN_POLICY_ALL:
            return all(edge.pair in state.active_edges for edge in frame.incoming)
        if frame.join_policy == JOIN_POLICY_ANY_ACTIVE:
            return True
        control_edges = [edge for edge in frame.incoming if edge.when and not self._edge_source_satisfies_requirement(edge, frame)]
        if control_edges:
            return any(edge.pair in state.active_edges for edge in control_edges)
        return True

    def _edge_source_satisfies_requirement(self, edge: EdgeSpec, frame: NodeFrame) -> bool:
        source = self._frames.get(edge.source)
        if source is None:
            return False
        required_types = {requirement.type for requirement in frame.requires}
        return any(provider.type in required_types for provider in source.provides)

    def _is_end_terminal(self, node_name: str) -> bool:
        frame = self._frames[node_name]
        if frame.outgoing:
            return False
        return frame.is_terminal

    def _activated_edges(self, node_name: str, outputs: Mapping[str, object], state: _RuntimeState) -> tuple[EdgeSpec, ...]:
        active = []
        values = self._condition_values(node_name, outputs, state)
        for edge in self._frames[node_name].outgoing:
            if not edge.when or condition_matches(edge.when, values):
                active.append(edge)
        return tuple(active)

    def _condition_values(self, node_name: str, outputs: Mapping[str, object], state: _RuntimeState) -> dict[str, object]:
        values = dict(outputs)
        for value in state.last_inputs.get(node_name, {}).values():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, Mapping):
                        values[str(item.get("key", ""))] = item.get("value")
            elif isinstance(value, Mapping):
                values[str(value.get("key", ""))] = value.get("value")
        return values

    def _run_node(self, node_name: str, state: _RuntimeState) -> Mapping[str, object]:
        self.trace.current_node = node_name
        frame = self._frames[node_name]
        inputs = self._resolve_inputs(frame, state)
        state.last_inputs[node_name] = inputs
        state.inboxes[node_name] = []
        if frame.async_mode:
            return self._run_async_node(frame, inputs)
        if frame.is_planned_stub:
            return self._run_planned_stub_node(frame, inputs)
        if frame.is_loop:
            if self.runtime_options.execution == "block":
                return self._run_loop_block_node(frame, inputs)
            if self.runtime_options.execution == "compiled" and loop_block(self._plan, frame.name) is not None:
                return self._run_loop_block_node(frame, inputs)
            return self._run_loop_node(frame, inputs)
        if frame.is_nodeset:
            if self.runtime_options.execution == "compiled" and nodeset_block(self._plan, frame.name) is not None:
                return self._run_nodeset_block_node(frame, inputs)
            return self._run_nodeset_node(frame, inputs)
        return self._run_pure_node(frame, inputs)

    def _resolve_inputs(self, frame: NodeFrame, state: _RuntimeState) -> dict[str, object]:
        inputs: dict[str, object] = {}
        for requirement in frame.requires:
            matches = [envelope for envelope in state.inboxes[frame.name] if envelope.type == requirement.type]
            self._record_type_resolution(frame, requirement, matches)
            if requirement.cardinality == CARDINALITY_EXACTLY_ONE:
                if len(matches) != 1:
                    raise PipelineRuntimeError(f"node '{frame.name}' requires type '{requirement.type}' exactly once, got {len(matches)}")
                inputs[requirement.type] = matches[0].to_input()
            elif requirement.cardinality == CARDINALITY_OPTIONAL_ONE:
                if len(matches) > 1:
                    raise PipelineRuntimeError(f"node '{frame.name}' requires type '{requirement.type}' at most once, got {len(matches)}")
                inputs[requirement.type] = matches[0].to_input() if matches else None
            elif requirement.cardinality == CARDINALITY_ALL:
                inputs[requirement.type] = [envelope.to_input() for envelope in matches]
            else:
                raise PipelineRuntimeError(f"node '{frame.name}' has invalid cardinality '{requirement.cardinality}'")
        return inputs


def _block_compile_error_details(plan: ExecutionPlan) -> str:
    findings = [item for item in explain_block_compilation(plan) if not bool(item.get("compiled"))]
    if not findings:
        return "unknown"
    first = findings[0]
    return f"{first.get('path')}: {first.get('reason')}"
