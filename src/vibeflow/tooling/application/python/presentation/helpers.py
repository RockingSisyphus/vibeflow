from __future__ import annotations

from typing import TYPE_CHECKING

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig, NodeCallSpec, STATUS_PLANNED
from vibeflow.tooling.presentation.node_presentation import registry_descriptor

if TYPE_CHECKING:
    from vibeflow.targets.python.project.registry import NodeRegistry


def node_is_external(node: NodeCallSpec, registry) -> bool:
    if registry is None or node.status == STATUS_PLANNED:
        return False
    return bool(getattr(registry_descriptor(registry, node.definition_id), "external", False))


def compile_for_render(graph: GraphConfig, compiled: CompiledGraph | None, registry: NodeRegistry | None, *, prepared=None) -> CompiledGraph:
    if prepared is not None:
        return prepared.graph_for(graph)[1]
    if compiled is not None:
        return compiled
    from vibeflow.targets.python.project.compiler import GraphCompiler

    return GraphCompiler().compile(graph, registry=registry)


def effective_graph_for_render(
    graph: GraphConfig,
    compiled: CompiledGraph | None,
    registry: NodeRegistry | None,
    *, prepared=None,
) -> tuple[GraphConfig, CompiledGraph]:
    if prepared is not None:
        return prepared.graph_for(graph)
    if registry is None:
        return graph, compile_for_render(graph, compiled, registry)
    from vibeflow.targets.python.project.compiler import GraphCompiler

    compilation = GraphCompiler().compile_with_findings(
        graph,
        registry=registry,
    )
    return compilation.workflow.graph, compilation.compiled_graph


def shorten(value: object, *, limit: int = 120) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."
