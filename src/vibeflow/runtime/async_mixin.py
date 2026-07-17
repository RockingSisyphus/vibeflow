from __future__ import annotations

from concurrent.futures import TimeoutError, ThreadPoolExecutor
from contextvars import copy_context
from typing import Mapping

from vibeflow.runtime.errors import DelegateCliExit, PipelineRuntimeError, normalize_delegate_cli_system_exit
from vibeflow.runtime.types import _AsyncOutputs, _NestedRuntimeFailure, _RuntimeState
from vibeflow.runtime.summaries import summarize_mapping

class RuntimeAsyncMixin:
    def _run_async_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.async_mode == "result_key" and frame.result_key not in frame.provide_keys:
            raise PipelineRuntimeError(f"async node '{frame.name}' result_key must be declared in provides")
        self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
        context = copy_context()
        future = self._executor_for_async().submit(context.run, self._execute_async_outputs, frame, inputs)
        self._mark_node_run(frame.name)
        if frame.async_mode == "detached":
            self._detached.append((frame, future))
            self._record_runtime_event("async_detached", frame.name, frame.node_type, input_summary=summarize_mapping(inputs))
            return {}
        self._async_results[frame.name] = (frame, future)
        self._record_runtime_event("async_result", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), output_summary={frame.result_key: {"type": "future"}})
        return {}

    def _execute_async_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        try:
            if frame.is_planned_stub:
                return self._execute_planned_stub_outputs(frame, inputs)
            if frame.is_nodeset:
                outputs, child_trace = self._run_nodeset_outputs_with_trace(frame, inputs, cached=False)
                return _AsyncOutputs(outputs=outputs, child_trace=child_trace)
            return self._execute_pure_outputs(frame, inputs)
        except SystemExit as exc:
            if not self.delegate_cli:
                raise PipelineRuntimeError(
                    f"node '{frame.name}' attempted SystemExit outside delegate CLI mode"
                ) from exc
            if frame.is_planned_stub or frame.flow_kind not in {"io", "document", "data_store"}:
                subject = "planned python_stub node" if frame.is_planned_stub else "node"
                raise PipelineRuntimeError(
                    f"{subject} '{frame.name}' with flow_kind '{frame.flow_kind}' cannot control delegate CLI exit"
                ) from exc
            raise normalize_delegate_cli_system_exit(exc, source=frame.name) from exc

    def _executor_for_async(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.runtime_options.async_max_workers)
        return self._executor

    def _join_async_incoming(self, node_name: str, state: _RuntimeState) -> None:
        if self.delegate_cli:
            business_exits: list[DelegateCliExit] = []
            failures: list[Exception] = []
            for edge in self._frames[node_name].incoming:
                if edge.source not in self._async_results:
                    continue
                try:
                    self._join_async_source(edge.source, state)
                except DelegateCliExit as exc:
                    business_exits.append(exc)
                except Exception as exc:
                    failures.append(exc)
            self._raise_delegate_async_outcomes(
                business_exits,
                failures,
                subject="parallel async result",
            )
            return
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
        active_edges = self._activated_edges(frame.name, outputs, state)
        active_pairs = {edge.pair for edge in active_edges}
        for edge in active_edges:
            self._activate_edge(edge, state)
            self._deliver_outputs(edge, outputs, state)
        self._deliver_transfer_only_edges(frame.name, outputs, state, active_pairs)
        self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
        self._record_runtime_event("async_result_join", frame.name, frame.node_type, output_summary=summarize_mapping(outputs))

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

    def _drain_async_results_for_delegate(self, *, exit_in_progress: bool) -> None:
        pending = tuple(self._async_results.items())
        self._async_results = {}
        business_exits: list[DelegateCliExit] = []
        failures: list[Exception] = []
        for node_name, (frame, future) in pending:
            try:
                outputs = self._unwrap_async_outputs(frame, future.result(timeout=self.runtime_options.async_flush_timeout))
            except TimeoutError:
                self._abandoned_async_results = True
                self._record_runtime_event(
                    "async_result_abandoned",
                    frame.name,
                    frame.node_type,
                    output_summary={node_name: {"type": "future", "status": "timeout", "cancelled": future.cancel()}},
                )
                failures.append(PipelineRuntimeError(f"delegate CLI async node '{frame.name}' timed out during exit"))
            except DelegateCliExit as exc:
                business_exits.append(exc)
            except _NestedRuntimeFailure as exc:
                self._merge_child_trace(frame, exc.child_trace)
                failures.append(
                    exc.__cause__
                    if isinstance(exc.__cause__, Exception)
                    else PipelineRuntimeError(f"delegate CLI async node '{frame.name}' failed: {exc}")
                )
            except Exception as exc:
                failures.append(exc)
            else:
                self._record_runtime_event(
                    "async_result_abandoned",
                    frame.name,
                    frame.node_type,
                    output_summary={
                        node_name: {
                            "type": "future",
                            "status": "completed_after_exit",
                            "outputs": summarize_mapping(outputs),
                        }
                    },
                )
        self._raise_delegate_async_outcomes(
            business_exits,
            failures,
            exit_in_progress=exit_in_progress,
            subject="parallel async result",
        )

    def _settle_async_for_delegate_exit(self) -> None:
        failures: list[Exception] = []
        try:
            self._drain_async_results_for_delegate(exit_in_progress=True)
        except Exception as exc:
            failures.append(exc)
        try:
            self._flush_detached(exit_in_progress=True)
        except Exception as exc:
            failures.append(exc)
        if failures:
            raise failures[0]

    def _flush_detached(self, *, exit_in_progress: bool = False) -> None:
        timeout = self.runtime_options.async_flush_timeout
        pending = self._detached
        self._detached = []
        business_exits: list[DelegateCliExit] = []
        failures: list[Exception] = []
        for frame, future in pending:
            try:
                outputs = self._unwrap_async_outputs(frame, future.result(timeout=timeout))
            except TimeoutError:
                self._detached_timeout = True
                self._record_runtime_event("async_detached_timeout", frame.name, frame.node_type, failure="async detached flush timed out")
                if self.delegate_cli:
                    failures.append(PipelineRuntimeError(f"delegate CLI detached node '{frame.name}' timed out"))
                continue
            except DelegateCliExit as exc:
                business_exits.append(exc)
                continue
            except _NestedRuntimeFailure as exc:
                self._merge_child_trace(frame, exc.child_trace)
                self._record_runtime_event("async_detached_failed", frame.name, frame.node_type, failure=str(exc))
                if self.delegate_cli:
                    if exc.__cause__ is not None:
                        failures.append(exc.__cause__)
                    else:
                        failures.append(PipelineRuntimeError(f"delegate CLI detached node '{frame.name}' failed: {exc}"))
                continue
            except Exception as exc:
                self._record_runtime_event("async_detached_failed", frame.name, frame.node_type, failure=str(exc))
                if self.delegate_cli:
                    failures.append(exc)
                continue
            self._record_runtime_event("async_detached_done", frame.name, frame.node_type, output_summary=summarize_mapping(outputs))
        self._raise_delegate_async_outcomes(
            business_exits,
            failures,
            exit_in_progress=exit_in_progress,
            subject="detached node",
        )

    @staticmethod
    def _raise_delegate_async_outcomes(
        business_exits: list[DelegateCliExit],
        failures: list[Exception],
        *,
        exit_in_progress: bool = False,
        subject: str,
    ) -> None:
        if failures:
            raise failures[0]
        if business_exits and exit_in_progress:
            raise PipelineRuntimeError(f"delegate CLI {subject} cannot replace an exit already in progress")
        if len(business_exits) > 1:
            raise PipelineRuntimeError(f"delegate CLI {subject}s produced multiple business exits")
        if business_exits:
            raise business_exits[0]

    def _shutdown_executor(self) -> None:
        if self._executor is not None:
            nonblocking = self._detached_timeout or self._abandoned_async_results
            self._executor.shutdown(wait=not nonblocking, cancel_futures=nonblocking)
            self._executor = None

    def _unwrap_async_outputs(self, frame: NodeFrame, value: object) -> Mapping[str, object]:
        if isinstance(value, _AsyncOutputs):
            if value.child_trace is not None:
                self._merge_child_trace(frame, value.child_trace)
            return value.outputs
        if isinstance(value, Mapping):
            return value
        raise PipelineRuntimeError(f"async node '{frame.name}' returned non-mapping outputs")
