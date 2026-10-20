"""Common entry, target and evaluated operation facts for architecture consumers."""
from vibeflow.core.workflows.entries import project_entry


def entry_facts(graph, compiled):
    entries = {}
    for name, declaration in graph.entries.items():
        selected, routes = project_entry(graph, compiled, name)
        entries[name] = {**declaration.to_dict(), "nodes": list(routes.order),
            "inputs": [item.to_dict() for item in selected.inputs],
            "outputs": [item.to_dict() for item in selected.outputs]}
    return {"entries": entries, "default_entry": graph.default_entry,
        "workflow_targets": {name: target.to_dict() for name, target in graph.workflow_targets.items()}}


def policy_facts(policies):
    import json
    return {json.dumps(list(path), ensure_ascii=False, separators=(",", ":")): value for path, value in policies.items()
            if value.get("capabilities") or value.get("actions")}
