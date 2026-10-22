"""Prepare declared target facts once for this snapshot, never from history."""
from copy import deepcopy
from pathlib import Path
import json
import os
import subprocess
import sys


def prepare_targets(architecture, *, config, workspace, load_own_target=None):
    from vibeflow.tooling.presentation.preview.exporter import workflow_identity
    current = workflow_identity(config, workspace, target=architecture.get("project_target", "python"))
    graphs = {current["id"]: {"workflow": current, "architecture": deepcopy(architecture)}}
    pending = [current["id"]]
    failures = {}
    while pending:
        identity = pending.pop()
        item = graphs[identity]
        facts = item["architecture"]
        from vibeflow.core.workflows.references import action_references
        references = {json.dumps(ref, sort_keys=True):ref for policy in facts.get("call_policies", {}).values()
            for action in policy.get("actions", ()) for ref in action_references(action)}
        for reference in references.values():
            target_id = reference["root"] + ":" + reference["path"]
            if target_id in graphs:
                continue
            try:
                root = workspace.root_by_id(reference["root"])
                path = (root.path / reference["path"]).resolve()
                target = workflow_identity(path, workspace, target=root.project_target)
                prepared = (load_own_target(path, workspace)
                    if load_own_target is not None and root.project_target == architecture.get("project_target", "python")
                    else _load(path, workspace))
                graphs[target_id] = {"workflow":target, "architecture":deepcopy(prepared)}
                pending.append(target_id)
            except Exception as error:
                graphs[target_id] = {"workflow":{"id":target_id,"root_id":reference["root"],"path":reference["path"],"name":reference["path"]}, "error":str(error)}
    primary = graphs.pop(current["id"])
    return primary["architecture"], graphs


def _load(path, workspace):
    """Cross-Target facts cross the CLI boundary as JSON, including zip installs."""
    from vibeflow.tooling.project.config_loader import strip_jsonc_comments
    command = [sys.executable, "-B", "-m", "vibeflow", "export-architecture", "--config", str(path)]
    if workspace.path.name == "vibeflow_config.jsonc" and workspace.path.is_file():
        command += ["--workspace", str(workspace.path)]
    environment = os.environ.copy()
    package_root = str(Path(__file__).parents[3])
    environment["PYTHONPATH"] = os.pathsep.join(filter(None, (package_root, environment.get("PYTHONPATH"))))
    result = subprocess.run(command, env=environment, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise ValueError("target facts unavailable: " + (result.stderr or result.stdout).strip())
    return json.loads(strip_jsonc_comments(result.stdout))


def preview_workspace(config, workspace=None):
    """Use the same registered project boundary as compilation and execution."""
    if workspace is not None:
        if workspace.root_for_path(Path(config).resolve()) is None:
            from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
            raise WorkspaceConfigError("WORKSPACE.ROOT.UNREGISTERED",
                f"path does not belong to a registered root: {config}", {"path": str(config)})
        return workspace
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    return load_project_workspace(config)
