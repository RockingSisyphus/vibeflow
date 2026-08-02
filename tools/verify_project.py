#!/usr/bin/env python3
"""Run the reproducible VibeFlow repository verification gate."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
TEST_GROUPS = (
    "tests/core",
    "tests/block_compiler",
    "tests/targets",
    "tests/tooling",
    "tests/conformance",
    "tests/integration",
)


class VerificationError(RuntimeError):
    """A verification step could not complete successfully."""


@dataclass(frozen=True)
class Step:
    name: str
    action: Callable[[Path], None]


def _environment(
    overrides: dict[str, str | None] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    source = str(ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source if not existing else os.pathsep.join((source, existing))
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key, value in (overrides or {}).items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    return environment


def _run(
    command: Sequence[str | Path],
    *,
    cwd: Path = ROOT,
    overrides: dict[str, str | None] | None = None,
) -> None:
    normalized = tuple(str(item) for item in command)
    print(f"$ {shlex.join(normalized)}", flush=True)
    subprocess.run(
        normalized,
        cwd=cwd,
        env=_environment(overrides),
        check=True,
    )


def _repository_quality(_scratch: Path) -> None:
    _run((PYTHON, "quality/run.py", "--profile", "all"))


def _compileall(scratch: Path) -> None:
    compile_root = scratch / "compile-source"
    ignored = shutil.ignore_patterns(
        "__pycache__",
        ".pytest_cache",
        ".artifacts",
        "node_modules",
        "*.pyc",
        "*.pyo",
    )
    for name in ("src", "tests", "sandbox", "quality", "tools", "distribution"):
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, compile_root / name, ignore=ignored)
    _run(
        (PYTHON, "-m", "compileall", "-q", str(compile_root)),
        cwd=compile_root,
        overrides={"PYTHONPATH": None},
    )


def _pytest(scratch: Path) -> None:
    paths = tuple(ROOT / item for item in TEST_GROUPS if (ROOT / item).exists())
    if not paths:
        paths = (ROOT / "tests",)
    work_root = scratch / "pytest-work"
    work_root.mkdir(parents=True, exist_ok=True)
    _run(
        (PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths),
        cwd=work_root,
    )


def _python_sandbox(_scratch: Path) -> None:
    _run((PYTHON, "sandbox/python/integration/run_all.py"))


def _javascript_minimal(_scratch: Path) -> None:
    _run((PYTHON, "sandbox/javascript/minimal/run_e2e.py"))


def _javascript_integration(_scratch: Path) -> None:
    _run((PYTHON, "sandbox/javascript/integration/run_all.py"))


def _venv_python(root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return root / relative


def _wheel_smoke(scratch: Path) -> None:
    source_root = scratch / "wheel-source"
    package_root = source_root / "src" / "vibeflow"
    package_root.parent.mkdir(parents=True)
    shutil.copytree(
        ROOT / "src" / "vibeflow",
        package_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for name in ("pyproject.toml", "LICENSE"):
        shutil.copy2(ROOT / name, source_root / name)

    wheel_root = scratch / "wheel-dist"
    _run(
        (PYTHON, "-m", "build", "--wheel", "--outdir", wheel_root),
        cwd=source_root,
        overrides={"PYTHONPATH": None},
    )
    wheels = sorted(wheel_root.glob("vibeflow-*.whl"))
    if len(wheels) != 1:
        raise VerificationError(
            f"wheel build produced {len(wheels)} matching artifacts"
        )

    environment_root = scratch / "wheel-venv"
    _run((PYTHON, "-m", "venv", environment_root))
    isolated = _venv_python(environment_root)
    _run(
        (isolated, "-m", "pip", "install", "--no-deps", wheels[0]),
        overrides={"PYTHONPATH": None},
    )
    probe = "\n".join(
        (
            "from importlib.resources import files",
            "import vibeflow",
            "assert tuple(getattr(vibeflow, '__all__', ())) == ()",
            "from vibeflow.core import GraphConfig",
            "from vibeflow.block_compiler import WorkflowPlan",
            "from vibeflow.targets.python.project import NodeRegistry",
            "from vibeflow.targets.python.runtime import PipelineRuntime",
            "from vibeflow.targets.javascript import WorkflowSpec",
            "from vibeflow.tooling.project.config_loader import load_config_document",
            "root = files('vibeflow')",
            "for name in ('config.schema.json', 'health_report.schema.json', 'node.schema.json', 'nodeset.schema.json', 'policy.schema.json'):",
            "    assert root.joinpath('tooling/project/schema', name).is_file()",
            "for name in ('runtime_helpers.mjs', 'toolchain_driver.mjs'):",
            "    assert root.joinpath('targets/javascript/resources', name).is_file()",
            "for removed in ('aot', 'runtime', 'portable', 'config', 'health', 'purity', 'devtools', 'rendering', 'workspace'):",
            "    assert not root.joinpath(removed).is_dir(), removed",
        )
    )
    _run((isolated, "-c", probe), overrides={"PYTHONPATH": None})
    _run((isolated, "-m", "vibeflow", "--help"), overrides={"PYTHONPATH": None})


def _distribution_smoke(scratch: Path) -> None:
    output = scratch / "distribution"
    _run(
        (PYTHON, "distribution/build.py", "--output", output),
        overrides={"PYTHONPATH": None},
    )
    launcher = output / "run.py"
    _run((PYTHON, launcher, "verify-kernel"), overrides={"PYTHONPATH": None})

    packaged_fixture = output / "sandbox" / "javascript" / "integration"
    fixture = scratch / "distribution-sandbox-runtime"
    shutil.copytree(
        packaged_fixture,
        fixture,
        ignore=shutil.ignore_patterns(
            "node_modules",
            "__pycache__",
            "*.pyc",
            "*.pyo",
            ".artifacts",
        ),
    )
    _run(("npm", "ci"), cwd=fixture / "project", overrides={"PYTHONPATH": None})
    aot_output = scratch / "distribution-aot"
    _run(
        (
            PYTHON,
            launcher,
            "build",
            "--workspace",
            fixture / "vibeflow_config.jsonc",
            "--config",
            fixture / "project/configs/linear.jsonc",
            "--target",
            "node",
            "--profile",
            "single-esm",
            "--out-dir",
            aot_output,
        ),
        overrides={"PYTHONPATH": None},
    )
    script = """
const { pathToFileURL } = await import("node:url");
const workflow = await import(pathToFileURL(process.env.VF_ENTRY).href);
const result = await workflow.runWorkflow({ x: 10, a: 8, b: 3 });
if (result.result !== 15) throw new Error(JSON.stringify(result));
process.stdout.write(JSON.stringify(result));
""".strip()
    _run(
        ("node", "--input-type=module", "--eval", script),
        overrides={
            "PYTHONPATH": None,
            "VF_ENTRY": str(aot_output / "index.js"),
        },
    )


def _clean_tree_check(_scratch: Path) -> None:
    command = (PYTHON, "tools/clean_workspace.py")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"$ {shlex.join(command)}", flush=True)
    print(completed.stdout, end="")
    if completed.returncode:
        print(completed.stderr, end="", file=sys.stderr)
        raise VerificationError("workspace cleanup preview was refused")
    if "cleanup targets: 0" not in completed.stdout:
        raise VerificationError("verification left repository artifacts behind")


def _steps(*, full: bool) -> tuple[Step, ...]:
    base = (
        Step("repository-quality", _repository_quality),
        Step("compileall", _compileall),
        Step("pytest", _pytest),
    )
    if not full:
        return base
    return (
        *base,
        Step("python-sandbox", _python_sandbox),
        Step("javascript-minimal", _javascript_minimal),
        Step("javascript-integration", _javascript_integration),
        Step("wheel-isolation", _wheel_smoke),
        Step("distribution", _distribution_smoke),
        Step("repository-quality-final", _repository_quality),
        Step("clean-tree", _clean_tree_check),
    )


def _run_steps(steps: Sequence[Step], *, scratch: Path) -> None:
    for index, step in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {step.name}", flush=True)
        try:
            step.action(scratch)
        except (OSError, subprocess.CalledProcessError, VerificationError) as exc:
            raise VerificationError(f"{step.name} failed: {exc}") from exc
        print(f"PASS: {step.name}", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="include Sandboxes and packaging")
    parser.add_argument(
        "--scratch",
        type=Path,
        help="use an explicit ignored scratch directory instead of a temporary one",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.scratch is not None:
            scratch = args.scratch.resolve()
            scratch.mkdir(parents=True, exist_ok=True)
            _run_steps(_steps(full=args.full), scratch=scratch)
        else:
            with tempfile.TemporaryDirectory(prefix="vibeflow-verify-") as raw:
                _run_steps(_steps(full=args.full), scratch=Path(raw))
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("VibeFlow verification: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
