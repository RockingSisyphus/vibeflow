from __future__ import annotations

import time
from collections import defaultdict
from concurrent.futures import Future, TimeoutError, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

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
from .graph_config import EdgeSpec, GraphConfig
from .planned_behavior import load_stub_callable, resolve_stub_module_path, signature_is_run_stub
from .plugin import PluginRegistry
from .registry import NodeRegistry, NodeRegistryError
from .runtime_compiled import run_compiled_steps
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import condition_matches, elapsed_ms, has_planned, planned_items
from .runtime_options import RuntimeOptions, runtime_hook_plan, runtime_options as normalize_runtime_options
from .runtime_trace import RuntimeTrace
from .summaries import summarize_mapping


@dataclass
class _RuntimeState:
    inboxes: dict[str, list[DataEnvelope]]
    result: RunResult = field(default_factory=RunResult)
    output_candidates: dict[str, list[DataEnvelope]] = field(default_factory=lambda: defaultdict(list))
    last_inputs: dict[str, dict[str, object]] = field(default_factory=dict)
    active_edges: set[tuple[str, str]] = field(default_factory=set)


@dataclass(frozen=True)
class _AsyncOutputs:
    outputs: Mapping[str, object]
    child_trace: RuntimeTrace | None = None


class _NestedRuntimeFailure(PipelineRuntimeError):
    def __init__(self, message: str, child_trace: RuntimeTrace) -> None:
        super().__init__(message)
        self.child_trace = child_trace


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
        runtime.runtime_options = parent.runtime_options
        return runtime

    def run(self, initial: Mapping[str, Any] | None = None) -> RunResult:
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
        self.trace = RuntimeTrace()
        self._node_runs = {name: 0 for name in self._plan.order}
        self._async_results = {}
        self._detached = []
        self._detached_timeout = False
        self._abandoned_async_results = False

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
            for edge in self._activated_edges(node_name, outputs, state):
                self._activate_edge(edge, state)
                self._deliver_outputs(edge, outputs, state)
                if edge.target not in queued:
                    ready.append(edge.target)
                    queued.add(edge.target)
        self.trace.stop_reason = "max_steps"
        raise PipelineRuntimeError(f"pipeline exceeded max_steps={self._plan.max_steps}")

    def _run_block_steps(self, state: _RuntimeState) -> None:
        try:
            self._assert_block_eligible()
        except PipelineRuntimeError:
            self._run_steps(state)
            return
        ready = self._initial_ready_nodes(state)
        if len(ready) != 1:
            raise PipelineRuntimeError("block execution requires exactly one ready start node")
        node_name = ready[0]
        for _ in range(self._plan.max_steps):
            if not self._requirements_available(node_name, state):
                self.trace.stop_reason = "no_ready_nodes"
                return
            outputs = self._run_node(node_name, state)
            self.trace.step_count += 1
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
            self._clear_conditional_outgoing(node_name, state)
            active = self._activated_edges(node_name, outputs, state)
            if len(active) != 1:
                raise PipelineRuntimeError(f"block execution requires exactly one active edge from '{node_name}'")
            edge = active[0]
            self._activate_edge(edge, state)
            self._deliver_outputs(edge, outputs, state)
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
        conditional_edges = [edge for edge in frame.incoming if edge.when]
        if not conditional_edges:
            return True
        return any(edge.pair in state.active_edges for edge in conditional_edges)

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
        if frame.is_nodeset:
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

    def _record_type_resolution(self, frame: NodeFrame, requirement: DataRequirement, matches: list[DataEnvelope]) -> None:
        self._record_runtime_event(
            "type_resolve",
            frame.name,
            frame.node_type,
            details={
                "consumer": frame.name,
                "required_type": requirement.type,
                "cardinality": requirement.cardinality,
                "matched_count": len(matches),
                "resolved_source_keys": [match.key for match in matches],
                "source_nodes": [match.source_node for match in matches],
            },
        )

    def _run_planned_stub_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        try:
            self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
            outputs = self._execute_planned_stub_outputs(frame, inputs)
            self._mark_node_run(frame.name)
            self._record_runtime_event(
                "planned_stub",
                frame.name,
                frame.node_type,
                input_summary=summarize_mapping(inputs),
                output_summary=summarize_mapping(outputs),
                elapsed_ms=elapsed_ms(started),
                details={
                    "stub_module": frame.planned_stub_module,
                    "stub_path": frame.planned_stub_path,
                    "stub_sha256": frame.planned_stub_hash,
                    "input_types": list(inputs),
                    "output_keys": list(outputs),
                },
            )
            self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
            return outputs
        except Exception as exc:
            self._record_runtime_event("node_failed", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            raise

    def _run_nodeset_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event("nodeset_enter", frame.name, frame.node_type)
        self._call_runtime_plugins("before_nodeset", frame.name, frame.node_type)
        try:
            outputs = self._run_nodeset_outputs(frame, inputs, cached=True)
            self._mark_node_run(frame.name)
            self._record_runtime_event("nodeset_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("after_nodeset", frame.name, frame.node_type)
            return outputs
        except Exception as exc:
            self._record_runtime_event("nodeset_failed", frame.name, frame.node_type, failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("nodeset_failed", frame.name, frame.node_type, str(exc))
            raise

    def _run_pure_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        try:
            node = frame.node
            if node is None:
                raise PipelineRuntimeError(f"node '{frame.name}' has no bound callable")
            self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
            outputs = self._execute_pure_outputs(frame, inputs)
            self._mark_node_run(frame.name)
            self._record_runtime_event("node", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
            return outputs
        except NodeRegistryError as exc:
            failure = PipelineRuntimeError(str(exc))
            self._record_runtime_event("node_failed", frame.name, frame.node_type, failure=str(failure), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(failure))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event("node_failed", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            raise

    def _execute_pure_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        node = frame.node
        if node is None:
            raise PipelineRuntimeError(f"node '{frame.name}' has no bound callable")
        outputs = node.run_pure(inputs, frame.params)
        return self._validate_outputs(frame, outputs)

    def _execute_planned_stub_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if not self.runtime_options.allow_planned_stub:
            raise PipelineRuntimeError(f"planned python_stub node '{frame.name}' requires allow_planned_stub")
        if frame.is_nodeset:
            self._assert_planned_stub_nodeset_contract(frame)
        try:
            path = Path(frame.planned_stub_path) if frame.planned_stub_path else resolve_stub_module_path(frame.planned_stub_module, self.graph.project_root)
            run_stub = load_stub_callable(path)
        except Exception as exc:
            raise PipelineRuntimeError(f"planned python_stub '{frame.name}' failed to load stub: {exc}") from exc
        if not signature_is_run_stub(run_stub):
            raise PipelineRuntimeError(f"planned python_stub '{frame.name}' must expose run_stub(inputs, params)")
        outputs = run_stub(dict(inputs), dict(frame.params))
        return self._validate_outputs(frame, outputs, subject="planned python_stub")

    def _validate_outputs(self, frame: NodeFrame, outputs: object, *, subject: str = "node") -> Mapping[str, object]:
        if not isinstance(outputs, Mapping):
            raise PipelineRuntimeError(f"{subject} '{frame.name}' must return a mapping")
        actual = {str(key) for key in outputs}
        expected = set(frame.provide_keys)
        if actual != expected:
            raise PipelineRuntimeError(f"{subject} '{frame.name}' output keys must exactly match provides: expected {sorted(expected)}, got {sorted(actual)}")
        return {str(key): value for key, value in outputs.items()}

    def _assert_planned_stub_nodeset_contract(self, frame: NodeFrame) -> None:
        nodeset = self.graph.nodesets.get(frame.nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown planned python_stub nodeset: {frame.nodeset_name}")
        if not nodeset.provides or not nodeset.exports:
            raise PipelineRuntimeError(f"planned python_stub nodeset '{nodeset.name}' must declare provides and exports")
        if set(frame.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(f"planned python_stub nodeset node '{frame.name}' requires must match nodeset '{nodeset.name}' requires")
        if set(frame.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(f"planned python_stub nodeset node '{frame.name}' provides must match nodeset '{nodeset.name}' provides")
        if set(frame.provide_keys) != set(frame.export_keys):
            raise PipelineRuntimeError(f"planned python_stub nodeset '{nodeset.name}' provides must match exports")

    def _run_async_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.async_mode == "result_key" and frame.result_key not in frame.provide_keys:
            raise PipelineRuntimeError(f"async node '{frame.name}' result_key must be declared in provides")
        self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
        future = self._executor_for_async().submit(self._execute_async_outputs, frame, inputs)
        self._mark_node_run(frame.name)
        if frame.async_mode == "detached":
            self._detached.append((frame, future))
            self._record_runtime_event("async_detached", frame.name, frame.node_type, input_summary=summarize_mapping(inputs))
            return {}
        self._async_results[frame.name] = (frame, future)
        self._record_runtime_event("async_result", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), output_summary={frame.result_key: {"type": "future"}})
        return {}

    def _execute_async_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.is_planned_stub:
            return self._execute_planned_stub_outputs(frame, inputs)
        if frame.is_nodeset:
            outputs, child_trace = self._run_nodeset_outputs_with_trace(frame, inputs, cached=False)
            return _AsyncOutputs(outputs=outputs, child_trace=child_trace)
        return self._execute_pure_outputs(frame, inputs)

    def _run_nodeset_outputs(self, frame: NodeFrame, inputs: Mapping[str, object], *, cached: bool = False) -> Mapping[str, object]:
        try:
            outputs, child_trace = self._run_nodeset_outputs_with_trace(frame, inputs, cached=cached)
        except _NestedRuntimeFailure as exc:
            self._merge_child_trace(frame, exc.child_trace)
            if exc.__cause__ is not None:
                raise exc.__cause__ from exc
            raise
        self._merge_child_trace(frame, child_trace)
        return outputs

    def _run_nodeset_outputs_with_trace(self, frame: NodeFrame, inputs: Mapping[str, object], *, cached: bool = False) -> tuple[Mapping[str, object], RuntimeTrace]:
        if frame.subplan is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' has no execution plan")
        if set(frame.provide_keys) - set(frame.export_keys):
            raise PipelineRuntimeError(f"nodeset '{frame.nodeset_name}' cannot export undeclared keys: {sorted(set(frame.provide_keys) - set(frame.export_keys))}")
        runtime = self._nodeset_runtime(frame) if cached else PipelineRuntime._from_plan(self, frame.subplan)
        initial = _nodeset_inputs_to_initial(inputs, frame.subplan.graph.inputs)
        try:
            nested_result = runtime.run(initial)
        except Exception as exc:
            raise _NestedRuntimeFailure(str(exc), runtime.trace) from exc
        outputs = {}
        for provider in frame.provides:
            nested_value = nested_result.get(provider.type)
            outputs[provider.key] = _result_value(nested_value)
        return outputs, runtime.trace

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

    def _join_async_incoming(self, node_name: str, state: _RuntimeState) -> None:
        for edge in self._frames[node_name].incoming:
            if edge.source in self._async_results:
                self._join_async_source(edge.source, state)

    def _join_async_source(self, node_name: str, state: _RuntimeState) -> None:
        frame, future = self._async_results.pop(node_name)
        try:
            outputs = self._unwrap_async_outputs(frame, future.result())
        except _NestedRuntimeFailure as exc:
            self._merge_child_trace(frame, exc.child_trace)
            self._record_runtime_event("node_failed", frame.name, frame.node_type, failure=str(exc))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            if exc.__cause__ is not None:
                raise exc.__cause__ from exc
            raise
        except Exception as exc:
            self._record_runtime_event("node_failed", frame.name, frame.node_type, failure=str(exc))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            raise
        self._clear_conditional_outgoing(frame.name, state)
        for edge in self._activated_edges(frame.name, outputs, state):
            self._activate_edge(edge, state)
            self._deliver_outputs(edge, outputs, state)
        self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
        self._record_runtime_event("async_result_join", frame.name, frame.node_type, output_summary=summarize_mapping(outputs))

    def _deliver_outputs(self, edge: EdgeSpec, outputs: Mapping[str, object], state: _RuntimeState) -> None:
        source = self._frames[edge.source]
        target = self._frames[edge.target]
        providers_by_key = {provider.key: provider for provider in source.provides}
        required_types = {requirement.type for requirement in target.requires}
        for key, value in outputs.items():
            provider = providers_by_key.get(str(key))
            if provider is None:
                continue
            envelope = DataEnvelope(key=provider.key, type=provider.type, value=value, source_node=source.name)
            self._record_pipeline_output_candidate(envelope, state)
            if provider.type in required_types:
                state.inboxes[target.name] = [
                    item
                    for item in state.inboxes[target.name]
                    if (item.key, item.type, item.source_node) != (envelope.key, envelope.type, envelope.source_node)
                ]
                state.inboxes[target.name].append(envelope)

    def _record_pipeline_output_candidate(self, envelope: DataEnvelope, state: _RuntimeState) -> None:
        if any(output.type == envelope.type for output in self.graph.outputs):
            candidates = state.output_candidates[envelope.type]
            identity = (envelope.key, envelope.type, envelope.source_node)
            for index, item in enumerate(candidates):
                if (item.key, item.type, item.source_node) == identity:
                    candidates[index] = envelope
                    break
            else:
                candidates.append(envelope)

    def _finalize_pipeline_outputs(self, state: _RuntimeState) -> None:
        for output in self.graph.outputs:
            matches = list(state.output_candidates.get(output.type, ()))
            if output.cardinality == CARDINALITY_EXACTLY_ONE:
                if len(matches) != 1:
                    raise PipelineRuntimeError(f"pipeline output type '{output.type}' expected exactly one value, got {len(matches)}")
                _store_output(state.result, output.type, matches[0])
            elif output.cardinality == CARDINALITY_OPTIONAL_ONE:
                if len(matches) > 1:
                    raise PipelineRuntimeError(f"pipeline output type '{output.type}' expected at most one value, got {len(matches)}")
                if matches:
                    _store_output(state.result, output.type, matches[0])
            elif output.cardinality == CARDINALITY_ALL:
                state.result.set(output.type, [match.to_input() for match in matches])

    def _abandon_async_results(self) -> None:
        if not self._async_results:
            return
        self._abandoned_async_results = True
        for node_name, (frame, future) in tuple(self._async_results.items()):
            cancelled = future.cancel()
            self._record_runtime_event(
                "async_result_abandoned",
                frame.name,
                frame.node_type,
                output_summary={node_name: {"type": "future", "status": "abandoned", "cancelled": cancelled}},
            )
        self._async_results = {}

    def _flush_detached(self) -> None:
        timeout = self.runtime_options.async_flush_timeout
        for frame, future in self._detached:
            try:
                outputs = self._unwrap_async_outputs(frame, future.result(timeout=timeout))
            except TimeoutError:
                self._detached_timeout = True
                self._record_runtime_event("async_detached_timeout", frame.name, frame.node_type, failure="async detached flush timed out")
                continue
            except _NestedRuntimeFailure as exc:
                self._merge_child_trace(frame, exc.child_trace)
                self._record_runtime_event("async_detached_failed", frame.name, frame.node_type, failure=str(exc))
                continue
            except Exception as exc:
                self._record_runtime_event("async_detached_failed", frame.name, frame.node_type, failure=str(exc))
                continue
            self._record_runtime_event("async_detached_done", frame.name, frame.node_type, output_summary=summarize_mapping(outputs))
        self._detached = []

    def _shutdown_executor(self) -> None:
        if self._executor is not None:
            nonblocking = self._detached_timeout or self._abandoned_async_results
            self._executor.shutdown(wait=not nonblocking, cancel_futures=nonblocking)
            self._executor = None

    def _record_edge(self, edge: EdgeSpec) -> None:
        self.trace.record_edge(edge.source, edge.target)

    def _activate_edge(self, edge: EdgeSpec, state: _RuntimeState) -> None:
        state.active_edges.add(edge.pair)
        self._record_edge(edge)

    def _clear_conditional_outgoing(self, node_name: str, state: _RuntimeState) -> None:
        for edge in self._frames[node_name].outgoing:
            if edge.when:
                state.active_edges.discard(edge.pair)

    def _mark_node_run(self, node_name: str) -> None:
        self._node_runs[node_name] = self._node_runs.get(node_name, 0) + 1
        self.trace.record_node_run(node_name, self._node_runs[node_name])

    def _write_trace(self, result: RunResult) -> None:
        payload = self.trace.to_dict()
        result.set("runtime.exec_order", payload["exec_order"])
        result.set("runtime.edge_executions", payload["edge_executions"])
        result.set("runtime.step_count", payload["step_count"])
        result.set("runtime.node_runs", payload["node_runs"])
        result.set("runtime.qualified_exec_order", payload["qualified_exec_order"])
        result.set("runtime.qualified_edge_executions", payload["qualified_edge_executions"])
        result.set("runtime.qualified_node_runs", payload["qualified_node_runs"])
        result.set("runtime.total_step_count", payload["total_step_count"])
        result.set("runtime.stop_reason", payload["stop_reason"])
        result.set("runtime.current_node", payload["current_node"])
        result.set("runtime.exception", payload["exception"])
        result.set("runtime.events", payload["events"])

    def _call_runtime_plugins(self, hook: str, *args) -> None:
        methods = self._hook_plan.for_hook(hook)
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
        details: Mapping[str, object] | None = None,
    ) -> None:
        if self.runtime_options.trace == "off":
            return
        if self.runtime_options.trace == "boundary" and kind not in {"run_start", "run_end", "nodeset_enter", "nodeset_exit", "nodeset_failed", "node_failed", "planned_stub", "async_result_abandoned", "async_detached_failed", "async_detached_timeout", "block_enter", "block_exit", "block_failed", "type_resolve"}:
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
        if details is not None:
            event["details"] = dict(details)
        self.trace.add_event(event, (node_name,))

    def _record_run_boundary(self, kind: str) -> None:
        if self.runtime_options.trace == "boundary":
            self._record_runtime_event(kind, "pipeline", "pipeline")

    def _merge_child_trace(self, frame: NodeFrame, child_trace: RuntimeTrace) -> None:
        self.trace.merge_child((frame.name,), child_trace)

    def _unwrap_async_outputs(self, frame: NodeFrame, value: object) -> Mapping[str, object]:
        if isinstance(value, _AsyncOutputs):
            if value.child_trace is not None:
                self._merge_child_trace(frame, value.child_trace)
            return value.outputs
        if isinstance(value, Mapping):
            return value
        raise PipelineRuntimeError(f"async node '{frame.name}' returned non-mapping outputs")


def _store_output(result: RunResult, result_key: str, envelope: DataEnvelope) -> None:
    result.set(result_key, envelope.to_input())


def _inputs_to_initial(inputs: Mapping[str, object]) -> dict[str, object]:
    initial: dict[str, object] = {}
    for value in inputs.values():
        if isinstance(value, list):
            for item in value:
                _copy_input_item(item, initial)
        else:
            _copy_input_item(value, initial)
    return initial


def _nodeset_inputs_to_initial(inputs: Mapping[str, object], graph_inputs: tuple[DataProvider, ...]) -> dict[str, object]:
    initial: dict[str, object] = {}
    input_items = list(_iter_input_items(inputs))
    for provider in graph_inputs:
        for item in input_items:
            if isinstance(item, Mapping) and item.get("type") == provider.type:
                initial[provider.key] = item.get("value")
                break
    return initial


def _iter_input_items(inputs: Mapping[str, object]):
    for value in inputs.values():
        if isinstance(value, list):
            yield from value
        else:
            yield value


def _copy_input_item(item: object, initial: dict[str, object]) -> None:
    if isinstance(item, Mapping) and "key" in item:
        initial[str(item["key"])] = item.get("value")


def _result_value(item: object) -> object:
    if isinstance(item, Mapping) and {"key", "type", "value", "source_node"} <= set(item):
        return item.get("value")
    return item
