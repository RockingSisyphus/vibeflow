"""Explicit project/root fixtures for tests whose subject is workflow behavior."""
import json
from pathlib import Path


def project_root(directory, target="python"):
    directory = Path(directory)
    root = directory / "project"
    root.mkdir(parents=True, exist_ok=True)
    (directory / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}))
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": target}))
    # These fixtures test the workflow/source layer. Governance defaults have
    # dedicated projects; selecting no optional root checks isolates the subject.
    (root / "root_rules.jsonc").write_text('{"rulesets":[]}')
    return root


def register_root(root, target="python"):
    """Register an already chosen fixture root in its separate parent project."""
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Fixtures may register Architecture before writing its workflow, so inspect
    # only topology here; product loading validates the completed project later.
    registered = False
    for parent in root.parents:
        config = parent / "vibeflow_config.jsonc"
        if config.is_file():
            from vibeflow.tooling.project.config_loader import load_raw_config_document
            data = load_raw_config_document(config).data
            registered = any(root.is_relative_to((parent / item["path"]).resolve())
                             for item in data["roots"])
            break
    if not registered:
        (root.parent / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": root.name, "path": root.name}]}))
        (root.parent / "project_rules.jsonc").write_text('{"rulesets":[]}')
    if not (root / "vibeflow_project.jsonc").exists():
        (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": target}))
    if not (root / "root_rules.jsonc").exists():
        (root / "root_rules.jsonc").write_text('{"rulesets":[]}')
