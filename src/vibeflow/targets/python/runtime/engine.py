from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping

from vibeflow.targets.python.runtime.block_compiler import explain_block_compilation, graph_block, loop_block, nodeset_block
from vibeflow.targets.python.project.compiler import GraphCompiler
from vibeflow.core.contracts import (
    CARDINALITY_EXACTLY_ONE,
    DataEnvelope,
    RunResult,
)
from vibeflow.targets.python.runtime.planning import ExecutionPlan, NodeFrame, build_execution_plan
from vibeflow.core.flow import EdgeSpec, GraphConfig, JOIN_POLICY_ALL, JOIN_POLICY_ANY_ACTIVE
from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime.compiled import run_compiled_steps
from vibeflow.targets.python.runtime.errors import DelegateCliExit, PipelineRuntimeError
from vibeflow.targets.python.runtime.helpers import condition_matches, elapsed_ms, has_planned, planned_items
from vibeflow.targets.python.runtime.options import RuntimeOptions, runtime_hook_plan, runtime_options as normalize_runtime_options
from vibeflow.targets.python.runtime.trace import RuntimeTrace, RuntimeTraceSink

from vibeflow.targets.python.runtime.async_mixin import RuntimeAsyncMixin
from vibeflow.targets.python.runtime.loop_mixin import RuntimeLoopMixin
from vibeflow.targets.python.runtime.node_mixin import RuntimeNodeMixin
from vibeflow.targets.python.runtime.nodeset_mixin import RuntimeNodesetMixin
from vibeflow.targets.python.runtime.output_mixin import RuntimeOutputMixin
from vibeflow.targets.python.runtime.trace_mixin import RuntimeTraceMixin
from vibeflow.targets.python.runtime.execution_lock_mixin import RuntimeExecutionLockMixin
from vibeflow.targets.python.runtime.support.contract_mixin import RuntimeContractMixin
from vibeflow.targets.python.runtime.types import _RuntimeState
from vibeflow.targets.python.runtime.summaries import summarize_mapping


class PipelineRuntime(RuntimeContractMixin, RuntimeLoopMixin, RuntimeNodeMixin, RuntimeNodesetMixin, RuntimeAsyncMixin, RuntimeOutputMixin, RuntimeTraceMixin, RuntimeExecutionLockMixin):
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
        delegate_cli: bool = False,
        capabilities: Mapping[str, object] | None = None,
    ) -> None:
        self.runtime_options = normalize_runtime_options(runtime_options)
        self.delegate_cli = bool(delegate_cli)
        if boundary_registry is not None:
            raise PipelineRuntimeError("boundary_registry is removed; use flowchart nodes")
        self._assert_planned_runtime_allowed(graph)
        self.registry = registry
        self._plugin_registry = plugin_registry
        self._runtime_plugins = plugin_registry.runtime_plugins() if plugin_registry is not None else ()
        self._hook_plan = runtime_hook_plan(self._runtime_plugins, self.runtime_options)
        compilation = GraphCompiler().compile_with_findings(
            graph,
            registry=registry,
            plugin_registry=plugin_registry,
        )
        graph = compilation.workflow.graph
        self.graph = graph
        self.compiled = compilation.compiled_graph
        self._plan = build_execution_plan(
            graph,
            self.compiled,
            registry=registry,
            node_config_overrides=node_config_overrides,
            global_config=global_config,
            runtime_options=self.runtime_options,
            plugin_registry=plugin_registry,
            _contracts_resolved=True,
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
        self._capabilities = dict(capabilities or {})
        self._reset_execution_lock_state()

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
        runtime.delegate_cli = parent.delegate_cli
        runtime._capabilities = parent._capabilities
        runtime._reset_execution_lock_state()
        return runtime

    def run(self, initial: Mapping[str, Any] | None = None) -> RunResult:
        owns_trace_sink = self._trace_sink is None
        if owns_trace_sink:
            self._trace_path_prefix = ()
            self._trace_sink = RuntimeTraceSink(self._trace_file_path())
            self._trace_sink.open()
        self._reset_run_state()
        initial_values = initial or {}
        state = self._new_state(initial_values)
        lease_started = False
        try:
            self._begin_execution_lease()
            lease_started = True
            self._validate_public_inputs(initial_values)
            self._record_run_boundary("run_start")
            self._call_runtime_plugins("before_run", dict(initial_values))
            if self.runtime_options.execution == "compiled":
                run_compiled_steps(self, state)
            elif self.runtime_options.execution == "block":
                self._run_block_steps(state)
            else:
                self._run_steps(state)
            if self.delegate_cli:
                self._drain_async_results_for_delegate(exit_in_progress=False)
            else:
                self._abandon_async_results()
            self._flush_detached()
            # A protected result must have been consumed through its declared
            # join before a successful root can publish outputs or success
            # hooks. This also closes conservative static-analysis gaps such
            # as an early terminal path abandoning a result task.
            self._drain_protected_tasks(fail_on_unjoined=True)
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._finalize_pipeline_outputs(state)
            self._record_run_boundary("run_end")
            self._write_trace(state.result)
            self._call_runtime_plugins("after_run", state.result.to_dict(), self.trace.to_dict())
        except DelegateCliExit as exc:
            try:
                self._settle_async_for_delegate_exit()
            except Exception as pending_exc:
                self._record_runtime_failure(state, pending_exc, force_node_failed=True)
                raise
            if not owns_trace_sink:
                self.trace.stop_reason = "business_exit"
                self.trace.exception = ""
                raise
            self.trace.stop_reason = "business_exit"
            self.trace.exception = ""
            self._record_runtime_event(
                "business_exit",
                exc.source,
                "delegate_cli",
                details={"exit_code": exc.exit_code},
            )
            state.result.set(
                "cli.exit_code",
                DataEnvelope(
                    key="cli.exit_code",
                    type="cli.exit_code",
                    value=exc.exit_code,
                    source_node=exc.source,
                ).to_input(),
            )
            self._write_trace(state.result)
        except BaseException as exc:
            self._abandon_async_results()
            try:
                self._flush_detached(exit_in_progress=True)
            except BaseException:
                # The original framework failure remains authoritative. Detached
                # failures are already represented by their runtime events, and
                # a later business exit must never replace the original error.
                pass
            self._record_runtime_failure(state, exc)
            raise
        finally:
            root_scope_protected = self._execution_scope_is_protected()
            has_protected_futures = bool(self._protected_futures)
            try:
                if has_protected_futures:
                    self._drain_protected_tasks()
            finally:
                try:
                    self._shutdown_executor(
                        force_wait=root_scope_protected
                    )
                finally:
                    try:
                        try:
                            # A protected worker can begin after the main scheduler
                            # has already entered failure handling. Re-check only
                            # after every managed task is drained, while the lease is
                            # still held, so that late ambient-state changes are not
                            # silently omitted from the trace.
                            if self.trace.exception:
                                self._record_global_state_change_warning(
                                    self.trace.exception
                                )
                        finally:
                            # Observability is not allowed to own the lock
                            # lifecycle. Even if recording the state-change warning
                            # fails, every acquired domain and its ContextVars must
                            # still be released/reset before this run can escape.
                            if lease_started:
                                self._end_execution_lease()
                                # The release event is part of the public runtime trace.
                                # Refresh the returned trace metadata only after the
                                # lease has actually been released so event_count and
                                # streamed events describe the same completed run.
                                self._write_trace(state.result)
                    finally:
                        if owns_trace_sink and self._trace_sink is not None:
                            self._trace_sink.write_summary(self.trace)
                            self._trace_sink.close()
                            self._trace_sink = None
        return state.result

    def _record_runtime_failure(
        self,
        state: _RuntimeState,
        exc: BaseException,
        *,
        force_node_failed: bool = False,
    ) -> None:
        if force_node_failed:
            self.trace.stop_reason = "node_failed"
        else:
            self.trace.stop_reason = self.trace.stop_reason or "node_failed"
        self.trace.exception = str(exc)
        self._record_global_state_change_warning(str(exc))
        self._write_trace(state.result)
        self._call_runtime_plugins("run_failed", state.result.to_dict(), self.trace.to_dict(), str(exc))

    def _record_global_state_change_warning(self, failure: str) -> None:
        lease = self._lease
        changed_nodes = (
            list(lease.global_state_nodes)
            if lease is not None
            else list(self._global_state_nodes)
        )
        if changed_nodes and (
            lease is None or not lease.state_change_reported
        ):
            self._record_runtime_event(
                "global_state_may_have_changed",
                (
                    self._global_state_nodes[-1]
                    if self._global_state_nodes
                    else changed_nodes[-1]
                ),
                "global_state",
                failure=failure,
                details={
                    **self._lease_details(),
                    "nodes": changed_nodes,
                },
            )
            if lease is not None:
                lease.state_change_reported = True

    def _reset_run_state(self) -> None:
        self.trace = RuntimeTrace(trace_path=str(self._trace_file_path()))
        self._node_runs = {name: 0 for name in self._plan.order}
        self._async_results = {}
        self._detached = []
        self._detached_timeout = False
        self._abandoned_async_results = False
        self._protected_futures = []
        self._global_state_started = False
        self._global_state_nodes = []

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
            self._clear_conditional_outgoing(node_name, state)
            active_edges = self._activated_edges(node_name, outputs, state)
            active_pairs = {edge.pair for edge in active_edges}
            for edge in active_edges:
                self._activate_edge(edge, state)
                self._deliver_outputs(edge, outputs, state)
            for target in self._scheduled_targets(node_name, active_edges):
                if target not in queued:
                    ready.append(target)
                    queued.add(target)
            self._deliver_transfer_only_edges(node_name, outputs, state, active_pairs)
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
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
                self._clear_conditional_outgoing(node_name, state)
                active = self._activated_edges(node_name, outputs, state)
                active_pairs = {edge.pair for edge in active}
                for edge in active:
                    self._activate_edge(edge, state)
                    self._deliver_outputs(edge, outputs, state)
                self._deliver_transfer_only_edges(node_name, outputs, state, active_pairs)
                if self._is_end_terminal(node_name):
                    self.trace.stop_reason = "completed"
                    self._record_runtime_event("block_exit", block_name, "block", output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
                    self._call_runtime_plugins("after_block", block_name, block_nodes)
                    return last_node, outputs
                if len(active) != 1:
                    raise PipelineRuntimeError(f"block execution requires exactly one active edge from '{node_name}'")
                edge = active[0]
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
            return any(edge.pair in state.active_edges for edge in frame.incoming)
        conditional_edges = [edge for edge in frame.incoming if edge.when]
        if conditional_edges and len(conditional_edges) == len(frame.incoming):
            return any(edge.pair in state.active_edges for edge in conditional_edges)
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
        # A result-key task has only been scheduled at this point; its
        # outgoing routes become active when ``_join_async_source`` resolves
        # the task and supplies the real outputs.  Activating unconditional
        # routes here records them twice and exposes a route before its result
        # exists.
        if node_name in self._async_results:
            return ()
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
            outputs = self._run_async_node(frame, inputs)
        else:
            with self._frame_execution_scope(frame):
                if frame.is_io:
                    outputs = self._run_io_node(frame, inputs)
                elif frame.is_planned_stub:
                    outputs = self._run_planned_stub_node(frame, inputs)
                elif frame.is_loop:
                    if self.runtime_options.execution == "block":
                        outputs = self._run_loop_block_node(frame, inputs)
                    elif self.runtime_options.execution == "compiled" and loop_block(self._plan, frame.name) is not None:
                        outputs = self._run_loop_block_node(frame, inputs)
                    else:
                        outputs = self._run_loop_node(frame, inputs)
                elif frame.is_nodeset:
                    if self.runtime_options.execution == "compiled" and nodeset_block(self._plan, frame.name) is not None:
                        outputs = self._run_nodeset_block_node(frame, inputs)
                    else:
                        outputs = self._run_nodeset_node(frame, inputs)
                else:
                    outputs = self._run_pure_node(frame, inputs)
        self._record_node_output_candidates(node_name, outputs, state)
        return outputs

def _block_compile_error_details(plan: ExecutionPlan) -> str:
    findings = [item for item in explain_block_compilation(plan) if not bool(item.get("compiled"))]
    if not findings:
        return "unknown"
    first = findings[0]
    return f"{first.get('path')}: {first.get('reason')}"


__all__ = ["PipelineRuntime"]
