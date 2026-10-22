"""Workflow-local declaration facts, with no resource-use policy."""
from pathlib import Path

from vibeflow.core.descriptors.contributions import RESOURCE_GROUPS, resource_kind
from vibeflow.core.descriptors.source_bundle import ownership_resources
from vibeflow.core.descriptors.source_members import source_owners


def workflow_identity(workspace, path):
    path = Path(path).resolve()
    root = workspace.root_for_path(path)
    return root.id + ":" + path.relative_to(root.path).as_posix()


def workflow_resource_facts(workspace, path, prepared):
    root = workspace.root_for_path(path)
    catalogs = prepared.catalogs
    candidates = {(kind, descriptor.id): (descriptor, catalogs.origins.get((group, descriptor.id)))
                  for kind, group in RESOURCE_GROUPS.items() for descriptor in getattr(catalogs, group)}
    # Discovery retains uncalled Nodes without resolving their unused NodeTypes.
    # Include those declarations as facts; binding remains reference-driven.
    for entry in prepared.resource_inventory:
        candidates.setdefault((resource_kind(entry.descriptor), entry.descriptor.id), (entry.descriptor, entry.origin))
    resources = [{"kind": kind, "id": identifier,
        "owner": origin.owner.to_dict() if origin else {}, "path": origin.path if origin else "",
        "base_libs": tuple(getattr(descriptor, "base_libs", ())),
        "dependencies": tuple(getattr(descriptor, "dependencies", ()))}
        for (kind, identifier), (descriptor, origin) in candidates.items()]
    for kind, descriptor in ownership_resources(catalogs):
        if kind == "plugin_declaration":
            record = next(item for item in prepared.records if item["id"] == descriptor.id)
            resources.append({"kind": kind, "id": descriptor.id,
                "owner": {"kind": "plugin", "id": descriptor.id, "root_id": record.get("root", ""),
                          "path": record["package_path"]},
                "path": record["package_path"], "base_libs": descriptor.base_libs, "dependencies": ()})
    document = prepared.document.data
    raw = document.get("base_lib", {})
    selections = tuple({"id": item} if isinstance(item, str) else dict(item)
                       for item in raw.get("modules", ())) if raw else ()
    from vibeflow.core.rules.planning import graph_rule_subjects
    nodes = {node.definition_id for subject in graph_rule_subjects(prepared.graph) for node in subject.graph.nodes
             if node.status != "planned"}
    entries = [("node", item.id) for item in catalogs.nodes if item.id in nodes]
    entries.extend(("plugin", item.id) for item in catalogs.plugins)
    entries.extend(("plugin_declaration", item["id"]) for item in prepared.records if item.get("loaded"))
    return {"workflow": workflow_identity(workspace, path), "path": str(path), "root_id": root.id,
        "entry_resources": tuple(entries),
        "resources": tuple(resources), "base_lib": selections,
        "plugins": tuple(item["id"] for item in prepared.records if item.get("loaded")),
        "planned": tuple({"kind": "base_lib", **item} for item in selections if item.get("status") == "planned")}

