"""Render the shared resource/source graph; dashed edges never schedule Nodes."""
import hashlib
from pathlib import PurePosixPath


def graph_id(value):
    return "vf_resource_" + hashlib.sha256(value.encode()).hexdigest()[:16]


def _label(value):
    return str(value).replace('"', "'").replace("<","&lt;").replace(">","&gt;")


def render_resource_graph(graph):
    lines = ["flowchart LR"]
    resources = graph.get("resources", {})
    for key, resource in resources.items():
        presentation = resource["effective_presentation"]["values"]
        name = resource.get("display_name") or resource.get("id", key)
        icon = presentation.get("icon", "")
        label = f"{icon + ' ' if icon else ''}{name}\\n{resource['kind']}: {resource['id']}"
        label += f"\\nstatus: {resource.get('status','implemented')}"
        if resource.get("markers"):
            label += "\\nmarkers: " + ", ".join(resource["markers"])
        if resource.get("flow_kind"):
            label += "\\nflow_kind: " + resource["flow_kind"]
        label += "\\nrulesets: " + (", ".join(resource.get("rulesets", ())) or "unconstrained")
        identifier = graph_id(key)
        lines.append(f'  {identifier}@{{ shape: {presentation["shape"]}, label: "{_label(label)}" }}')
        style = ",".join(f"{target}:{presentation[field]}" for field,target in (("fill","fill"),("stroke","stroke"),("text","color")) if field in presentation)
        lines.append(f"  style {identifier} {style};")
        if presentation["shape"] == "cloud":
            lines.append(f"  class {identifier} vibeflowCloudNode;")
    for key, file in graph.get("files", {}).items():
        roles = ", ".join(sorted({item["role"] for item in file["owners"]})) or "unregistered"
        label = f"{PurePosixPath(file['path']).name}\\n{roles}\\n{file.get('load_state','unknown')}"
        lines.append(f'  {graph_id(key)}@{{ shape: doc, label: "{_label(label)}" }}')
    for edge in graph.get("relations", ()):
        relation = edge["relation"] + (" (type)" if edge.get("type_only") else "")
        lines.append(f'  {graph_id(edge["from"])} -. "{_label(relation)}" .-> {graph_id(edge["to"])}')
    return "\n".join(lines) + "\n"
