"""Fresh-process public entry points and comparable sandbox observations."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[3]


def environment(kernel: Path, **extra) -> dict[str, str]:
    source = kernel / "src" if (kernel / "src/vibeflow").is_dir() else kernel
    env = {**os.environ, "PYTHONPATH": str(source), "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    for name in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(name, None)
    env.setdefault("npm_config_cache", str(Path(os.environ.get("TMPDIR",tempfile.gettempdir())) / "vibeflow-npm-cache"))
    env.update({str(key): str(value) for key, value in extra.items() if value is not None})
    return env


def run_command(project: Path, command, kernel: Path, *, name="observation", env=None,
                timeout=180, toolchain=None, renderer=None):
    project.mkdir(parents=True, exist_ok=True)
    overrides = dict(env or {})
    if toolchain:
        overrides["VIBEFLOW_TEST_TOOLCHAIN_ROOT"] = str(toolchain)
    if renderer:
        overrides["VIBEFLOW_MERMAID_RENDERER_ROOT"] = str(renderer)
    started = perf_counter()
    completed = subprocess.run(list(map(str, command)), cwd=project,
        env=environment(kernel, **overrides), capture_output=True, text=True, timeout=timeout)
    stdout_path, stderr_path = project / (name + ".stdout.txt"), project / (name + ".stderr.txt")
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = None
    return {"exit_code": completed.returncode, "stdout": completed.stdout,
        "stderr": completed.stderr, "payload": payload, "error": None,
        "status": payload.get("status") if isinstance(payload, dict) else None,
        "seconds": perf_counter() - started, "command": list(map(str, command)),
        "stdout_path": str(stdout_path), "stderr_path": str(stderr_path)}


def run_cli(project: Path, args, kernel: Path, **options):
    return run_command(project, [sys.executable, "-B", "-m", "vibeflow", *args], kernel, **options)


def run_probe(project: Path, source, kernel: Path, *, args=(), name="probe", **options):
    if isinstance(source, Path):
        script = source.resolve()
    else:
        project.mkdir(parents=True, exist_ok=True)
        script = project / (name + ".py")
        script.write_text(source, encoding="utf-8")
    return run_command(project, [sys.executable, "-B", script, *args], kernel, name=name, **options)


def _mismatches(expected, actual, path=""):
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or 'result'} is not an object"]
        return [message for key, value in expected.items()
                for message in _mismatches(value, actual.get(key), f"{path}.{key}".strip("."))]
    return [] if expected == actual else [f"{path}: expected {expected!r}, got {actual!r}"]


def row(identifier, theme, title, expected, actual, failures=None, project=None):
    differences = _mismatches(expected, actual) if failures is None else list(failures)
    return {"id": identifier, "theme": theme, "title": title, "expected": expected,
            "actual": actual, "matched": not differences, "failures": differences,
            "artifact_root": str(project) if project else ""}


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
