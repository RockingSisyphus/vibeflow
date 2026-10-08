"""Read-only migration recheck; create all sample projects under a new /tmp root.

Run from the repository: PYTHONPATH=src python <this-file>
Outputs raw observations, without treating observed failures as acceptance.
"""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


REPO = Path(__file__).resolve().parents[3]


def cli(arguments):
    command = [sys.executable, "-m", "vibeflow", *arguments]
    result = subprocess.run(command, cwd=REPO, text=True, capture_output=True,
        timeout=30, env={**os.environ, "PYTHONPATH": str(REPO / "src"),
                        "PYTHONDONTWRITEBYTECODE": "1"})
    try:
        output = json.loads(result.stdout)
    except ValueError:
        output = result.stdout
    return {"command": command, "exit_code": result.returncode,
            "output": output, "stderr": result.stderr}


def main():
    work = Path(tempfile.mkdtemp(prefix="vibeflow-migration-recheck-"))
    observations = {"work": str(work), "layout": {}}
    for directory in ("ordinary", "nodes", "task_nodes", "custom_nodes", "base_lib", "plugins"):
        root = work / directory
        (root / directory).mkdir(parents=True)
        (root / "utility").mkdir()
        (root / directory / "worker.py").write_text(
            "from utility.math import add\ndef calculate():\n    return add(1,2)\n")
        (root / "utility/math.py").write_text("def add(a,b):\n    return a+b\n")
        (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python"}))
        workspace = root / "vibeflow_config.jsonc"
        workspace.write_text(json.dumps({"roots": [{"id": "main", "path": "."}]}))
        observations["layout"][directory] = {
            "workspace": cli(["quality-check", "--workspace", str(workspace), "--json"]),
            "path": cli(["quality-check", "--path", str(root), "--json"]),
        }

    host = work / "host"
    host.mkdir()
    project = host / "vibeflow_project.jsonc"
    project.write_text(json.dumps({"project_target": "javascript",
        "javascript": {"host_extensions": ["old.host"]}}))
    workspace = host / "vibeflow_config.jsonc"
    workspace.write_text(json.dumps({"roots": [{"id": "main", "path": "."}]}))
    config = host / "workflow.jsonc"
    config.write_text(json.dumps({"rulesets": [], "pipeline": {"nodes": [{
        "id": "input", "type_used": "vibeflow.io", "display_name": "Input",
        "description": "Receive native input", "requires": [],
        "provides": [{"key": "data.in", "type": "data.in", "display_name": "Input data"}],
        "io": {"operation": "receive", "port": "in"},
    }]}}))
    observations["host"] = {
        "preview": cli(["review-rules", "--config", str(config), "--json"]),
        "validate": cli(["validate", "--workspace", str(workspace), "--config", str(config), "--json"]),
    }

    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality import PythonSource
    from vibeflow.targets.python.quality.source_context import PythonSourceFile
    from vibeflow.targets.python.quality.rules.effects import no_side_effects
    text = 'def read():\n    return open("data.txt").read()\n'
    path = str(work / "ordinary.py")
    source = PythonSource("ordinary", "ordinary.py", path, text)
    parsed = PythonSourceFile(path, "ordinary", text, _tree=ast.parse(text))
    context = RuleContext(subject={"kind": "python_source"},
        facts={"python_source": source, "source_file": parsed})
    observations["project_effects"] = []
    for scope in ("none", "python_io", "terminal", "trusted"):
        result = no_side_effects(context, {}, {"effect_scope": scope, "policy": {}})
        observations["project_effects"].append({"scope": scope, "state": result.state,
            "codes": [item.code for item in result.findings],
            "effect_policy": dict(result.records["effect_policy"].value)})
    output = work / "observations.json"
    output.write_text(json.dumps(observations, ensure_ascii=False, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()
