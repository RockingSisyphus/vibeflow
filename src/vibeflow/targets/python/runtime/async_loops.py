"""Native asynchronous loop mixin."""
from __future__ import annotations
import time
from typing import Mapping
from vibeflow.targets.python.runtime.block_compiler import graph_block, loop_block
from vibeflow.core.contracts import RunResult
from vibeflow.targets.python.runtime.errors import DelegateCliExit, PipelineRuntimeError
from vibeflow.targets.python.runtime.helpers import elapsed_ms
from vibeflow.targets.python.runtime.values import _initial_loop_values, _loop_body_initial, _loop_outputs, _loop_should_stop, _update_loop_values
from vibeflow.targets.python.runtime.summaries import summarize_mapping
from .completion import suspended

class AsyncRuntimeLoopMixin:

    async def _run_loop_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event('loop_enter', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), details=frame.loop_spec.to_dict())
        await self._call_runtime_plugins_async('before_node', frame.id, frame.definition_id, summarize_mapping(inputs))
        try:
            outputs = await self._run_loop_outputs_async(frame, inputs)
            outputs = self._validate_outputs(frame, outputs, subject='loop node')
            self._mark_node_run(frame.id)
            self._record_runtime_event('loop_exit', frame.id, frame.definition_id, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('after_node', frame.id, frame.definition_id, summarize_mapping(outputs))
            return outputs
        except Exception as exc:
            self._record_runtime_event('loop_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _run_loop_block_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        block = loop_block(self._plan, frame.id)
        if block is None:
            raise PipelineRuntimeError(f"loop node '{frame.id}' is not block compiled")
        started = time.perf_counter()
        self._record_runtime_event('loop_enter', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), details=frame.loop_spec.to_dict())
        self._record_runtime_event('loop_block_enter', frame.id, frame.definition_id, details={'block': block.name, 'body': frame.loop_spec.body})
        await self._call_runtime_plugins_async('before_node', frame.id, frame.definition_id, summarize_mapping(inputs))
        try:
            result = await suspended(block.callable(self, inputs))
            outputs = self._validate_outputs(frame, result.outputs, subject='loop node')
            self._mark_node_run(frame.id)
            self._record_runtime_event('loop_block_exit', frame.id, frame.definition_id, output_summary=summarize_mapping(outputs), details={'block': block.name})
            self._record_runtime_event('loop_exit', frame.id, frame.definition_id, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('after_node', frame.id, frame.definition_id, summarize_mapping(outputs))
            return outputs
        except Exception as exc:
            self._record_runtime_event('loop_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _run_loop_outputs_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.subplan is None:
            raise PipelineRuntimeError(f"loop node '{frame.id}' has no body execution plan")
        return await self._run_while_loop_async(frame, inputs, require_block=False)

    async def _execute_loop_block_async(self, node_name: str, inputs: object) -> Mapping[str, object]:
        frame = self._frames[node_name]
        if not isinstance(inputs, Mapping):
            raise PipelineRuntimeError(f"loop block '{node_name}' received non-mapping inputs")
        if frame.subplan is None or graph_block(frame.subplan) is None:
            raise PipelineRuntimeError(f"loop node '{frame.id}' body is not block compiled")
        return await self._run_while_loop_async(frame, inputs, require_block=True)

    async def _run_while_loop_async(self, frame: NodeFrame, inputs: Mapping[str, object], *, require_block: bool) -> Mapping[str, object]:
        spec = frame.loop_spec
        values = _initial_loop_values(inputs, spec.carry)
        runtime = self._nodeset_runtime(frame)
        iteration = 0
        while spec.max_iterations is None or iteration < spec.max_iterations:
            initial = _loop_body_initial(values, spec.carry)
            iteration_path = (frame.id, f'iter_{iteration}')
            result = await self._run_loop_body_iteration_async(frame, runtime, initial, iteration_path, iteration)
            _update_loop_values(values, result, spec.carry, spec.collect, frame.subplan.graph.outputs)
            iteration_count = iteration + 1
            values['loop.iterations'] = iteration_count
            if _loop_should_stop(frame, values, iteration_count):
                return _loop_outputs(frame, values)
            iteration += 1
        if not spec.stop_after and (not spec.stop_when.source):
            return _loop_outputs(frame, values)
        raise PipelineRuntimeError(f"loop node '{frame.id}' exceeded max_iterations={spec.max_iterations}")

    async def _run_loop_body_iteration_async(self, frame: NodeFrame, runtime: 'PipelineRuntime', initial: Mapping[str, object], iteration_path: tuple[str, ...], iteration_index: int) -> RunResult:
        if self.runtime_options.trace == 'full':
            self.trace.add_event({'kind': 'loop_iteration', 'node': frame.id, 'type': frame.definition_id, 'details': {'iteration': iteration_index, 'initial_keys': sorted((str(key) for key in initial))}}, self._trace_event_path(iteration_path), self._trace_sink)
        previous_sink = runtime._trace_sink
        previous_prefix = runtime._trace_path_prefix
        runtime._trace_sink = self._trace_sink
        runtime._trace_path_prefix = self._trace_event_path(iteration_path)
        try:
            result = await runtime.run_async(initial)
        except DelegateCliExit:
            self.trace.merge_child(iteration_path, runtime.trace)
            raise
        except Exception:
            self.trace.merge_child(iteration_path, runtime.trace)
            raise
        finally:
            runtime._trace_sink = previous_sink
            runtime._trace_path_prefix = previous_prefix
        self.trace.merge_child(iteration_path, runtime.trace)
        return result
