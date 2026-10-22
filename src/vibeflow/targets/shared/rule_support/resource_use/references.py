"""Resource-reference policy over declared and Target-resolved relationships."""
from pathlib import PurePath
from dataclasses import replace
from collections import deque

from vibeflow.core.rules import RuleResult
from vibeflow.core.descriptors.resource_use import ResourceUse
from vibeflow.targets.shared.rule_support.governance import _finding
from .selection import workflows


def _allowed(source, target):
    return (source.get("plugin_id") and source["plugin_id"] == target.get("plugin_id")
        or (source["kind"], source["id"]) == (target["kind"], target["id"])
        or target["kind"] == "base_lib" and target["id"] in (*source.get("base_libs", ()), *source.get("dependencies", ())))


def references(context, inputs, params):
    findings = []
    for workflow in workflows(context):
        use = ResourceUse(**inputs["use"].value["workflows"][workflow["workflow"]])
        findings.extend(_declared(context, workflow, use))
        findings.extend(_imports(context, workflow, use))
    return RuleResult(findings=tuple(findings))


def _declared(context, workflow, use):
    resources = {(item["kind"], item["id"]): item for item in workflow["resources"]}
    pending = deque(tuple(item) for item in workflow["entry_resources"])
    pending.extend((item["kind"], item["id"]) for item in use.resources or () if item.get("reason") == "explicit")
    visited, findings = set(), []
    while pending:
        key = pending.popleft()
        if key in visited:
            continue
        visited.add(key)
        if not use.allows(*key):
            findings.append(_finding(context, "RESOURCE.REFERENCE.UNAVAILABLE",
                f"{key[0]} '{key[1]}' is unavailable in {workflow['workflow']}",
                workflow["path"], resource_id=key[1], resource_kind=key[0], workflow=workflow["workflow"]))
        resource = resources.get(key)
        if resource is None:
            continue  # The declaration resolver reports unknown Node/type identities.
        for identifier in (*resource["base_libs"], *(resource["dependencies"] if key[0] == "base_lib" else ())):
            target = ("base_lib", identifier)
            if target not in resources or not use.allows(*target):
                findings.append(_finding(context, "RESOURCE.REFERENCE.UNAVAILABLE",
                    f"{key[0]} '{key[1]}' requires unavailable BaseLib '{identifier}' in {workflow['workflow']}",
                    workflow["path"], resource_id=identifier, source_resource=key, workflow=workflow["workflow"]))
            pending.append(target)
    return findings


def _imports(context, workflow, use):
    owners = workflow.get("owners", ())
    paths, edges = {}, {}
    for owner in owners:
        paths.setdefault(owner["path"], []).append(owner)
    for edge in workflow.get("imports", ()):
        edges.setdefault(edge["path"], []).append(edge)
    entries = {tuple(item) for item in workflow["entry_resources"]}
    entries.update((item["kind"], item["id"]) for item in use.resources or () if item.get("reason") == "explicit")
    pending = deque(owner for owner in owners if (owner["kind"], owner["id"]) in entries)
    seen, findings = set(), []
    while pending:
        owner = pending.popleft()
        key = (owner["kind"], owner["id"], owner["path"], owner["symbol"])
        if key in seen:
            continue
        seen.add(key)
        for edge in edges.get(owner["path"], ()):
            lines = owner.get("import_lines")
            if edge.get("empty_package") or lines is not None and edge["line"] not in lines:
                continue
            targets = paths.get(edge["target"], ())
            named = [item for item in targets if item["symbol"] in edge.get("symbols", ())]
            targets = named or targets
            own = [item for item in targets if (item["kind"], item["id"]) == (owner["kind"], owner["id"])]
            targets = own or targets
            if not targets and owner.get("package_path") and PurePath(edge["target"]).is_relative_to(owner["package_path"]):
                targets = [{**owner, "path": edge["target"], "symbol": "", "role": "support", "import_lines": None}]
            permitted = [item for item in targets if _allowed(owner, item) and use.allows(item["kind"], item["id"])]
            if permitted:
                pending.extend(permitted)
            else:
                findings.append(replace(_finding(context, "RESOURCE.REFERENCE.UNAVAILABLE" if targets and any(not use.allows(item["kind"], item["id"]) for item in targets)
                    else "RESOURCE.REFERENCE.UNDECLARED",
                    f"{owner['kind']} '{owner['id']}' imports unavailable or undeclared project code: {edge['target']}",
                    edge["path"], resource_id=owner["id"], resource_kind=owner["kind"], imported_path=edge["target"], workflow=workflow["workflow"]),
                    source_location={"path":edge["path"], "line":edge["line"], "column":edge.get("column",1)}))
    return findings
