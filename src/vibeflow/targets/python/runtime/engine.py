from __future__ import annotations

import time
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

from vibeflow.targets.python.runtime.loop_mixin import RuntimeLoopMixin
from vibeflow.targets.python.runtime.node_mixin import RuntimeNodeMixin
from vibeflow.targets.python.runtime.nodeset_mixin import RuntimeNodesetMixin
from vibeflow.targets.python.runtime.output_mixin import RuntimeOutputMixin
from vibeflow.targets.python.runtime.trace_mixin import RuntimeTraceMixin
from vibeflow.targets.python.runtime.execution_lock_mixin import RuntimeExecutionLockMixin
from vibeflow.targets.python.runtime.support.contract_mixin import RuntimeContractMixin
from vibeflow.targets.python.runtime.types import _RuntimeState
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from vibeflow.targets.python.runtime.observation import observe_run


class PipelineRuntime(RuntimeContractMixin, RuntimeLoopMixin, RuntimeNodeMixin, RuntimeNodesetMixin, RuntimeOutputMixin, RuntimeTraceMixin, RuntimeExecutionLockMixin):
    def __init__(
        self,
        graph: GraphConfig,
        *,
        registry: NodeRegistry,
        plugin_registry: PluginRegistry | None = None,
        run_dir: str | Path | None = None,
        node_config_overrides: Mapping[str, Mapping[str, object]] | None = None,
        global_config: Mapping[str, Any] | None = None,
        runtime_options: RuntimeOptions | Mapping[str, object] | None = None,
        delegate_cli: bool = False,
        capabilities: Mapping[str, object] | None = None,
        _execution_plan: ExecutionPlan | None = None,
    ) -> None:
        self.runtime_options = normalize_runtime_options(runtime_options)
        self.delegate_cli = bool(delegate_cli)
        self._assert_planned_runtime_allowed(graph)
        self.registry = registry
        self._plugin_registry = plugin_registry
        self._runtime_plugins = plugin_registry.runtime_plugins() if plugin_registry is not None else ()
        self._hook_plan = runtime_hook_plan(self._runtime_plugins, self.runtime_options)
        from vibeflow.targets.python.project.check_session import current_python_check
        session = current_python_check(registry)
        compilation = session.checked_compilation(graph) if session is not None else None
        if compilation is None and _execution_plan is None:
            compilation = GraphCompiler().compile_with_findings(
                graph,
                registry=registry,
                plugin_registry=plugin_registry,
            )
        graph = _execution_plan.graph if _execution_plan is not None else compilation.workflow.graph
        self.graph = graph
        self.compiled = _execution_plan.compiled if _execution_plan is not None else compilation.compiled_graph
        self._plan = _execution_plan if _execution_plan is not None else build_execution_plan(
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
        self._run_dir = Path(run_dir) if run_dir is not None else Path("runs") / "vibeflow"
        self._trace_sink: RuntimeTraceSink | None = None
        self._trace_path_prefix: tuple[str, ...] = ()
        self._capabilities = dict(capabilities or {})
        from .lifecycle import CancellationSignal
        self._signal = CancellationSignal()
        self._owns_run = True
        self._has_run = False
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
        runtime._run_dir = parent._run_dir
        runtime._trace_sink = parent._trace_sink
        runtime._trace_path_prefix = parent._trace_path_prefix
        runtime.runtime_options = parent.runtime_options
        runtime.delegate_cli = parent.delegate_cli
        runtime._capabilities = parent._capabilities
        runtime._signal = parent._signal
        runtime._owns_run = False
        runtime._reset_execution_lock_state()
        return runtime

    def request_stop(self, reason=None):
        """Request cooperative cancellation; run() returns only after actual cleanup."""
        self._signal.request_stop(reason)

    def run(self, initial: Mapping[str, Any] | None = None) -> RunResult:
        factory = getattr(self, "_runtime_plugin_factory", None)
        if factory is None or not self._owns_run:
            return self._run_with_observation(initial)
        from vibeflow.targets.python.sdk.loading import source_paths
        from vibeflow.targets.python.project.plugins import plugin_lifetime
        with source_paths(self._bundle_source_roots), observe_run(self._run_dir, self.runtime_options):
            plugins = factory()
            self._plugin_registry = plugins
            with plugin_lifetime(plugins):
                initialize = getattr(self, "_runtime_plan_factory", None)
                if initialize is not None:
                    self._plan = initialize(plugins)
                    self._frames = self._plan.frames
                    self._runtime_plan_factory = None
                else:
                    from dataclasses import replace
                    self._plan = replace(self._plan,python_bindings=replace(self._plan.python_bindings,plugin_registry=plugins))
                self._runtime_plugins = plugins.runtime_plugins()
                self._hook_plan = runtime_hook_plan(self._runtime_plugins, self.runtime_options)
                return self._run_with_observation(initial)

    def _run_with_observation(self, initial: Mapping[str, Any] | None = None) -> RunResult:
        if not self._owns_run:
            return self._run_observed(initial)
        if self._has_run:
            from .lifecycle import CancellationSignal
            self._signal = CancellationSignal()
        self._has_run = True
        with observe_run(self._run_dir, self.runtime_options) as observer:
            observer.configure(self.runtime_options)
            observer.transition("running")
            unsubscribe = self._signal.subscribe(lambda reason: observer.transition("stopping"))
            try:
                return self._run_observed(initial)
            finally:
                unsubscribe()

    def _run_observed(self, initial: Mapping[str, Any] | None = None) -> RunResult:
        owns_trace_sink = self._trace_sink is None
        if owns_trace_sink:
            self._trace_path_prefix = ()
            self._trace_sink = RuntimeTraceSink(self._trace_file_path())
            self._trace_sink.open()
        self._reset_run_state()
        initial_values = initial or {}
        state = self._new_state(initial_values)
        lease_started = False
        primary_error = None
        try:
            self._begin_execution_lease()
            lease_started = True
            self._validate_public_inputs(initial_values)
            self._record_run_boundary("run_start")
            if self._owns_run:
                self._call_runtime_plugins("before_run", dict(initial_values))
            if self.runtime_options.execution == "compiled":
                run_compiled_steps(self, state)
            elif self.runtime_options.execution == "block":
                self._run_block_steps(state)
            else:
                self._run_steps(state)
            self._signal.throw_if_aborted()
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._finalize_pipeline_outputs(state)
            self._record_run_boundary("run_end")
            self._write_trace(state.result)
            if self._owns_run:
                self._call_runtime_plugins("after_run", state.result.to_dict(), self.trace.to_dict())
        except DelegateCliExit as exc:
            try:
                self._signal.request_stop("business exit")
            except BaseException as cleanup:
                primary_error = cleanup
                cleanup.business_exit = {"exit_code":exc.exit_code,"source":exc.source}
                self._record_runtime_failure(state, cleanup, force_node_failed=True)
                raise
            self.trace.stop_reason = "business_exit"
            self.trace.exception = ""
            if not owns_trace_sink:
                raise
            self._record_runtime_event("business_exit", exc.source, "delegate_cli",
                                       details={"exit_code": exc.exit_code})
            state.result.set("cli.exit_code", DataEnvelope(key="cli.exit_code", type="cli.exit_code",
                value=exc.exit_code, source_node=exc.source).to_input())
            self._write_trace(state.result)
        except BaseException as exc:
            primary_error = exc
            self._signal.request_stop("workflow failed")
            self._record_runtime_failure(state, exc)
            raise
        finally:
            try:
                if self.trace.exception:
                    self._record_global_state_change_warning(self.trace.exception)
            finally:
                try:
                    if lease_started:
                        self._end_execution_lease()
                        self._write_trace(state.result)
                except BaseException as cleanup:
                    if primary_error is None:
                        raise
                    primary_error.add_note(str(cleanup))
                    primary_error.cleanup_errors = [*getattr(primary_error, "cleanup_errors", ()), cleanup]
                finally:
                    if owns_trace_sink and self._trace_sink is not None:
                        try:
                            self._trace_sink.write_summary(self.trace)
                        finally:
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
        if self._owns_run:
            try:
                self._call_runtime_plugins("run_failed", state.result.to_dict(), self.trace.to_dict(), str(exc))
            except BaseException as cleanup:
                exc.add_note(str(cleanup))
                exc.cleanup_errors = [*getattr(exc, "cleanup_errors", ()), cleanup]

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
        self._global_state_started = False
        self._global_state_nodes = []

    def _trace_file_path(self) -> Path:
        if self._trace_sink is not None:
            return self._trace_sink.path
        return self._run_dir / "runtime_trace.jsonl"

    def _run_steps(self, state: _RuntimeState) -> None:
        from .scheduler import run_graph
        run_graph(self, state)

    def _run_block_steps(self, state: _RuntimeState) -> None:
        block = graph_block(self._plan)
        if block is not None:
            block.callable(self, state)
            return
        details = _block_compile_error_details(self._plan)
        raise PipelineRuntimeError(f"block execution requires a compiled graph block: {details}")



    def _scheduled_targets(self, node_name, active_edges):
        return tuple(dict.fromkeys(edge.target for edge in active_edges))

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




def _block_compile_error_details(plan: ExecutionPlan) -> str:
    findings = [item for item in explain_block_compilation(plan) if not bool(item.get("compiled"))]
    if not findings:
        return "unknown"
    first = findings[0]
    return f"{first.get('path')}: {first.get('reason')}"


__all__ = ["PipelineRuntime"]
