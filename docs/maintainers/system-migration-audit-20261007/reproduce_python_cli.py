"""Reproduce directory-role conflicts through the current official CLI.

Only copies sandbox inputs into a newly created /tmp directory. Product source
and existing project inputs are not modified. Each CLI call has a fresh process.
"""

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys
import tempfile


REPOSITORY = Path(__file__).resolve().parents[3]
SOURCE = REPOSITORY / "sandbox/resources/python"


def fixture(work: Path, name: str, module: str, placement: str) -> Path:
    root = work / name
    shutil.copytree(SOURCE, root, ignore=shutil.ignore_patterns(
        "ARCHITECTURE*", "__pycache__", "reports", "runs", "node_modules"))
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}\n')
    package = root / module
    package.mkdir()
    (package / "__init__.py").write_text("")
    for file in ("math_resource.py", "math_support.py"):
        shutil.move(str(root / file), str(package / file))
    library = package / "math_resource.py"
    library.write_text(library.read_text().replace(
        "from math_support import", "from .math_support import"))
    statement = f"from {module}.math_resource import increment"
    for file in ("node_resource.py", "plugin.py"):
        path = root / file
        path.write_text(path.read_text().replace(
            "from math_resource import increment", statement))
    if placement == "method":
        path = root / "node_resource.py"
        path.write_text(path.read_text().replace(statement + "\n", "").replace(
            '    def run_pure(self, inputs, params):\n        return {"result":',
            f'    def run_pure(self, inputs, params):\n        {statement}\n'
            '        return {"result":'))
    return root


def validate(work: Path, root: Path, case: str) -> dict:
    command = [sys.executable, "-m", "vibeflow", "validate",
               "--workspace", str(root / "vibeflow_config.jsonc"),
               "--config", str(root / "workflow.jsonc"), "--json"]
    result = subprocess.run(command, text=True, capture_output=True, check=False,
                            timeout=30, cwd=REPOSITORY, env={**os.environ,
                            "PYTHONPATH": str(REPOSITORY / "src"),
                            "PYTHONDONTWRITEBYTECODE": "1"})
    (work / (case + ".stdout.json")).write_text(result.stdout)
    (work / (case + ".stderr.txt")).write_text(result.stderr)
    data = json.loads(result.stdout)
    observation = {"exit_code": result.returncode, "status": data.get("status"),
                   "errors": [{"code": item.get("code", item.get("rule_id")),
                               "definition_id": item.get("definition_id"),
                               "message": item.get("message"),
                               "location": item.get("source_location")}
                              for item in data.get("errors", [])]}
    print(case, observation["status"], [item["code"] for item in observation["errors"]])
    return observation


def main() -> None:
    work = Path(tempfile.mkdtemp(prefix="vibeflow-system-migration-probe-"))
    observations = {}
    for placement in ("top", "method"):
        for module in ("ordinary", "base_lib", "boundary", "nodes", "runtime"):
            case = placement + "-" + module
            root = fixture(work, case, module, placement)
            observations[case] = validate(work, root, case)
    for support in ("parts", "runtime", "nodes", "plugins"):
        case = "support-" + support
        root = fixture(work, case, "ordinary", "method")
        package = root / "ordinary"
        folder = package / support
        folder.mkdir()
        (folder / "__init__.py").write_text("")
        shutil.move(str(package / "math_support.py"), str(folder / "math_support.py"))
        library = package / "math_resource.py"
        library.write_text(library.read_text().replace(
            "from .math_support import add", f"from .{support}.math_support import add"
        ).replace('implementation_files=["math_support.py"]',
                  f'implementation_files=["{support}/math_support.py"]'))
        observations[case] = validate(work, root, case)
    path = work / "summary.json"
    path.write_text(json.dumps(observations, ensure_ascii=False, indent=2) + "\n")
    print("Saved observations:", path)


if __name__ == "__main__":
    main()
