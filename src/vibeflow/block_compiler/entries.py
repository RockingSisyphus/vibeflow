"""Select a baked entry without graph compilation or source inspection."""
from dataclasses import replace

from vibeflow.core.workflows.entries import choose_entry


def select_workflow_entry(plan, entry=None):
    declarations = {item.name: item for item in plan.named_entries}
    name = choose_entry(declarations, plan.default_entry, entry)
    if name is None:
        return plan
    selected = declarations[name]
    active = set(selected.nodes)
    root = plan.block(plan.entry_block)
    nodes = tuple(node for node in root.nodes if node.id in active)
    routes = tuple(route for route in root.routes if route.source in active and route.target in active)
    projected = replace(root, nodes=nodes, routes=routes, order=selected.nodes,
        entries=(selected.start,), exits=tuple(n for n in root.exits if n in active),
        inputs=selected.inputs, outputs=selected.outputs,
        contains_global_state=any(n.contains_global_state for n in nodes))
    included = {root.id: projected}

    def collect(block):
        for call in block.nodes:
            if call.child_block and call.child_block not in included:
                child = plan.block(call.child_block)
                included[child.id] = child
                collect(child)

    collect(projected)
    return replace(plan, blocks=tuple(included[b.id] for b in plan.blocks if b.id in included),
        inputs=selected.inputs, outputs=selected.outputs, selected_entry=name,
        contains_global_state=projected.contains_global_state)
