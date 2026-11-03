"""Process and input-file drivers. No VibeFlow implementation imports belong here."""
from __future__ import annotations

import json
from contextlib import contextmanager
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import subprocess
import sys
from threading import Thread


ROOT = Path(__file__).resolve().parents[2]


def write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2), encoding="utf-8")
    return path


def command(*args, cwd: Path, success=True, env=None, timeout=120, stdin=None):
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    if env:
        for key, value in env.items():
            if value is None:
                environment.pop(key, None)
            else:
                environment[key] = str(value)
    result = subprocess.run([str(arg) for arg in args], cwd=cwd, env=environment,
        capture_output=True, text=True, encoding="utf-8", timeout=timeout, input=stdin)
    if success:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def cli(work: Path, *args, success=True, timeout=120):
    return command(sys.executable, "-B", "-m", "vibeflow", *args,
        cwd=work, success=success, timeout=timeout)


def checker_command(root: Path, profile="base", *args):
    return command(sys.executable, "-B", ROOT / "repo_check/run.py", "--root", root,
        "--profile", profile, "--format", "json", *args, cwd=ROOT, success=False,
        env={"PYTHONPATH":root / "src"}, timeout=30)


def example(work: Path, relative: str, toolchain: Path | None = None):
    """Copy a real example as an editable, isolated user workspace."""
    shutil.copytree(ROOT / "sandbox" / relative, work,
        ignore=shutil.ignore_patterns("__pycache__", "node_modules", "*.pyc", ".artifacts"))
    if toolchain:
        (work / "project/node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    return work


def workspace(work: Path, source: str, *, plugin: str | None = None):
    """Write ordinary SDK code and project configuration, never descriptors or IR."""
    write(work / "vibeflow_config.jsonc", {"roots":[{"id":"app","path":"app"}]})
    write(work / "project_rules.jsonc", {"rulesets":[]})
    write(work / "app/root_rules.jsonc", {"rulesets":[]})
    write(work / "app/vibeflow_project.jsonc", {"project_target":"python"})
    write(work / "app/nodes/tasks.py", source)
    if plugin is not None:
        write(work / "app/plugins/example/plugin.py", plugin)
    return work / "app"


def findings(result):
    """Read the command's normal JSON report (including nested phase reports)."""
    payload = json.loads(result.stdout)
    def visit(value):
        if isinstance(value, dict):
            if "code" in value and "message" in value:
                yield value
            else:
                for item in value.values():
                    yield from visit(item)
        elif isinstance(value, list):
            for item in value:
                yield from visit(item)
    return list(visit(payload))


@contextmanager
def serve(directory: Path):
    """Host ordinary application files on an ephemeral loopback port."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(directory)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
