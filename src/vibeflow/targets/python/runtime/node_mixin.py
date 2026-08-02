from __future__ import annotations

import time
from pathlib import Path
from typing import Mapping

from vibeflow.targets.python.runtime.block_compiler import loop_block, nodeset_block
from vibeflow.targets.python.runtime.support.planned import load_stub_callable, resolve_stub_module_path, signature_is_run_stub
from vibeflow.targets.python.project.registry import NodeRegistryError
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError, normalize_delegate_cli_system_exit
from vibeflow.targets.python.runtime.helpers import elapsed_ms
from vibeflow.targets.python.runtime.summaries import summarize_mapping

class RuntimeNodeMixin:
    def _run_compiled_frame(self, frame: NodeFrame, state: "_RuntimeState") -> Mapping[str, object]:
        self.trace.current_node = frame.name
        inputs = self._resolve_inputs(frame, state)
        state.last_inputs[frame.name] = inputs
        state.inboxes[frame.name] = []
        if frame.async_mode:
            outputs = self._run_async_node(frame, inputs)
        elif frame.is_io:
            outputs = self._run_io_node(frame, inputs)
        elif frame.is_planned_stub:
            outputs = self._run_planned_stub_node(frame, inputs)
        elif frame.is_loop:
            if loop_block(self._plan, frame.name) is not None:
                outputs = self._run_loop_block_node(frame, inputs)
            else:
                outputs = self._run_loop_node(frame, inputs)
        elif frame.is_nodeset:
            if nodeset_block(self._plan, frame.name) is not None:
                outputs = self._run_nodeset_block_node(frame, inputs)
            else:
                outputs = self._run_nodeset_node(frame, inputs)
        else:
            outputs = self._run_pure_node(frame, inputs)
        self._record_node_output_candidates(frame.name, outputs, state)
        return outputs

    def _run_io_node(
        self,
        frame: NodeFrame,
        inputs: Mapping[str, object],
    ) -> Mapping[str, object]:
        operation = frame.io_spec.operation
        capability = self._capabilities.get("vibeflow.port")
        if not isinstance(capability, Mapping):
            raise PipelineRuntimeError(
                "vibeflow.io requires capability 'vibeflow.port'"
            )
        callable_operation = capability.get(operation)
        if not callable(callable_operation):
            raise PipelineRuntimeError(
                f"vibeflow.port is missing operation '{operation}'"
            )
        self._call_runtime_plugins(
            "before_node",
            frame.name,
            frame.node_type,
            summarize_mapping(inputs),
        )
        try:
            if operation == "receive":
                result = callable_operation(
                    {"port": frame.io_spec.port}
                )
                if not isinstance(result, Mapping) or "value" not in result:
                    raise PipelineRuntimeError(
                        "vibeflow.port.receive must return a mapping with value"
                    )
                outputs: Mapping[str, object] = {
                    frame.provides[0].key: result["value"]
                }
            elif operation == "send":
                raw = next(iter(inputs.values()))
                if isinstance(raw, list):
                    raw = raw[0]
                value = (
                    raw.get("value")
                    if isinstance(raw, Mapping) and "value" in raw
                    else getattr(raw, "value", raw)
                )
                result = callable_operation(
                    {"port": frame.io_spec.port, "value": value}
                )
                if result is not None:
                    raise PipelineRuntimeError(
                        "vibeflow.port.send must return None"
                    )
                outputs = {}
            else:
                raise PipelineRuntimeError(
                    f"unsupported vibeflow.io operation '{operation}'"
                )
            validated = self._validate_outputs(
                frame,
                outputs,
                subject="vibeflow.io",
            )
            self._mark_node_run(frame.name)
            self._record_runtime_event(
                f"io_{operation}",
                frame.name,
                frame.node_type,
                input_summary=summarize_mapping(inputs),
                output_summary=summarize_mapping(validated),
                details={"port": frame.io_spec.port},
            )
            self._call_runtime_plugins(
                "after_node",
                frame.name,
                frame.node_type,
                summarize_mapping(validated),
            )
            return validated
        except Exception as exc:
            self._record_runtime_event(
                "node_failed",
                frame.name,
                frame.node_type,
                failure=str(exc),
            )
            self._call_runtime_plugins(
                "node_failed",
                frame.name,
                frame.node_type,
                str(exc),
            )
            raise

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
        except SystemExit as exc:
            failure = PipelineRuntimeError(
                f"planned python_stub node '{frame.name}' attempted SystemExit; planned stubs use effect scope none"
            )
            self._record_runtime_event(
                "node_failed",
                frame.name,
                frame.node_type,
                input_summary=summarize_mapping(inputs),
                failure=str(failure),
                elapsed_ms=elapsed_ms(started),
            )
            self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(failure))
            raise failure from exc
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
        except SystemExit as exc:
            if not self.delegate_cli:
                failure = PipelineRuntimeError(
                    f"node '{frame.name}' attempted SystemExit outside delegate CLI mode"
                )
                self._record_runtime_event(
                    "node_failed",
                    frame.name,
                    frame.node_type,
                    input_summary=summarize_mapping(inputs),
                    failure=str(failure),
                    elapsed_ms=elapsed_ms(started),
                )
                self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(failure))
                raise failure from exc
            if frame.flow_kind not in {"io", "document", "data_store"}:
                failure = PipelineRuntimeError(
                    f"node '{frame.name}' with flow_kind '{frame.flow_kind}' cannot control delegate CLI exit"
                )
                self._record_runtime_event(
                    "node_failed",
                    frame.name,
                    frame.node_type,
                    input_summary=summarize_mapping(inputs),
                    failure=str(failure),
                    elapsed_ms=elapsed_ms(started),
                )
                self._call_runtime_plugins("node_failed", frame.name, frame.node_type, str(failure))
                raise failure from exc
            raise normalize_delegate_cli_system_exit(exc, source=frame.name) from exc
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


__all__ = ["RuntimeNodeMixin"]
