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
        declarations = facts.get("workflow", {}).get("workflow_targets", {})
        needed = {action.get("target") for policy in facts.get("call_policies", {}).values()
            for action in policy.get("actions", ()) if action.get("capability") == "vibeflow.workflow" and action.get("target")}
        for alias in needed:
            declaration = declarations.get(alias)
            if declaration is None:
                continue
            try:
                if workspace is None:
                    raise ValueError("target expansion requires project root metadata")
                root = workspace.root_by_id(declaration.get("root") or item["workflow"]["root_id"])
                path = (root.path / declaration["workflow"]).resolve()
                target = workflow_identity(path, workspace, target=root.project_target)
                declaration["identity"] = target["id"]
                if target["id"] in graphs:
                    continue
                if target["id"] in failures:
                    raise ValueError(failures[target["id"]])
                try:
                    prepared = (load_own_target(path, workspace)
                        if load_own_target is not None and root.project_target == architecture.get("project_target", "python")
                        else _load(path, workspace))
                except Exception as error:
                    failures[target["id"]] = str(error)
                    raise
                graphs[target["id"]] = {"workflow": target, "architecture": deepcopy(prepared)}
                pending.append(target["id"])
            except Exception as error:
                declaration["preview_error"] = str(error)
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
    """A synthetic single-project workspace must not hide a real enclosing workspace."""
    if workspace is not None and getattr(workspace, "path", None) is not None and workspace.path.name == "vibeflow_config.jsonc":
        return workspace
    from vibeflow.tooling.project.workspace_loader import load_workspace_config, find_project_config, load_project_workspace
    for directory in Path(config).resolve().parents:
        candidate = directory / "vibeflow_config.jsonc"
        if candidate.is_file():
            return load_workspace_config(candidate)
    if workspace is None:
        project = find_project_config(config)
        if project is not None:
            return load_project_workspace(project)
    return workspace
