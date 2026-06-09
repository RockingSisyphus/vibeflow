from __future__ import annotations

import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .boundary import BoundaryRegistry, BoundaryRegistryError, GlobalBoundary
from .compiler import GraphCompiler
from .context import Context
from .graph_config import GraphConfig, NodeSpec
from .node import NodeContract
from .path_utils import is_relative_to
from .plugin import PluginRegistry
from .summaries import summarize_mapping
from .registry import NodeRegistry, NodeRegistryError


@dataclass
class PipelineRuntimeError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"Pipeline runtime error: {self.detail}"


@dataclass
class BoundaryRuntimeError(PipelineRuntimeError):
    pass


@dataclass
class RuntimeTrace:
    exec_order: list[str] = field(default_factory=list)
    edge_executions: dict[str, int] = field(default_factory=dict)
    loop_iterations: dict[str, int] = field(default_factory=dict)
    loop_stop_reasons: dict[str, str] = field(default_factory=dict)
    loop_orders: dict[str, tuple[str, ...]] = field(default_factory=dict)
    boundary_events: list[dict[str, object]] = field(default_factory=list)
    events: list[dict[str, object]] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "exec_order": tuple(self.exec_order),
            "edge_executions": dict(self.edge_executions),
            "loop_iterations": dict(self.loop_iterations),
            "loop_stop_reasons": dict(self.loop_stop_reasons),
            "loop_orders": {name: list(order) for name, order in self.loop_orders.items()},
            "boundary_events": [dict(event) for event in self.boundary_events],
            "events": [dict(event) for event in self.events],
        }


class PipelineRuntime:
    def __init__(
        self,
        graph: GraphConfig,
        *,
        registry: NodeRegistry,
        boundary_registry: BoundaryRegistry | None = None,
        plugin_registry: PluginRegistry | None = None,
        run_dir: str | Path | None = None,
    ) -> None:
        self.graph = graph
        self.registry = registry
        self._plugin_registry = plugin_registry
        self.compiled = GraphCompiler().compile(graph, plugin_registry=plugin_registry)
        self._specs = {node.name: node for node in graph.nodes}
        self.trace = RuntimeTrace(loop_orders=dict(self.compiled.loop_orders))
        self._node_runs: dict[str, int] = {node.name: 0 for node in graph.nodes}
        self._incoming_edges = {
            node.name: tuple(edge for edge in self.compiled.effective_edges if edge.target == node.name)
            for node in graph.nodes
        }
        self._boundary_spec = graph.boundary
        self._boundary = self._load_boundary(boundary_registry)
        self._run_dir = self._resolve_run_dir(run_dir)
        self._boundary_trace_path = self._run_dir / "boundary_trace.jsonl" if self._boundary is not None else None

    def run(self, initial: Mapping[str, Any] | None = None) -> Context:
        context = Context(dict(initial or {}))
        try:
            self._call_runtime_plugins("before_run", context.to_dict())
            self._call_boundary("before_run", context, lambda boundary: boundary.before_run(self._run_config()))
            for node_name in self.compiled.acyclic_order:
                self._run_node(node_name, context)
            for loop in self.graph.loops:
                loop_nodes = self.compiled.loop_orders.get(loop.name, ())
                self.trace.loop_iterations[loop.name] = 0
                self.trace.loop_stop_reasons[loop.name] = ""
                for iteration in range(loop.max_iterations):
                    if loop.until and bool(context.get(loop.until, default=False)):
                        self.trace.loop_stop_reasons[loop.name] = "until"
                        break
                    try:
                        self._call_boundary(
                            "before_iteration",
                            context,
                            lambda boundary, iteration=iteration: boundary.before_iteration(iteration, context.to_dict()),
                            iteration=iteration,
                        )
                        for node_name in loop_nodes:
                            self._run_node(node_name, context)
                        self._call_boundary(
                            "after_iteration",
                            context,
                            lambda boundary, iteration=iteration: boundary.after_iteration(
                                iteration,
                                self._boundary_consumed_outputs(context),
                                context.to_dict(),
                            ),
                            iteration=iteration,
                        )
                    except BoundaryRuntimeError:
                        self.trace.loop_stop_reasons[loop.name] = "boundary_failed"
                        self.trace.loop_iterations[loop.name] = iteration
                        self._write_trace(context)
                        raise
                    except Exception:
                        self.trace.loop_stop_reasons[loop.name] = "node_failed"
                        self.trace.loop_iterations[loop.name] = iteration
                        self._write_trace(context)
                        raise
                    self.trace.loop_iterations[loop.name] = iteration + 1
                if not self.trace.loop_stop_reasons[loop.name]:
                    self.trace.loop_stop_reasons[loop.name] = "max_iterations"
            self._call_boundary("after_run", context, lambda boundary: boundary.after_run(context.to_dict(), self._run_config()))
            self._call_runtime_plugins("after_run", context.to_dict(), self.trace.to_dict())
        except Exception:
            self.trace.loop_stop_reasons.setdefault("runtime", "boundary_failed")
            self._write_trace(context)
            raise
        self._write_trace(context)
        return context

    def _load_boundary(self, boundary_registry: BoundaryRegistry | None) -> GlobalBoundary | None:
        if self._boundary_spec is None:
            return None
        if boundary_registry is None:
            raise PipelineRuntimeError("graph declares boundary but no boundary registry was provided")
        try:
            boundary_cls = boundary_registry.get(self._boundary_spec.boundary_type)
            return boundary_cls()
        except (BoundaryRegistryError, TypeError) as exc:
            raise PipelineRuntimeError(str(exc)) from exc

    def _resolve_run_dir(self, run_dir: str | Path | None) -> Path:
        if run_dir is not None:
            return Path(run_dir)
        if self._boundary_spec is not None:
            configured = self._boundary_spec.config.get("run_dir")
            if isinstance(configured, str) and configured.strip():
                return Path(configured)
        return Path("runs") / "topology_kernel"

    def _run_config(self) -> dict[str, object]:
        spec = self._boundary_spec
        return {
            "run_dir": str(self._run_dir),
            "boundary": {
                "type": spec.boundary_type if spec else "",
                "config": dict(spec.config) if spec else {},
                "consumes": list(spec.consumes) if spec else [],
                "provides": list(spec.provides) if spec else [],
                "allowed_paths": list(spec.allowed_paths) if spec else [],
            },
        }

    def _call_boundary(self, stage: str, context: Context, call, *, iteration: int | None = None) -> None:
        if self._boundary is None or self._boundary_spec is None:
            return
        try:
            self._call_boundary_plugins("before_boundary", stage, context.to_dict(), iteration)
            result = call(self._boundary)
            if not isinstance(result, Mapping):
                raise PipelineRuntimeError(f"boundary {stage} must return a mapping")
            updates = self._validate_boundary_result(stage, result)
            context.update_flat(updates)
            self._record_boundary_event(stage, "ok", result, iteration=iteration)
            self._call_boundary_plugins("after_boundary", stage, dict(result), iteration)
        except PipelineRuntimeError as exc:
            self._record_boundary_event(stage, "error", {"error": str(exc)}, iteration=iteration)
            if isinstance(exc, BoundaryRuntimeError):
                raise
            raise BoundaryRuntimeError(exc.detail) from exc
        except Exception as exc:
            self._record_boundary_event(stage, "error", {"error": str(exc)}, iteration=iteration)
            raise BoundaryRuntimeError(f"boundary {stage} failed: {exc}") from exc

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

    def _call_boundary_plugins(self, hook: str, *args) -> None:
        if self._plugin_registry is None:
            return
        for plugin in self._plugin_registry.boundary_plugins():
            method = getattr(plugin, hook, None)
            if not callable(method):
                continue
            try:
                method(*args)
            except Exception as exc:
                plugin_name = str(getattr(plugin, "name", plugin.__class__.__name__))
                raise BoundaryRuntimeError(f"boundary plugin '{plugin_name}' {hook} failed: {exc}") from exc

    def _validate_boundary_result(self, stage: str, result: Mapping[str, object]) -> dict[str, object]:
        assert self._boundary_spec is not None
        updates: dict[str, object] = {}
        for key, value in result.items():
            text_key = str(key)
            if text_key in {"artifacts", "boundary.artifacts"}:
                self._assert_boundary_artifacts(value)
                continue
            if text_key not in self._boundary_spec.provides:
                raise PipelineRuntimeError(
                    f"boundary {stage} returned undeclared key '{text_key}'; declare it in boundary.provides"
                )
            updates[text_key] = value
        return updates

    def _assert_boundary_artifacts(self, value: object) -> None:
        paths = value if isinstance(value, list) else [value]
        assert self._boundary_spec is not None
        allowed_roots = [self._run_dir, *(Path(path) for path in self._boundary_spec.allowed_paths)]
        config_allowed = self._boundary_spec.config.get("allowed_paths")
        if isinstance(config_allowed, list):
            allowed_roots.extend(Path(str(path)) for path in config_allowed)
        resolved_roots = [root.resolve() for root in allowed_roots]
        for item in paths:
            path = Path(str(item)).resolve()
            if not any(is_relative_to(path, root) for root in resolved_roots):
                raise PipelineRuntimeError(f"boundary artifact path is outside controlled paths: {path}")

    def _boundary_consumed_outputs(self, context: Context) -> dict[str, object]:
        assert self._boundary_spec is not None
        out: dict[str, object] = {}
        for key in self._boundary_spec.consumes:
            if context.exists(key):
                out[key] = context.get(key)
        return out

    def _record_boundary_event(
        self,
        stage: str,
        status: str,
        payload: Mapping[str, object],
        *,
        iteration: int | None = None,
    ) -> None:
        event: dict[str, object] = {"stage": stage, "status": status}
        if iteration is not None:
            event["iteration"] = iteration
        event["keys"] = sorted(str(key) for key in payload if str(key) not in {"artifacts", "boundary.artifacts"})
        if "error" in payload:
            event["error"] = str(payload["error"])
        self.trace.boundary_events.append(event)
        if self._boundary_trace_path is not None:
            self._boundary_trace_path.parent.mkdir(parents=True, exist_ok=True)
            with self._boundary_trace_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    def _run_node(self, node_name: str, context: Context) -> None:
        spec = self._specs[node_name]
        if spec.node_type.startswith("nodeset."):
            self._record_incoming_edges(node_name)
            started = time.perf_counter()
            self._record_runtime_event("nodeset_enter", node_name, spec.node_type)
            self._call_runtime_plugins("before_nodeset", node_name, spec.node_type)
            try:
                self._run_nodeset(spec, context)
                self._mark_node_run(node_name)
                outputs = {key: context.get(key, default=None) for key in spec.provides}
                self._record_runtime_event(
                    "nodeset_exit",
                    node_name,
                    spec.node_type,
                    output_summary=summarize_mapping(outputs),
                    elapsed_ms=_elapsed_ms(started),
                )
                self._call_runtime_plugins("after_nodeset", node_name, spec.node_type)
            except Exception as exc:
                self._record_runtime_event(
                    "nodeset_failed",
                    node_name,
                    spec.node_type,
                    failure=str(exc),
                    elapsed_ms=_elapsed_ms(started),
                )
                raise
            return
        started = time.perf_counter()
        inputs: dict[str, object] = {}
        try:
            self._record_incoming_edges(node_name)
            node_cls = self.registry.get(spec.node_type)
            node = node_cls()
            inputs = {key: deepcopy(context.get(key)) for key in spec.requires}
            self._call_runtime_plugins("before_node", node_name, spec.node_type, summarize_mapping(inputs))
            before = deepcopy(inputs)
            outputs = node.run_pure(inputs, spec.params)
            if inputs != before:
                raise PipelineRuntimeError(f"node '{node_name}' mutated inputs")
            if not isinstance(outputs, Mapping):
                raise PipelineRuntimeError(f"node '{node_name}' must return a mapping")
            unexpected = set(outputs) - set(spec.provides)
            if unexpected:
                raise PipelineRuntimeError(f"node '{node_name}' returned undeclared outputs: {sorted(unexpected)}")
            missing = set(spec.provides) - set(outputs)
            if missing:
                raise PipelineRuntimeError(f"node '{node_name}' missed declared outputs: {sorted(missing)}")
            contract = getattr(node_cls, "CONTRACT", None)
            for key, value in outputs.items():
                if not _output_allows_opaque_snapshot(contract, str(key)):
                    _assert_json_snapshot(value, node_name=node_name, key=str(key))
            for key, value in outputs.items():
                context.set(str(key), value)
            self._mark_node_run(node_name)
            self._record_runtime_event(
                "node",
                node_name,
                spec.node_type,
                input_summary=summarize_mapping(inputs),
                output_summary=summarize_mapping(outputs),
                elapsed_ms=_elapsed_ms(started),
            )
            self._call_runtime_plugins("after_node", node_name, spec.node_type, summarize_mapping(outputs))
        except NodeRegistryError as exc:
            failure = PipelineRuntimeError(str(exc))
            self._record_runtime_event("node_failed", node_name, spec.node_type, failure=str(failure), elapsed_ms=_elapsed_ms(started))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event(
                "node_failed",
                node_name,
                spec.node_type,
                input_summary=summarize_mapping(inputs),
                failure=str(exc),
                elapsed_ms=_elapsed_ms(started),
            )
            raise

    def _run_nodeset(self, spec: NodeSpec, context: Context) -> None:
        nodeset_name = spec.node_type.removeprefix("nodeset.")
        nodeset = self.graph.nodesets.get(nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown nodeset: {nodeset_name}")
        if set(spec.requires) != set(nodeset.requires):
            raise PipelineRuntimeError(
                f"nodeset node '{spec.name}' requires must match nodeset '{nodeset.name}' requires"
            )
        if set(spec.provides) != set(nodeset.provides):
            raise PipelineRuntimeError(
                f"nodeset node '{spec.name}' provides must match nodeset '{nodeset.name}' provides"
            )
        initial = {key: deepcopy(context.get(key)) for key in spec.requires}
        nested_context = PipelineRuntime(nodeset.graph, registry=self.registry, plugin_registry=self._plugin_registry).run(initial)
        for key in spec.provides:
            if key not in nodeset.exports:
                raise PipelineRuntimeError(f"nodeset '{nodeset.name}' cannot export undeclared key '{key}'")
            context.set(key, nested_context.get(key))

    def _record_incoming_edges(self, node_name: str) -> None:
        for edge in self._incoming_edges.get(node_name, ()):
            if self._node_runs.get(edge.source, 0) < 1:
                continue
            key = _edge_key(edge.pair)
            count = self.trace.edge_executions.get(key, 0) + 1
            if count > edge.max_executions:
                raise PipelineRuntimeError(
                    f"edge {edge.source}->{edge.target} exceeded max_executions={edge.max_executions}"
                )
            self.trace.edge_executions[key] = count

    def _mark_node_run(self, node_name: str) -> None:
        self._node_runs[node_name] = self._node_runs.get(node_name, 0) + 1
        self.trace.exec_order.append(node_name)

    def _write_trace(self, context: Context) -> None:
        payload = self.trace.to_dict()
        context.set("runtime.exec_order", payload["exec_order"])
        context.set("runtime.edge_executions", payload["edge_executions"])
        context.set("runtime.loop_iterations", payload["loop_iterations"])
        context.set("runtime.loop_stop_reasons", payload["loop_stop_reasons"])
        context.set("runtime.loop_orders", payload["loop_orders"])
        context.set("runtime.boundary_events", payload["boundary_events"])
        context.set("runtime.events", payload["events"])

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
        event: dict[str, object] = {
            "kind": kind,
            "node": node_name,
            "type": node_type,
        }
        if input_summary is not None:
            event["input_summary"] = dict(input_summary)
        if output_summary is not None:
            event["output_summary"] = dict(output_summary)
        if elapsed_ms is not None:
            event["elapsed_ms"] = elapsed_ms
        if failure:
            event["failure"] = failure
        self.trace.events.append(event)


def _output_allows_opaque_snapshot(contract: object, key: str) -> bool:
    if not isinstance(contract, NodeContract):
        return False
    schema = contract.output_schema.get(key)
    return isinstance(schema, Mapping) and schema.get("snapshot") == "opaque"


def _assert_json_snapshot(value: Any, *, node_name: str, key: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise PipelineRuntimeError(f"node '{node_name}' output '{key}' is not JSON snapshot serializable: {exc}") from exc


def _edge_key(pair: tuple[str, str]) -> str:
    return f"{pair[0]}->{pair[1]}"


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)

