"""Fixed workflow operation facts; these describe calls, not permissions."""
from collections.abc import Mapping
from types import MappingProxyType

OPERATIONS = frozenset({"invoke_sync", "call", "wait", "send", "receive", "kill"})


def normalize_operations(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("workflow_operations must be a list")
    result = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) - {"operation", "wait"}:
            raise ValueError("workflow operation accepts operation and optional call wait")
        operation = item.get("operation")
        if operation not in OPERATIONS:
            raise ValueError(f"unknown workflow operation: {operation!r}")
        action = {"operation": operation}
        if operation == "call":
            wait = item.get("wait", False)
            if not isinstance(wait, bool):
                raise ValueError("workflow call wait must be boolean")
            action["wait"] = wait
        elif "wait" in item:
            raise ValueError("wait is only valid on a workflow call operation")
        if action not in result:
            result.append(action)
    return tuple(MappingProxyType(item) for item in result)


def node_operations(node, descriptor):
    if descriptor is not None:
        return tuple(dict(item) for item in descriptor.workflow_operations)
    return tuple(dict(item) for item in node.workflow_operations)


def operations_by_path(graph, descriptor, *, global_config=None):
    from vibeflow.core.graph_calls import graph_call_subjects
    return {(*subject.call_path, node.id): node_operations(node, descriptor(node.definition_id))
            for subject in graph_call_subjects(graph, global_config=global_config,
                include_planned=True, include_planned_calls=True)
            for node in subject.graph.nodes}


def operation_facts(graph, descriptor, *, global_config=None):
    return {path: {"actions": list(actions)} for path, actions in
            operations_by_path(graph, descriptor, global_config=global_config).items()}
