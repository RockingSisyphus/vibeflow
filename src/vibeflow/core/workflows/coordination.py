"""Pure coordination contracts shared by hosts, Targets and presentation."""
from collections.abc import Mapping

TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
STATES = ("starting", "running", "stopping", *sorted(TERMINAL))


def workflow_descriptor(plan, reference, launches=()):
    """Describe a prepared artifact without retaining a graph or live objects."""
    from .references import workflow_reference
    def contract(inputs, outputs):
        return {"inputs": [item.to_dict() for item in inputs],
                "outputs": [item.to_dict() for item in outputs]}
    from .references import node_workflow_actions
    normalized = workflow_reference(reference) if reference is not None else None
    calls = []
    for block in plan.blocks:
        for node in block.nodes:
            for action in node_workflow_actions(node.capability_policy.to_value().get('actions', ()),
                    node.params.to_value(), root=normalized['root'] if normalized else ''):
                if action.get('capability') != 'vibeflow.workflow' or action['operation'] not in {'invoke_sync','call'}:
                    continue
                if action['operation'] == 'call':
                    from .references import launch_configuration
                    action['launch'] = launch_configuration(node.params.to_value()['launch'])
                calls.append(action)
    for item in launches:
        if not any(action.get('workflow') == item['workflow'] and action.get('launch') == item['launch'] for action in calls):
            calls.append({'operation':'call', **{k:item[k] for k in ('workflow','launch')}})
    return {"workflow": normalized, "entry_mode": plan.entry_mode, "calls": calls,
            "entries": {item.name: contract(item.inputs, item.outputs) for item in plan.named_entries},
            "default_entry": plan.default_entry, **contract(plan.inputs, plan.outputs)}


def synchronous_violation(completion, *, capabilities=(), descriptors=()):
    if completion == "suspend":
        return "suspending implementation"
    available = {item.id: item for item in descriptors}
    for requirement in capabilities:
        descriptor = available.get(requirement.id)
        if descriptor is None:
            continue
        for name in requirement.operations:
            operation = descriptor.operations.get(name)
            if operation is not None and operation.completion == "suspend":
                return f"suspending capability '{requirement.id}.{name}'"
    return None


def validate_descriptor(value):
    from .references import workflow_reference
    if not isinstance(value, Mapping) or value.get("entry_mode") not in {"sync", "async"}:
        raise ValueError("workflow descriptor requires entry_mode sync or async")
    return {**value, "workflow": workflow_reference(value.get("workflow"))}
