#!/usr/bin/env python3
"""Run repository checks and the single user-behavior acceptance suite."""
from __future__ import annotations
import argparse
from collections.abc import Callable,Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.dont_write_bytecode=True
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from tools.test_parallel import DEFAULT_WORKERS,add_worker_argument
from tools.pytest_workdirs import external_scratch
PYTHON=sys.executable

class VerificationError(RuntimeError):
    """An actual check failed; independent checks can still continue."""

@dataclass(frozen=True)
class Step:
    name:str
    action:Callable[[Path],None]


def _run(command,cwd=ROOT):
    command=tuple(map(str,command))
    print("$ "+shlex.join(command),flush=True)
    environment={**os.environ,"PYTHONDONTWRITEBYTECODE":"1","PYTHONIOENCODING":"utf-8"}
    subprocess.run(command,cwd=cwd,env=environment,check=True)


def _repository_quality(_scratch):
    _run((PYTHON,"repo_check/run.py","--profile","all"))


def _compileall(scratch):
    target=scratch / "compile-source"
    ignored=shutil.ignore_patterns("__pycache__","*.pyc","*.pyo",".pytest_cache","node_modules",".artifacts")
    for name in ("src","tests","sandbox","repo_check","tools","distribution"):
        shutil.copytree(ROOT / name,target / name,ignore=ignored)
    _run((PYTHON,"-m","compileall","-q",target),cwd=target)


def _pytest(scratch,full,workers):
    _run((PYTHON,"tools/run_tests.py","--workers",str(workers),"--scratch",scratch / "pytest","--",
        "tests/e2e",*( () if full else ("-m","not delivery") ),"--junitxml",scratch / "acceptance.xml"))


def _clean_tree_check(_scratch):
    result=subprocess.run((PYTHON,"tools/clean_workspace.py"),cwd=ROOT,capture_output=True,text=True,encoding="utf-8")
    print(result.stdout,end="",flush=True)
    if result.returncode or "cleanup targets: 0" not in result.stdout:
        raise VerificationError(result.stdout+result.stderr)


def _steps(*,full,workers=DEFAULT_WORKERS):
    return (Step("repository-quality",_repository_quality),Step("compileall",_compileall),
        Step("e2e",lambda scratch:_pytest(scratch,full,workers)),
        Step("repository-quality-final",_repository_quality),Step("clean-tree",_clean_tree_check))


def _run_steps(steps: Sequence[Step], *, scratch: Path) -> None:
    observations = []
    failures = []
    for index, step in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {step.name}", flush=True)
        started = perf_counter()
        try:
            step.action(scratch)
        except (OSError, subprocess.CalledProcessError, VerificationError) as exc:
            failure = f"{step.name} failed: {exc}"
            failures.append(failure)
            observations.append({'step':step.name,'status':'failed','error':str(exc),
                                 'seconds':perf_counter()-started})
            print(failure, file=sys.stderr, flush=True)
        else:
            observations.append({'step':step.name,'status':'passed','seconds':perf_counter()-started})
            print(f"PASS: {step.name}", flush=True)
        (scratch/'verification.json').write_text(json.dumps({'steps':observations,'failures':failures},indent=2)+'\n',encoding='utf-8')
    if failures:
        raise VerificationError('\n'.join(failures))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument("--full", action="store_true", help="include wheel/sdist installation and extracted distribution profiles")
    parser.add_argument(
        "--scratch",
        type=Path,
        help="use a caller-owned scratch directory outside the repository",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.scratch is not None:
            try:
                scratch = external_scratch(args.scratch, ROOT)
            except ValueError as exc:
                parser.error(str(exc))
            scratch.mkdir(parents=True, exist_ok=True)
            _run_steps(_steps(full=args.full, workers=args.workers), scratch=scratch)
        else:
            with tempfile.TemporaryDirectory(prefix="vibeflow-verify-") as raw:
                _run_steps(_steps(full=args.full, workers=args.workers), scratch=Path(raw))
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("VibeFlow verification: PASS")
    return 0


if __name__ == "__main__":
    if __package__:
        from .process_supervision import entrypoint
    else:
        from process_supervision import entrypoint
    raise SystemExit(entrypoint(Path(__file__), sys.argv[1:], main))
