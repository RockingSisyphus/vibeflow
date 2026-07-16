from __future__ import annotations

from typing import Mapping

from vibeflow.data_contract import DataEnvelope, DataRequirement, RunResult
from vibeflow.runtime.errors import PipelineRuntimeError, normalize_delegate_cli_system_exit
from vibeflow.runtime.trace import RuntimeTrace

class RuntimeTraceMixin:
    def _record_type_resolution(self, frame: NodeFrame, requirement: DataRequirement, matches: list[DataEnvelope]) -> None:
        self._record_runtime_event(
            "type_resolve",
            frame.name,
            frame.node_type,
            details={
                "consumer": frame.name,
                "required_type": requirement.type,
                "cardinality": requirement.cardinality,
                "matched_count": len(matches),
                "resolved_source_keys": [match.key for match in matches],
                "source_nodes": [match.source_node for match in matches],
            },
        )

    def _write_trace(self, result: RunResult) -> None:
        payload = self.trace.to_dict()
        result.set("runtime.exec_order", payload["exec_order"])
        result.set("runtime.edge_executions", payload["edge_executions"])
        result.set("runtime.step_count", payload["step_count"])
        result.set("runtime.node_runs", payload["node_runs"])
        result.set("runtime.qualified_exec_order", payload["qualified_exec_order"])
        result.set("runtime.qualified_edge_executions", payload["qualified_edge_executions"])
        result.set("runtime.qualified_node_runs", payload["qualified_node_runs"])
        result.set("runtime.total_step_count", payload["total_step_count"])
        result.set("runtime.stop_reason", payload["stop_reason"])
        result.set("runtime.current_node", payload["current_node"])
        result.set("runtime.exception", payload["exception"])
        result.set("runtime.event_count", payload["event_count"])
        result.set("runtime.trace_path", payload["trace_path"])
        result.set("runtime.events_streamed", payload["events_streamed"])

    def _call_runtime_plugins(self, hook: str, *args) -> None:
        methods = self._hook_plan.for_hook(hook)
        if not methods:
            return
        for plugin_name, method in methods:
            try:
                method(*args)
            except SystemExit as exc:
                if not self.delegate_cli:
                    raise PipelineRuntimeError(
                        f"runtime plugin '{plugin_name}' {hook} attempted SystemExit outside delegate CLI mode"
                    ) from exc
                if hook.endswith("_failed"):
                    raise PipelineRuntimeError(
                        f"runtime plugin '{plugin_name}' {hook} cannot replace an existing runtime failure with SystemExit"
                    ) from exc
                raise normalize_delegate_cli_system_exit(exc, source=f"plugin:{plugin_name}") from exc
            except Exception as exc:
                raise PipelineRuntimeError(f"runtime plugin '{plugin_name}' {hook} failed: {exc}") from exc

    def _record_runtime_event(
        self,
        kind: str,
        node_name: str,
        node_type: str,
        *,
        input_summary: Mapping[str, object] | None = None,
        output_summary: Mapping[str, object] | None = None,
        elapsed_ms: float | None = None,
        failure: str = "",
        details: Mapping[str, object] | None = None,
    ) -> None:
        if self.runtime_options.trace == "off":
            return
        if self.runtime_options.trace == "boundary" and kind not in {"run_start", "run_end", "business_exit", "nodeset_enter", "nodeset_exit", "nodeset_failed", "loop_enter", "loop_exit", "loop_block_enter", "loop_block_exit", "loop_failed", "node_failed", "planned_stub", "async_result_abandoned", "async_detached_failed", "async_detached_timeout", "block_enter", "block_exit", "block_failed", "type_resolve"}:
            return
        event: dict[str, object] = {"kind": kind, "node": node_name, "type": node_type}
        if input_summary is not None:
            event["input_summary"] = dict(input_summary)
        if output_summary is not None:
            event["output_summary"] = dict(output_summary)
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        if failure:
            event["failure"] = failure
        if details is not None:
            event["details"] = dict(details)
        self.trace.add_event(event, self._trace_event_path((node_name,)), self._trace_sink)

    def _record_run_boundary(self, kind: str) -> None:
        if self.runtime_options.trace == "boundary":
            self._record_runtime_event(kind, "pipeline", "pipeline")

    def _merge_child_trace(self, frame: NodeFrame, child_trace: RuntimeTrace) -> None:
        self.trace.merge_child((frame.name,), child_trace)

    def _trace_event_path(self, path: tuple[str, ...]) -> tuple[str, ...]:
        return (*self._trace_path_prefix, *path)
