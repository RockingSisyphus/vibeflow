"""Project existing diagnostic associations onto the user's actual Node calls."""
from __future__ import annotations

from vibeflow.core.flow import LOOP_DEFINITION_IDS, STATUS_PLANNED


def node_health_classes(graph, findings):
    entries = {}
    called_blocks = set()

    def visit(block, prefix, active):
        if id(block) in active:
            return
        called_blocks.add(id(block))
        for node in block.nodes:
            key = (id(block), node.id)
            _, paths = entries.setdefault(key, (node.definition_id, set()))
            path = (*prefix, node.id) if prefix is not None else None
            if path is not None:
                paths.add(path)
            target = node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id
            definition = block.nodeset_types.get(target)
            if definition is not None and node.status != STATUS_PLANNED and definition.status != STATUS_PLANNED:
                visit(definition.graph, path, {*active, id(block)})

    visit(graph, (), set())
    for definition in graph.nodeset_types.values():
        if id(definition.graph) not in called_blocks:
            visit(definition.graph, None, set())
    result = {}
    definitions = {definition_id for definition_id, _ in entries.values()}
    for finding in findings:
        item = finding.to_dict() if hasattr(finding, "to_dict") else finding
        severity = item.get("severity")
        if severity not in {"error", "warning"}:
            continue
        details = item.get("details", {})
        subject = item.get("object_id", item.get("subject_id", ""))
        definition_id = details.get("definition_id") or (subject if subject in definitions else "")
        is_call = not definition_id and item.get("object_type", item.get("subject_type")) == "node"
        if not definition_id and not is_call:
            continue
        associated = {tuple(path) for path in details.get("call_paths", ()) if isinstance(path, (tuple, list))}
        for key, (entry_definition, paths) in entries.items():
            if definition_id and entry_definition != definition_id or is_call and key[1] != subject:
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
