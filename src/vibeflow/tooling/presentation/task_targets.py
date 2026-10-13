"""Visible task-call declarations; these links describe launch permission."""
from vibeflow.core.contracts import providers_to_dicts, requirements_to_dicts


def task_target_document(node, descriptor_for=None):
    return {key: {"id": target.id, "type_used": target.type_used,
        "metadata": target.metadata.to_dict(), "flow_kind": getattr(descriptor_for(target.type_used),"flow_kind",target.flow_kind) if descriptor_for else target.flow_kind, "requires": requirements_to_dicts(target.requires),
        "provides": providers_to_dicts(target.provides), "config": dict(target.params),
        "node_configs": dict(target.node_config_overrides),
        "task_targets": task_target_document(target,descriptor_for)} for key, target in node.task_targets.items()}


def task_target_label(slot, target):
    rows = [target.metadata.display_name or slot, f"任务目标: {slot}",
            f"id: {target.id}", f"type_used: {target.type_used}", target.metadata.description]
    rows.extend(f"requires: {r.type} ({r.cardinality})" for r in target.requires)
    rows.extend(f"provides: {p.key}: {p.type}" for p in target.provides)
    return "\n".join(rows)
