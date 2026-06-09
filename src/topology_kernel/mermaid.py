from __future__ import annotations

from .compiler import GraphCompiler
from .graph_config import GraphConfig


def export_mermaid(graph: GraphConfig, *, expand_nodesets: bool = False) -> str:
    compiled = GraphCompiler().compile(graph)
    lines = ["flowchart TD"]
    for node in graph.nodes:
        if expand_nodesets and node.node_type.startswith("nodeset."):
            lines.append(f'  subgraph {node.name}["{node.name}\\n{node.node_type}"]')
            nodeset_name = node.node_type.removeprefix("nodeset.")
            nodeset = graph.nodesets.get(nodeset_name)
            if nodeset is not None:
                nested = export_mermaid(nodeset.graph, expand_nodesets=True).splitlines()[1:]
                lines.extend("  " + line for line in nested)
            lines.append("  end")
        else:
            lines.append(f'  {node.name}["{node.name}\\n{node.node_type}"]')
    for edge in compiled.effective_edges:
        label_parts = [f"max={edge.max_executions}"]
        if edge.loop:
            label_parts.insert(0, f"loop {edge.loop}")
        label = " ".join(label_parts)
        lines.append(f"  {edge.source} -->|{label}| {edge.target}")
    return "\n".join(lines) + "\n"
