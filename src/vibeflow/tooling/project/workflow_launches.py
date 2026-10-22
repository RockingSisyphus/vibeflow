"""Prepare node-owned launch declarations for a source service or deployment."""
import json
from pathlib import Path
from vibeflow.core.flow import STATUS_PLANNED
from vibeflow.core.graph_calls import graph_call_subjects
from vibeflow.core.workflows.references import workflow_reference, launch_configuration, workflow_node_params


def graph_launches(graph, catalogs, *, root, global_config=None, effective_params=None):
    launches = []
    caller = {"root":root.id, "path":Path(graph.source_path).resolve().relative_to(root.path).as_posix()}
    for subject in graph_call_subjects(graph, global_config=global_config):
        for node in subject.graph.nodes:
            if node.status == STATUS_PLANNED:
                continue
            descriptor = catalogs.nodes.get(node.definition_id)
            if not any(req.id == "vibeflow.workflow" and "call" in req.operations for req in getattr(descriptor, "capabilities", ())):
                continue
            params = (effective_params or {}).get((*subject.call_path, node.id), workflow_node_params(node, descriptor, subject))
            launches.append({"workflow":workflow_reference(params.get("workflow"), root=root.id),
                "launch":launch_configuration(params.get("launch")), "base":str(root.path), "caller":caller})
    return launches


def source_launches(workspace, *, preparation=None, config=None):
    from .preparation import ProjectPreparation
    preparation = preparation or ProjectPreparation(workspace)
    result = []
    for document in preparation.inventory.workflows:
        if config is not None and document.path != Path(config).resolve():
            continue
        prepared = preparation.workflow_resources(document.path)
        result.extend(graph_launches(prepared.graph, prepared.catalogs, root=workspace.root_by_id(document.root_id),
            global_config=prepared.document.data.get("global_config", {})))
    return result


def write_bundle_launches(destination, launches, *, base=".", workflow=None):
    """Save portable declarations, not source-discovery instructions."""
    from vibeflow.tooling.file_io import atomic_write
    from vibeflow.core.workflows.references import launch_document
    value = launch_document(launches, base=base, workflow=workflow)
    atomic_write(Path(destination)/"workflow-launches.json", json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def bundle_launches(path):
    path = Path(path).resolve()
    value = json.loads((path/"workflow-launches.json").read_text())
    if value.get("format") != "vibeflow.workflow-launches.v1":
        raise ValueError("unsupported workflow launch declarations; rebuild the bundle")
    return [{**item, "base":str(path/item["base"])} for item in value["launches"]]
