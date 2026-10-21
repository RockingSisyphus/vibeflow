"""One operation's project inventory, without importing business resources."""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Mapping
from vibeflow.core.rules.models import readonly

from vibeflow.tooling.project.config_loader import ConfigLoadError, load_raw_config_document
from vibeflow.tooling.project.document_kinds import is_architecture_document_text


@dataclass(frozen=True)
class WorkflowDocument:
    root_id: str
    path: Path
    data: Mapping


@dataclass(frozen=True)
class InventoryIssue:
    root_id: str
    path: Path
    code: str
    message: str


@dataclass(frozen=True)
class ProjectInventory:
    workspace: object
    workflows: tuple[WorkflowDocument, ...]
    issues: tuple[InventoryIssue, ...]
    directories: Mapping
    entries: Mapping

    def for_root(self, root_id):
        return tuple(item for item in self.workflows if item.root_id == root_id)

    @property
    def complete(self):
        return not self.issues


def workflow_candidates(root):
    paths = {item.workflow_path.resolve() for item in root.architecture_documents}
    metadata = {"vibeflow_project.jsonc", "root_rules.jsonc", "vibeflow_config.jsonc", "project_rules.jsonc"}
    paths.update(path.resolve() for path in root.path.iterdir()
                 if path.is_file() and path.suffix.lower() in {".json", ".jsonc"} and path.name not in metadata)
    directory = root.path / "configs"
    if directory.is_dir():
        paths.update(path.resolve() for path in directory.rglob("*")
                     if path.is_file() and path.suffix.lower() in {".json", ".jsonc"})
    documents = {item.document_path.resolve() for item in root.architecture_documents}
    return tuple(sorted(path for path in paths if path not in documents))


def inventory_root(root):
    workflows, issues = [], []
    declared = {item.workflow_path.resolve() for item in root.architecture_documents}
    for path in workflow_candidates(root):
        intended = path in declared or path.is_relative_to(root.path / "configs")
        text = ""
        try:
            text = path.read_text(encoding="utf-8")
            if path not in declared and is_architecture_document_text(text):
                continue
            document = load_raw_config_document(path)
            if isinstance(document.data.get("pipeline"), Mapping) and "type_key" not in document.data:
                workflows.append(WorkflowDocument(root.id, path, document.data))
            elif path in declared or "type_key" not in document.data and (intended or "pipeline" in document.data):
                issues.append(InventoryIssue(root.id, path, "PROJECT.INVENTORY.DOCUMENT",
                    "workflow documents must declare an object pipeline without type_key; registered workflows cannot be NodesetTypes"))
        except (OSError, ValueError) as error:
            code = error.rule_id if isinstance(error, ConfigLoadError) else "PROJECT.INVENTORY.READ"
            # A textual hint recovers malformed workflows only. Valid input
            # objects/arrays may contain nested keys named pipeline.
            if not intended and (code == "CONFIG.ROOT_OBJECT" or not re.search(r'"pipeline"\s*:', text)):
                continue
            issues.append(InventoryIssue(root.id, path, code, str(error)))
    return tuple(workflows), tuple(issues)


def inventory_project(workspace, *, root_ids=None):
    from vibeflow.tooling.project.workspace_model import WorkspaceConfig
    workflows, issues = [], []
    directories = {"project": tuple(sorted(path.name for path in workspace.root.iterdir() if path.is_dir())), "roots": {}}
    for root in workspace.roots:
        if root_ids is not None and root.id not in root_ids:
            continue
        directories["roots"][root.id] = tuple(sorted(path.name for path in root.path.iterdir() if path.is_dir()))
        found, failed = inventory_root(root)
        workflows.extend(item for item in found if WorkspaceConfig.root_for_path(workspace, item.path) == root)
        issues.extend(item for item in failed if WorkspaceConfig.root_for_path(workspace, item.path) == root)
    entries = {"project": directory_entries(workspace.root, excluded=tuple(root.path for root in workspace.roots)),
               "roots": {root.id: directory_entries(root.path) for root in workspace.roots
                         if root_ids is None or root.id in root_ids}}
    return ProjectInventory(workspace, tuple(workflows), tuple(issues), readonly(directories), readonly(entries))


# Dependency installations and generated histories are listed, not traversed.
UNSCANNED_DIRECTORIES = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__",
                                  "runs", "vibeflow-preview", ".pytest_cache"})


def directory_entries(directory, *, excluded=()):
    import os
    entries = []
    excluded = {path.resolve() for path in excluded}
    for parent, names, files in os.walk(directory, followlinks=False):
        base = Path(parent)
        for name in sorted(names):
            path = base / name
            traverse = name not in UNSCANNED_DIRECTORIES and path.resolve() not in excluded and not path.is_symlink()
            entries.append({"path": path.relative_to(directory).as_posix(), "kind": "directory", "traversed": traverse})
        names[:] = sorted(name for name in names if name not in UNSCANNED_DIRECTORIES
                          and (base / name).resolve() not in excluded and not (base / name).is_symlink())
        entries.extend({"path": (base / name).relative_to(directory).as_posix(), "kind": "file"} for name in sorted(files))
    return tuple(entries)
