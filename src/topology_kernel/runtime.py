from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping

from .compiler import GraphCompiler
from .context import Context
from .graph_config import GraphConfig, NodeSpec
from .registry import NodeRegistry, NodeRegistryError


@dataclass
class PipelineRuntimeError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"Pipeline runtime error: {self.detail}"


class PipelineRuntime:
    def __init__(self, graph: GraphConfig, *, registry: NodeRegistry) -> None:
        self.graph = graph
        self.registry = registry
        self.compiled = GraphCompiler().compile(graph)
        self._specs = {node.name: node for node in graph.nodes}

    def run(self, initial: Mapping[str, Any] | None = None) -> Context:
        context = Context(dict(initial or {}))
        exec_order: list[str] = []
        for node_name in self.compiled.acyclic_order:
            self._run_node(node_name, context)
            exec_order.append(node_name)
        for loop in self.graph.loops:
            loop_nodes = loop.nodes or tuple(dict.fromkeys(name for edge in loop.edges for name in edge))
            for _ in range(loop.max_iterations):
                if loop.until and bool(context.get(loop.until, default=False)):
                    break
                for node_name in loop_nodes:
                    self._run_node(node_name, context)
                    exec_order.append(node_name)
        context.set("runtime.exec_order", tuple(exec_order))
        return context

    def _run_node(self, node_name: str, context: Context) -> None:
        spec = self._specs[node_name]
        if spec.node_type.startswith("nodeset."):
            self._run_nodeset(spec, context)
            return
        try:
            node = self.registry.get(spec.node_type)()
        except NodeRegistryError as exc:
            raise PipelineRuntimeError(str(exc)) from exc
        inputs = {key: deepcopy(context.get(key)) for key in spec.requires}
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
        for key, value in outputs.items():
            context.set(str(key), value)

    def _run_nodeset(self, spec: NodeSpec, context: Context) -> None:
        nodeset_name = spec.node_type.removeprefix("nodeset.")
        nodeset = self.graph.nodesets.get(nodeset_name)
        if nodeset is None:
            raise PipelineRuntimeError(f"unknown nodeset: {nodeset_name}")
        initial = {key: deepcopy(context.get(key)) for key in spec.requires}
        nested_context = PipelineRuntime(nodeset.graph, registry=self.registry).run(initial)
        for key in spec.provides:
            if key not in nodeset.exports:
                raise PipelineRuntimeError(f"nodeset '{nodeset.name}' cannot export undeclared key '{key}'")
            context.set(key, nested_context.get(key))
