"""Project existing diagnostic associations onto the user's actual Node calls."""
from __future__ import annotations

from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED


def node_health_classes(graph, findings):
    entries = {}
    called_blocks = set()

    def visit(block, prefix, active):
        if id(block) in active:
            return
        called_blocks.add(id(block))
        for node in block.nodes:
            key = (id(block), node.id)
            _, paths = entries.setdefault(key, (node.type_used, set()))
            path = (*prefix, node.id) if prefix is not None else None
            if path is not None:
                paths.add(path)
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            definition = block.nodesets.get(target)
            if definition is not None and node.status != STATUS_PLANNED and definition.status != STATUS_PLANNED:
                visit(definition.graph, path, {*active, id(block)})

    visit(graph, (), set())
    for definition in graph.nodesets.values():
        if id(definition.graph) not in called_blocks:
            visit(definition.graph, None, set())
    result = {}
    types = {node_type for node_type, _ in entries.values()}
    for finding in findings:
        item = finding.to_dict() if hasattr(finding, "to_dict") else finding
        severity = item.get("severity")
        if severity not in {"error", "warning"}:
            continue
        details = item.get("details", {})
        subject = item.get("object_id", item.get("subject_id", ""))
        node_type = details.get("node_type") or (subject if subject in types else "")
        is_call = not node_type and item.get("object_type", item.get("subject_type")) == "node"
        if not node_type and not is_call:
            continue
        associated = {tuple(path) for path in details.get("call_paths", ()) if isinstance(path, (tuple, list))}
        for key, (entry_type, paths) in entries.items():
            if node_type and entry_type != node_type or is_call and key[1] != subject:
                continue
            if "call_paths" in details:
                if associated:
                    if not any(path in associated or is_call and path[:-1] in associated for path in paths):
                        continue
                elif paths:
                    continue
            elif is_call and sum(candidate[1] == subject for candidate in entries) != 1:
                continue
            status = "healthError" if severity == "error" else "healthWarning"
            if result.get(key) != "healthError":
                result[key] = status
    return result
