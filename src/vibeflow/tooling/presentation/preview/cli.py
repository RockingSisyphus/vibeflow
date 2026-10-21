"""Target-neutral maintenance of generated local previews."""
import argparse
import json
from pathlib import Path

from .catalog import ensure_catalog, reindex
from ..viewer import install_page


def _default_root():
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    return load_project_workspace(Path.cwd()).root


def main(argv=None):
    parser = argparse.ArgumentParser(prog="vibeflow preview")
    parser.add_argument("--preview-root", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--reindex", action="store_true")
    args = parser.parse_args(argv)
    try:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        root = args.preview_root or (load_workspace_config(args.workspace).root if args.workspace else _default_root())
        install_page(root.resolve())
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
