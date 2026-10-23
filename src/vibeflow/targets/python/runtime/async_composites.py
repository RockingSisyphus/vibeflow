"""Native asynchronous nodeset mixin."""
from __future__ import annotations
import time
from typing import Mapping
from vibeflow.targets.python.runtime.block_compiler import graph_block, nodeset_block
from vibeflow.targets.python.runtime.errors import DelegateCliExit, PipelineRuntimeError
from vibeflow.targets.python.runtime.helpers import elapsed_ms
from vibeflow.targets.python.runtime.trace import RuntimeTrace
from vibeflow.targets.python.runtime.types import _NestedRuntimeFailure
from vibeflow.targets.python.runtime.values import _nodeset_inputs_to_initial, _public_result_value
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from .completion import suspended

class AsyncRuntimeNodesetMixin:

    async def _run_nodeset_block_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        block = nodeset_block(self._plan, frame.id)
        if block is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.id}' is not block compiled")
        started = time.perf_counter()
        self._record_runtime_event('nodeset_enter', frame.id, frame.definition_id)
        await self._call_runtime_plugins_async('before_nodeset', frame.id, frame.definition_id)
        try:
            result = await suspended(block.callable(self, inputs))
            outputs = self._validate_outputs(frame, result.outputs, subject='nodeset node')
            self._mark_node_run(frame.id)
            self._record_runtime_event('nodeset_exit', frame.id, frame.definition_id, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('after_nodeset', frame.id, frame.definition_id)
            return outputs
        except Exception as exc:
            self._record_runtime_event('nodeset_failed', frame.id, frame.definition_id, failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('nodeset_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _run_nodeset_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event('nodeset_enter', frame.id, frame.definition_id)
        await self._call_runtime_plugins_async('before_nodeset', frame.id, frame.definition_id)
        try:
            outputs = await self._run_nodeset_outputs_async(frame, inputs, cached=True)
            self._mark_node_run(frame.id)
            self._record_runtime_event('nodeset_exit', frame.id, frame.definition_id, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('after_nodeset', frame.id, frame.definition_id)
            return outputs
        except Exception as exc:
            self._record_runtime_event('nodeset_failed', frame.id, frame.definition_id, failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('nodeset_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _run_nodeset_outputs_async(self, frame: NodeFrame, inputs: Mapping[str, object], *, cached: bool=False) -> Mapping[str, object]:
        try:
            outputs, child_trace = await self._run_nodeset_outputs_with_trace_async(frame, inputs, cached=cached)
        except _NestedRuntimeFailure as exc:
            self._merge_child_trace(frame, exc.child_trace)
            if exc.__cause__ is not None:
                raise exc.__cause__
            raise
        self._merge_child_trace(frame, child_trace)
        return outputs

    async def _run_nodeset_outputs_with_trace_async(self, frame: NodeFrame, inputs: Mapping[str, object], *, cached: bool=False) -> tuple[Mapping[str, object], RuntimeTrace]:
        if frame.subplan is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.id}' has no execution plan")
        runtime = self._nodeset_runtime(frame) if cached else type(self)._from_plan(self, frame.subplan)
        initial = _nodeset_inputs_to_initial(inputs, frame.subplan.graph.inputs)
        previous_sink = runtime._trace_sink
        previous_prefix = runtime._trace_path_prefix
        runtime._trace_sink = self._trace_sink
        runtime._trace_path_prefix = self._trace_event_path((frame.id,))
        try:
            nested_result = await runtime.run_async(initial)
        except DelegateCliExit:
            self._merge_child_trace(frame, runtime.trace)
            raise
        except Exception as exc:
            raise _NestedRuntimeFailure(str(exc), runtime.trace) from exc
        finally:
            runtime._trace_sink = previous_sink
            runtime._trace_path_prefix = previous_prefix
        outputs = {}
        output_specs = {output.type: output for output in frame.subplan.graph.outputs}
        for provider in frame.provides:
            output_spec = output_specs.get(provider.type)
            result_key = output_spec.public_name if output_spec is not None else provider.type
            try:
                nested_value = nested_result.get(result_key)
            except KeyError as exc:
                raise PipelineRuntimeError(f"nodeset instance '{frame.id}' provides type '{provider.type}' for key '{provider.key}', but the nodeset body did not produce it") from exc
            outputs[provider.key] = _public_result_value(nested_value)
        return (outputs, runtime.trace)

    async def _execute_nodeset_block_async(self, node_name: str, inputs: object) -> Mapping[str, object]:
        frame = self._frames[node_name]
        if not isinstance(inputs, Mapping):
            raise PipelineRuntimeError(f"nodeset block '{node_name}' received non-mapping inputs")
        if frame.subplan is None or graph_block(frame.subplan) is None:
            raise PipelineRuntimeError(f"nodeset node '{frame.id}' body is not graph compiled")
        return await self._run_nodeset_outputs_async(frame, inputs, cached=True)
