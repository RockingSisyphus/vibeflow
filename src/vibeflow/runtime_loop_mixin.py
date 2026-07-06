from __future__ import annotations

import time
from typing import Mapping

from .block_compiler import graph_block, loop_block
from .data_contract import RunResult
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import elapsed_ms
from .runtime_values import (
    _initial_loop_values,
    _loop_body_initial,
    _loop_outputs,
    _loop_should_stop,
    _update_loop_values,
)
from .summaries import summarize_mapping

class RuntimeLoopMixin:
    def _run_loop_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event("loop_enter", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), details=frame.loop_spec.to_dict())
        self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
        try:
            outputs = self._run_loop_outputs(frame, inputs)
            outputs = self._validate_outputs(frame, outputs, subject="loop node")
            self._mark_node_run(frame.name)
            self._record_runtime_event("loop_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
            return outputs
        except Exception as exc:
            self._record_runtime_event("loop_failed", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            raise

    def _run_loop_block_node(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        block = loop_block(self._plan, frame.name)
        if block is None:
            raise PipelineRuntimeError(f"loop node '{frame.name}' is not block compiled")
        started = time.perf_counter()
        self._record_runtime_event("loop_enter", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), details=frame.loop_spec.to_dict())
        self._record_runtime_event("loop_block_enter", frame.name, frame.node_type, details={"block": block.name, "body": frame.loop_spec.body})
        self._call_runtime_plugins("before_node", frame.name, frame.node_type, summarize_mapping(inputs))
        try:
            result = block.callable(self, inputs)
            outputs = self._validate_outputs(frame, result.outputs, subject="loop node")
            self._mark_node_run(frame.name)
            self._record_runtime_event("loop_block_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), details={"block": block.name})
            self._record_runtime_event("loop_exit", frame.name, frame.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("after_node", frame.name, frame.node_type, summarize_mapping(outputs))
            return outputs
        except Exception as exc:
            self._record_runtime_event("loop_failed", frame.name, frame.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(exc))
            raise

    def _run_loop_outputs(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        if frame.subplan is None:
            raise PipelineRuntimeError(f"loop node '{frame.name}' has no body execution plan")
        return self._run_while_loop(frame, inputs, require_block=False)

    def _execute_loop_block(self, node_name: str, inputs: object) -> Mapping[str, object]:
        frame = self._frames[node_name]
        if not isinstance(inputs, Mapping):
            raise PipelineRuntimeError(f"loop block '{node_name}' received non-mapping inputs")
        if frame.subplan is None or graph_block(frame.subplan) is None:
            raise PipelineRuntimeError(f"loop node '{frame.name}' body is not block compiled")
        return self._run_while_loop(frame, inputs, require_block=True)

    def _run_while_loop(self, frame: NodeFrame, inputs: Mapping[str, object], *, require_block: bool) -> Mapping[str, object]:
        spec = frame.loop_spec
        values = _initial_loop_values(inputs, spec.carry)
        runtime = self._nodeset_runtime(frame)
        for iteration in range(spec.max_iterations):
            initial = _loop_body_initial(values, spec.carry)
            iteration_path = (frame.name, f"iter_{iteration}")
            result = self._run_loop_body_iteration(frame, runtime, initial, iteration_path, iteration)
            _update_loop_values(values, result, spec.carry, spec.collect)
            iteration_count = iteration + 1
            values["loop.iterations"] = iteration_count
            if _loop_should_stop(frame, values, iteration_count):
                return _loop_outputs(frame, values)
        raise PipelineRuntimeError(f"loop node '{frame.name}' exceeded max_iterations={spec.max_iterations}")

    def _run_loop_body_iteration(
        self,
        frame: NodeFrame,
        runtime: "PipelineRuntime",
        initial: Mapping[str, object],
        iteration_path: tuple[str, ...],
        iteration_index: int,
    ) -> RunResult:
        if self.runtime_options.trace == "full":
            self.trace.add_event(
                {
                    "kind": "loop_iteration",
                    "node": frame.name,
                    "type": frame.node_type,
                    "details": {"iteration": iteration_index, "initial_keys": sorted(str(key) for key in initial)},
                },
                iteration_path,
            )
        try:
            result = runtime.run(initial)
        except Exception:
            self.trace.merge_child(iteration_path, runtime.trace)
            raise
        self.trace.merge_child(iteration_path, runtime.trace)
        return result
