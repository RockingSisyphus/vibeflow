"""Target-neutral maintenance of generated local previews."""
import argparse
import json
from pathlib import Path

from .catalog import ensure_catalog, reindex
from ..viewer import install_page



def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibeflow preview")
    parser.add_argument("--preview-root", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args(argv)
    try:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        from vibeflow.tooling.project.workspace_loader import load_project_workspace
        workspace = load_workspace_config(args.workspace) if args.workspace else (
            None if args.preview_root else load_project_workspace(Path.cwd()))
        root = args.preview_root or workspace.root
        install_page(root.resolve())
        if workspace is not None:
            from vibeflow.tooling.project.preparation import ProjectPreparation
            ProjectPreparation(workspace).review(write_architecture=True)
            from .exporter import publish_project
            publish_project(root, workspace)
        if args.reindex:
            result = reindex(root)
        else:
            ensure_catalog(root)
            result = {"output": str(root.resolve() / "vibeflow-preview.html")}
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("errors") else 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False))
        return 1
