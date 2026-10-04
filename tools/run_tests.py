#!/usr/bin/env python3
"""Run VibeFlow pytest suites in an isolated, disposable work directory.

Tests are allowed to exercise the real runtime.  Some programmatic Runtime
calls intentionally use the public default ``runs/vibeflow`` location, so the
test process must never use the repository as its working directory.  This
entrypoint also prevents user-site packages and ambient pytest plugins from
affecting repository verification.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

if __package__:
    from .test_parallel import DEFAULT_WORKERS, WORKER_ENVIRONMENT, add_worker_argument
else:
    from test_parallel import DEFAULT_WORKERS, WORKER_ENVIRONMENT, add_worker_argument


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DEFAULT_TEST_PATHS = (ROOT / "tests",)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument(
        "--scratch",
        type=Path,
        help="caller-owned temporary directory; omitted to create and remove one automatically",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="arguments forwarded to pytest; place them after '--'",
    )
    return parser


def _environment(*, toolchain_root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    # Do not inherit a caller's project checkout or user packages into a
    # framework verification process.
    environment["PYTHONPATH"] = os.pathsep.join((str(ROOT / "src"), str(ROOT / "tools")))
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["VIBEFLOW_TEST_TOOLCHAIN_ROOT"] = str(toolchain_root)
    environment.pop("PYTEST_ADDOPTS", None)
    environment.pop("PYTEST_PLUGINS", None)
    return environment


def _prepare_toolchain(scratch: Path, *, environment: dict[str, str]) -> Path:
    toolchain_root = scratch / "javascript-toolchain"
    toolchain_root.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(ROOT / "sandbox/javascript/minimal/project" / name, toolchain_root / name)
    subprocess.run(("npm", "ci"), cwd=toolchain_root, env=environment, check=True)
    return toolchain_root


def _resolve_paths(arguments: list[str]) -> list[str]:
    if not arguments:
        return [str(path) for path in DEFAULT_TEST_PATHS]
    resolved: list[str] = []
    for argument in arguments:
        candidate = Path(argument)
        repository_candidate = ROOT / candidate
        if not argument.startswith("-") and not candidate.is_absolute() and repository_candidate.exists():
            resolved.append(str(repository_candidate.resolve()))
        else:
            resolved.append(argument)
    return resolved


def run_tests(scratch: Path, pytest_args: list[str], *, workers: int = DEFAULT_WORKERS) -> int:
    scratch.mkdir(parents=True, exist_ok=True)
    bootstrap_environment = _environment(toolchain_root=scratch / "javascript-toolchain")
    toolchain_root = _prepare_toolchain(scratch, environment=bootstrap_environment)
    work_root = scratch / "work"
    work_root.mkdir()
    environment = _environment(toolchain_root=toolchain_root)
    environment[WORKER_ENVIRONMENT] = str(workers)
    environment["VIBEFLOW_PYTEST_WORK_ROOT"] = str(work_root)
    parallel = workers > 1 and not any(value in {"--collect-only", "--co", "--help", "-h", "--version"} for value in pytest_args)
    command = (
        PYTHON,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p", "pytest_workdirs",
        *(("-p", "xdist.plugin", "-n", str(workers), "--dist", "loadfile") if parallel else ()),
        *_resolve_paths(pytest_args),
    )
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=work_root,
        env=environment,
        check=False,
    ).returncode


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    pytest_args = list(args.pytest_args)
    if pytest_args[:1] == ["--"]:
        pytest_args.pop(0)
    if args.scratch is not None:
        return run_tests(args.scratch.resolve(), pytest_args, workers=args.workers)
    with tempfile.TemporaryDirectory(prefix="vibeflow-pytest-") as temporary:
        return run_tests(Path(temporary), pytest_args, workers=args.workers)


if __name__ == "__main__":
    raise SystemExit(main())
