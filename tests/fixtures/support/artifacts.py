"""One declared output tree for sandbox builds, runs, and observations."""
import json
from pathlib import Path


def artifact_directory(workspace):
    from vibeflow.tooling.project.config_loader import load_raw_config_document
    workspace = Path(workspace)
    config = workspace / "project_rules.jsonc"
    data = load_raw_config_document(config).data if config.exists() else {}
    directories = data.setdefault("rule_params", {}).setdefault("vibeflow.project.layout", {}).setdefault("directories", [])
    if not any(item.get("path") == "artifacts" for item in directories):
        directories.append({"path": "artifacts", "purpose": "Sandbox generated builds, execution records and observations"})
        config.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    output = workspace / "artifacts"
    output.mkdir(exist_ok=True)
    return output
