from __future__ import annotations

import operator
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .compiler import GraphCompiler
from .context import Context
from .graph_config import EdgeSpec, GraphConfig, NodeSpec, STATUS_PLANNED
from .node import FLOW_KIND_TERMINAL
from .plugin import PluginRegistry
from .summaries import summarize_mapping
from .registry import NodeRegistry, NodeRegistryError
from .runtime_config import effective_node_params, nested_node_config_overrides, normalize_node_config_overrides
from .runtime_errors import PipelineRuntimeError
from .runtime_trace import RuntimeTrace
from .runtime_validation import assert_runtime_output_snapshot


class PipelineRuntime:
    def __init__(
        self,
        graph: GraphConfig,
        *,
        registry: NodeRegistry,
        boundary_registry: object | None = None,
        plugin_registry: PluginRegistry | None = None,
        run_dir: str | Path | None = None,
        node_config_overrides: Mapping[str, Mapping[str, object]] | None = None,
    ) -> None:
        if boundary_registry is not None:
            raise PipelineRuntimeError("boundary_registry is removed; use flowchart nodes")
        if _has_planned(graph):
            raise PipelineRuntimeError("planned nodes/nodesets cannot run")
        self.graph = graph
        self.registry = registry
        self._plugin_registry = plugin_registry
        self.compiled = GraphCompiler().compile(graph, registry=registry, plugin_registry=plugin_registry)
        self._specs = {node.name: node for node in graph.nodes}
        self.trace = RuntimeTrace()
        self._node_runs: dict[str, int] = {node.name: 0 for node in graph.nodes}
        self._incoming_edges = {
            node.name: tuple(edge for edge in self.compiled.effective_edges if edge.target == node.name)
            for node in graph.nodes
        }
        self._outgoing_edges = {
            node.name: tuple(edge for edge in self.compiled.effective_edges if edge.source == node.name)
            for node in graph.nodes
        }
        self._run_dir = Path(run_dir) if run_dir is not None else Path("runs") / "vibeflow"
        self._node_config_overrides = normalize_node_config_overrides(node_config_overrides or {})

    def run(self, initial: Mapping[str, Any] | None = None) -> Context:
        context = Context(dict(initial or {}))
        try:
            self._call_runtime_plugins("before_run", context.to_dict())
            self._run_steps(context)
            self.trace.stop_reason = self.trace.stop_reason or "completed"
            self._call_runtime_plugins("after_run", context.to_dict(), self.trace.to_dict())
        except Exception:
            self.trace.stop_reason = self.trace.stop_reason or "node_failed"
            self._write_trace(context)
            raise
        self._write_trace(context)
        return context

    def _run_steps(self, context: Context) -> None:
        ready = list(self._initial_ready_nodes(context))
        queued = set(ready)
        for _ in range(self.graph.max_steps):
            if not ready:
                self.trace.stop_reason = "no_ready_nodes"
                return
            node_name = ready.pop(0)
            queued.discard(node_name)
            if not self._requirements_available(node_name, context):
                continue
            outputs = self._run_node(node_name, context)
            self.trace.step_count += 1
            if self._is_end_terminal(node_name):
                self.trace.stop_reason = "completed"
                return
            for edge in self._activated_edges(node_name, outputs, context):
                self._record_edge(edge)
                if edge.target not in queued:
                    ready.append(edge.target)
                    queued.add(edge.target)
        self.trace.stop_reason = "max_steps"
        raise PipelineRuntimeError(f"pipeline exceeded max_steps={self.graph.max_steps}")

    def _initial_ready_nodes(self, context: Context) -> tuple[str, ...]:
        ready = []
        for node in self.graph.nodes:
            if self._incoming_edges.get(node.name):
                continue
            if not self._is_terminal_node(node.name):
                continue
            if self._requirements_available(node.name, context):
                ready.append(node.name)
        return tuple(ready)

    def _requirements_available(self, node_name: str, context: Context) -> bool:
        return all(context.exists(key) for key in self._specs[node_name].requires)

    def _is_end_terminal(self, node_name: str) -> bool:
        spec = self._specs[node_name]
        if self._outgoing_edges.get(node_name):
            return False
        return self._is_terminal_node(node_name)

    def _is_terminal_node(self, node_name: str) -> bool:
        return self.compiled.flow_kinds.get(node_name) == FLOW_KIND_TERMINAL

    def _activated_edges(self, node_name: str, outputs: Mapping[str, object], context: Context) -> tuple[EdgeSpec, ...]:
        active = []
        values = {**context.to_dict(), **dict(outputs)}
        for edge in self._outgoing_edges.get(node_name, ()):
            if not edge.when or _condition_matches(edge.when, values):
                active.append(edge)
        return tuple(active)

    def _run_node(self, node_name: str, context: Context) -> Mapping[str, object]:
        spec = self._specs[node_name]
        if spec.node_type.startswith("nodeset."):
            return self._run_nodeset_node(spec, context)
        return self._run_pure_node(spec, context)

    def _run_nodeset_node(self, spec: NodeSpec, context: Context) -> Mapping[str, object]:
        started = time.perf_counter()
        self._record_runtime_event("nodeset_enter", spec.name, spec.node_type)
        self._call_runtime_plugins("before_nodeset", spec.name, spec.node_type)
        try:
            self._run_nodeset(spec, context)
            outputs = {key: context.get(key, default=None) for key in spec.provides}
            self._mark_node_run(spec.name)
            self._record_runtime_event("nodeset_exit", spec.name, spec.node_type, output_summary=summarize_mapping(outputs), elapsed_ms=_elapsed_ms(started))
            self._call_runtime_plugins("after_nodeset", spec.name, spec.node_type)
            return outputs
        except Exception as exc:
            self._record_runtime_event("nodeset_failed", spec.name, spec.node_type, failure=str(exc), elapsed_ms=_elapsed_ms(started))
            raise

    def _run_pure_node(self, spec: NodeSpec, context: Context) -> Mapping[str, object]:
        started = time.perf_counter()
        inputs: dict[str, object] = {}
        try:
            node_cls = self.registry.get(spec.node_type)
            node = node_cls()
            inputs = {key: deepcopy(context.get(key)) for key in spec.requires}
            params = self.registry.merge_config(spec.node_type, effective_node_params(spec, self._node_config_overrides))
            self._call_runtime_plugins("before_node", spec.name, spec.node_type, summarize_mapping(inputs))
            before = deepcopy(inputs)
            outputs = node.run_pure(inputs, params)
            if inputs != before:
                raise PipelineRuntimeError(f"node '{spec.name}' mutated inputs")
            if not isinstance(outputs, Mapping):
                raise PipelineRuntimeError(f"node '{spec.name}' must return a mapping")
            unexpected = set(outputs) - set(spec.provides)
            if unexpected:
                raise PipelineRuntimeError(f"node '{spec.name}' returned undeclared outputs: {sorted(unexpected)}")
            missing = set(spec.provides) - set(outputs)
            if missing:
                raise PipelineRuntimeError(f"node '{spec.name}' missed declared outputs: {sorted(missing)}")
            contract = getattr(node_cls, "CONTRACT", None)
            for key, value in outputs.items():
                assert_runtime_output_snapshot(value, contract=contract, node_name=spec.name, key=str(key))
                context.set(str(key), value)
            self._mark_node_run(spec.name)
            self._record_runtime_event("node", spec.name, spec.node_type, input_summary=summarize_mapping(inputs), output_summary=summarize_mapping(outputs), elapsed_ms=_elapsed_ms(started))
            self._call_runtime_plugins("after_node", spec.name, spec.node_type, summarize_mapping(outputs))
            return outputs
        except NodeRegistryError as exc:
            failure = PipelineRuntimeError(str(exc))
            self._record_runtime_event("node_failed", spec.name, spec.node_type, failure=str(failure), elapsed_ms=_elapsed_ms(started))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event("node_failed", spec.name, spec.node_type, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=_elapsed_ms(started))
            raise

    def _run_nodeset(self, spec: NodeSpec, context: Context) -> None:
        nodeset_name = spec.node_type.removeprefix("nodeset.")
        nodeset = self.graph.nodesets.get(nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown nodeset: {nodeset_name}")
        if set(spec.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(f"nodeset node '{spec.name}' requires must match nodeset '{nodeset.name}' requires")
        if set(spec.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(f"nodeset node '{spec.name}' provides must match nodeset '{nodeset.name}' provides")
        initial = {key: deepcopy(context.get(key)) for key in spec.requires}
        nested_overrides = nested_node_config_overrides(spec, self._node_config_overrides)
        nested_context = PipelineRuntime(nodeset.graph, registry=self.registry, plugin_registry=self._plugin_registry, node_config_overrides=nested_overrides).run(initial)
        for key in spec.provides:
            if key not in nodeset.exports:
                raise PipelineRuntimeError(f"nodeset '{nodeset.name}' cannot export undeclared key '{key}'")
            context.set(key, nested_context.get(key))

    def _record_edge(self, edge: EdgeSpec) -> None:
        key = _edge_key(edge.pair)
        self.trace.edge_executions[key] = self.trace.edge_executions.get(key, 0) + 1

    def _mark_node_run(self, node_name: str) -> None:
        self._node_runs[node_name] = self._node_runs.get(node_name, 0) + 1
        self.trace.node_runs[node_name] = self._node_runs[node_name]
        self.trace.exec_order.append(node_name)

    def _write_trace(self, context: Context) -> None:
        payload = self.trace.to_dict()
        context.set("runtime.exec_order", payload["exec_order"])
        context.set("runtime.edge_executions", payload["edge_executions"])
        context.set("runtime.step_count", payload["step_count"])
        context.set("runtime.node_runs", payload["node_runs"])
        context.set("runtime.stop_reason", payload["stop_reason"])
        context.set("runtime.events", payload["events"])

    def _call_runtime_plugins(self, hook: str, *args) -> None:
        if self._plugin_registry is None:
            return
        for plugin in self._plugin_registry.runtime_plugins():
            method = getattr(plugin, hook, None)
            if not callable(method):
                continue
            try:
                method(*args)
            except Exception as exc:
                plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
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
    ) -> None:
        event: dict[str, object] = {"kind": kind, "node": node_name, "type": node_type}
        if input_summary is not None:
            event["input_summary"] = dict(input_summary)
        if output_summary is not None:
            event["output_summary"] = dict(output_summary)
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        if failure:
            event["failure"] = failure
        self.trace.events.append(event)


def _condition_matches(expression: str, values: Mapping[str, object]) -> bool:
    for token, op in (("==", operator.eq), ("!=", operator.ne)):
        if token not in expression:
            continue
        left, right = (part.strip() for part in expression.split(token, 1))
        if not left or not right:
            raise PipelineRuntimeError(f"invalid edge condition: {expression}")
        return bool(op(values.get(left), _literal_value(right)))
    raise PipelineRuntimeError(f"unsupported edge condition: {expression}")


def _has_planned(graph: GraphConfig) -> bool:
    return any(node.status == STATUS_PLANNED for node in graph.nodes) or any(nodeset.status == STATUS_PLANNED or _has_planned(nodeset.graph) for nodeset in graph.nodesets.values())


def _literal_value(value: str) -> object:
    if value in {"true", "false"}:
        return value == "true"
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _edge_key(pair: tuple[str, str]) -> str:
    return f"{pair[0]}->{pair[1]}"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)
