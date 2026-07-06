from __future__ import annotations

from concurrent.futures import TimeoutError, ThreadPoolExecutor
from typing import Mapping

from .runtime_errors import PipelineRuntimeError
from .runtime_types import _AsyncOutputs, _NestedRuntimeFailure, _RuntimeState
from .summaries import summarize_mapping

class RuntimeAsyncMixin:
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

    def _unwrap_async_outputs(self, frame: NodeFrame, value: object) -> Mapping[str, object]:
        if isinstance(value, _AsyncOutputs):
            if value.child_trace is not None:
                self._merge_child_trace(frame, value.child_trace)
            return value.outputs
        if isinstance(value, Mapping):
            return value
        raise PipelineRuntimeError(f"async node '{frame.name}' returned non-mapping outputs")
