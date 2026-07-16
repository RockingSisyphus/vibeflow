from __future__ import annotations

import time
from typing import Mapping

from vibeflow.runtime.block_compiler import graph_block, nodeset_block
from vibeflow.runtime.errors import DelegateCliExit, PipelineRuntimeError
from vibeflow.runtime.helpers import elapsed_ms
from vibeflow.runtime.trace import RuntimeTrace
from vibeflow.runtime.types import _NestedRuntimeFailure
from vibeflow.runtime.values import _nodeset_inputs_to_initial, _result_value
from vibeflow.runtime.summaries import summarize_mapping

class RuntimeNodesetMixin:
    def _run_nodeset_block_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        block = nodeset_block(self._plan, frame.name)
        if block is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' is not block compiled")
        started = time.perf_counter()
        self._record_runtime_event("nodeset_enter", frame.name, frame.node_type)
        self._call_runtime_plugins("before_nodeset", frame.name, frame.node_type)
        try:
            result = block.callable(self, inputs)
            outputs = self._validate_outputs(frame, result.outputs, subject="nodeset node")
            self._mark_node_run(frame.name)
            self._record_runtime_event("nodeset_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("after_nodeset", frame.name, frame.node_type)
            return outputs
        except Exception as exc:
            self._record_runtime_event("nodeset_failed", frame.name, frame.node_type, failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("nodeset_failed", frame.name, frame.node_type, str(exc))
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
        runtime = self._nodeset_runtime(frame) if cached else type(self)._from_plan(self, frame.subplan)
        initial = _nodeset_inputs_to_initial(inputs, frame.subplan.graph.inputs)
        previous_sink = runtime._trace_sink
        previous_prefix = runtime._trace_path_prefix
        runtime._trace_sink = self._trace_sink
        runtime._trace_path_prefix = self._trace_event_path((frame.name,))
        try:
            nested_result = runtime.run(initial)
        except DelegateCliExit:
            self._merge_child_trace(frame, runtime.trace)
            raise
        except Exception as exc:
            raise _NestedRuntimeFailure(str(exc), runtime.trace) from exc
        finally:
            runtime._trace_sink = previous_sink
            runtime._trace_path_prefix = previous_prefix
        outputs = {}
        for provider in frame.provides:
            try:
                nested_value = nested_result.get(provider.type)
            except KeyError as exc:
                raise PipelineRuntimeError(
                    f"nodeset instance '{frame.id}' provides type '{provider.type}' "
                    f"for key '{provider.key}', but the nodeset body did not produce it"
                ) from exc
            outputs[provider.key] = _result_value(nested_value)
        return outputs, runtime.trace

    def _execute_nodeset_block(self, node_name: str, inputs: object) -> Mapping[str, object]:
        frame = self._frames[node_name]
        if not isinstance(inputs, Mapping):
            raise PipelineRuntimeError(f"nodeset block '{node_name}' received non-mapping inputs")
        if frame.subplan is None or graph_block(frame.subplan) is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.name}' body is not graph compiled")
        return self._run_nodeset_outputs(frame, inputs, cached=True)

    def _nodeset_runtime(self, frame: NodeFrame) -> "PipelineRuntime":
        runtime = self._nodeset_runtimes.get(frame.name)
        if runtime is None:
            if frame.subplan is None:
                raise PipelineRuntimeError(f"nodeset node '{frame.name}' has no execution plan")
            runtime = type(self)._from_plan(self, frame.subplan)
            self._nodeset_runtimes[frame.name] = runtime
        return runtime
