from __future__ import annotations

import time
from pathlib import Path
from typing import Mapping

from .block_compiler import loop_block, nodeset_block
from .planned_behavior import load_stub_callable, resolve_stub_module_path, signature_is_run_stub
from .registry import NodeRegistryError
from .runtime_errors import PipelineRuntimeError
from .runtime_helpers import elapsed_ms
from .summaries import summarize_mapping

class RuntimeNodeMixin:
    def _run_compiled_frame(self, frame: NodeFrame, state: "_RuntimeState") -> Mapping[str, object]:
        self.trace.current_node = frame.name
        inputs = self._resolve_inputs(frame, state)
        state.last_inputs[frame.name] = inputs
        state.inboxes[frame.name] = []
        if frame.async_mode:
            return self._run_async_node(frame, inputs)
        if frame.is_planned_stub:
            return self._run_planned_stub_node(frame, inputs)
        if frame.is_loop:
            if loop_block(self._plan, frame.name) is not None:
                return self._run_loop_block_node(frame, inputs)
            return self._run_loop_node(frame, inputs)
        if frame.is_nodeset:
            if nodeset_block(self._plan, frame.name) is not None:
                return self._run_nodeset_block_node(frame, inputs)
            return self._run_nodeset_node(frame, inputs)
        return self._run_pure_node(frame, inputs)

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
        nodeset = self.graph.nodesets.get(frame.nodeset_type_key)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown planned python_stub nodeset: {frame.nodeset_type_key}")
        if not nodeset.provides:
            raise PipelineRuntimeError(f"planned python_stub nodeset '{nodeset.type_key}' must declare provides")
        if set(frame.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(f"planned python_stub nodeset instance '{frame.id}' requires must match nodeset '{nodeset.type_key}' requires")
        if set(frame.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(f"planned python_stub nodeset instance '{frame.id}' provides must match nodeset '{nodeset.type_key}' provides")
