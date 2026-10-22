"""Collect typed Rule results and prepare language-neutral workflow facts."""
from dataclasses import replace

from vibeflow.core.descriptors.resource_use import ResourceUse, RESOURCE_USE_TYPE
from vibeflow.core.findings import HealthFinding
from .use_facts import workflow_identity, workflow_resource_facts, source_owners


def resource_workflows(preparation, root):
    from vibeflow.tooling.application.project_targets import preparation_adapter
    values = []
    for path, prepared in preparation.workflows.items():
        if preparation.workspace.root_for_path(path) != root:
            continue
        facts = workflow_resource_facts(preparation.workspace, path, prepared)
        imports = preparation_adapter(root.project_target).resource_import_facts(
            preparation.workspace, root, prepared, source_owners(prepared),
            syntax_cache=preparation.syntax_caches.setdefault(root.project_target, {}), node_command=preparation.node_command)
        values.append({**facts, **imports})
    return tuple(values)


def collect_resource_uses(preparation, executions):
    values, findings, unavailable = {}, [], False
    facts_by_key = {workflow_identity(preparation.workspace,path): workflow_resource_facts(preparation.workspace,path,prepared)
                    for path,prepared in preparation.workflows.items()}
    for execution in executions:
        for result in execution.results.values():
            if result.state != "completed":
                unavailable = True
                findings.append(HealthFinding(rule_id="RESOURCE.RULE.UNAVAILABLE", severity="error", object_type="rule",
                    object_id="resource preparation", message="a selected governance Rule did not complete"))
                continue
            for record in result.records.values():
                if record.type_id != RESOURCE_USE_TYPE:
                    continue
                try:
                    expected = {key for key, facts in facts_by_key.items() if execution.scope.get("level") != "root"
                                or facts["root_id"] == execution.scope["id"]}
                    if set(record.value["workflows"]) != expected:
                        raise ValueError("resource use must cover exactly the workflows in its Rule scope")
                    for key, value in record.value["workflows"].items():
                        if "resources" not in value:
                            raise ValueError("resource use requires an explicit resources field")
                        use = ResourceUse(**value)
                        if use.workflow != key:
                            raise ValueError("resource use workflow identity does not match its key")
                        known = {(item["kind"],item["id"]) for item in facts_by_key[key]["resources"]}
                        if any((item["kind"],item["id"]) not in known for item in use.resources or ()):
                            raise ValueError(f"resource use references an unknown resource in {key}")
                        if key in values and values[key] != use:
                            raise ValueError(f"conflicting resource use records for {key}")
                        values[key] = use
                except (KeyError, TypeError, ValueError) as error:
                    unavailable = True
                    findings.append(HealthFinding(rule_id="RESOURCE.RECORD.INVALID", severity="error", object_type="rule",
                        object_id=RESOURCE_USE_TYPE, message=str(error)))
    for path, prepared in tuple(preparation.workflows.items()):
        key = workflow_identity(preparation.workspace, path)
        facts = workflow_resource_facts(preparation.workspace, path, prepared)
        planned = facts["planned"]
        annotations = tuple({"kind": "base_lib", "id": item["id"], "selection": item}
                            for item in facts["base_lib"] if item.get("status") != "planned")
        preparation.workflows[path] = replace(prepared, resource_use=None if unavailable else values.get(key, ResourceUse(key, planned=planned, annotations=annotations)))
    return tuple(findings)
