#!/usr/bin/env python3
"""Preview or remove VibeFlow's reproducible local artifacts.

The cleaner intentionally does not delegate to ``git clean``.  Every target is
resolved below the repository root, checked against Git's tracked files, and
keeps nested repositories and distribution sources out of scope.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
PROTECTED_TREES = frozenset({".git", "references"})
PROTECTED_ROOTS = frozenset({"archive", "dist", "distribution"})
EXACT_ARTIFACTS = (
    ".pytest_cache",
    "build",
    "output",
    "reports",
    "review_artifacts",
    "runs",
    "tmp",
    "vibeflow_distribution",
)
EMPTY_METADATA_DIRS = (".agents", ".codex")
LEGACY_DIRECTORIES = (
    "examples",
    "tests/support",
    "tests/unit",
    "src/vibeflow/aot",
    "src/vibeflow/cli",
    "src/vibeflow/config",
    "src/vibeflow/descriptors",
    "src/vibeflow/devtools",
    "src/vibeflow/graph_config",
    "src/vibeflow/health",
    "src/vibeflow/plugins",
    "src/vibeflow/portable",
    "src/vibeflow/purity",
    "src/vibeflow/rendering",
    "src/vibeflow/resources",
    "src/vibeflow/runtime",
    "src/vibeflow/workspace",
    "src/vibeflow/targets/python/health",
    "src/vibeflow/targets/python/purity",
    "src/vibeflow/tooling/devtools",
    "src/vibeflow/tooling/javascript",
    "src/vibeflow/tooling/rendering",
    "src/vibeflow/tooling/workspace",
)
RECURSIVE_DIR_NAMES = frozenset(
    {
        ".artifacts",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "review_artifacts",
    }
)
SANDBOX_OUTPUT_NAMES = frozenset(
    {
        ".artifacts",
        "build",
        "dist",
        "output",
        "reports",
        "review_artifacts",
        "runs",
        "tmp",
    }
)


@dataclass(frozen=True)
class CleanupTarget:
    path: Path
    kind: str


def _tracked_paths() -> frozenset[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    candidates = (
        ROOT / item.decode("utf-8")
        for item in completed.stdout.split(b"\0")
        if item
    )
    return frozenset(
        candidate
        for candidate in candidates
        if candidate.exists() or candidate.is_symlink()
    )


def _is_protected(path: Path) -> bool:
    try:
        relative = path.absolute().relative_to(ROOT)
    except ValueError:
        return True
    if not relative.parts:
        return True
    if relative.parts[0] in PROTECTED_TREES:
        return True
    return len(relative.parts) == 1 and relative.parts[0] in PROTECTED_ROOTS


def _is_traversable_protected_root(path: Path) -> bool:
    return path.absolute() == (ROOT / "distribution").absolute()


def _contains_tracked(path: Path, tracked: frozenset[Path]) -> bool:
    if path.is_symlink() or path.is_file():
        return path.absolute() in tracked
    prefix = path.absolute()
    return any(candidate == prefix or prefix in candidate.parents for candidate in tracked)


def _contains_only_generated_content(directory: Path) -> bool:
    """Return whether a legacy directory can be removed as one safe unit."""

    if directory.is_symlink() or not directory.is_dir():
        return False
    for current, directory_names, file_names in os.walk(directory, followlinks=False):
        current_path = Path(current)
        retained: list[str] = []
        for name in directory_names:
            candidate = current_path / name
            if candidate.is_symlink():
                return False
            if name in RECURSIVE_DIR_NAMES or name.endswith(".egg-info"):
                continue
            retained.append(name)
        directory_names[:] = retained
        if any(not name.endswith((".pyc", ".pyo")) for name in file_names):
            return False
    return True


def discover_targets(*, include_release: bool = False) -> tuple[CleanupTarget, ...]:
    found: dict[Path, str] = {}
    for relative in EXACT_ARTIFACTS:
        candidate = ROOT / relative
        if candidate.exists() or candidate.is_symlink():
            found[candidate] = "workspace"
    for relative in EMPTY_METADATA_DIRS:
        candidate = ROOT / relative
        if candidate.is_dir() and not any(candidate.iterdir()):
            found[candidate] = "empty-metadata"
    for relative in LEGACY_DIRECTORIES:
        candidate = ROOT / relative
        if _contains_only_generated_content(candidate):
            found[candidate] = "empty-legacy-directory"
    for current, directory_names, file_names in os.walk(ROOT, followlinks=False):
        current_path = Path(current)
        # The repository root is protected as a deletion target, but it is the
        # traversal starting point.  Only protected descendants are pruned.
        if (
            current_path != ROOT
            and _is_protected(current_path)
            and not _is_traversable_protected_root(current_path)
        ):
            directory_names[:] = []
            continue
        retained: list[str] = []
        for name in directory_names:
            candidate = current_path / name
            if _is_protected(candidate) and not _is_traversable_protected_root(
                candidate
            ):
                continue
            if current_path == ROOT and name in EMPTY_METADATA_DIRS:
                # Empty metadata directories were handled above.  Non-empty
                # ones are user-owned state and must not be cleaned piecemeal.
                continue
            if name in RECURSIVE_DIR_NAMES:
                found[candidate] = "cache-or-dependency"
                continue
            if name in SANDBOX_OUTPUT_NAMES and "sandbox" in candidate.parts:
                found[candidate] = "sandbox-output"
                continue
            if name.endswith(".egg-info"):
                found[candidate] = "package-metadata"
                continue
            retained.append(name)
        directory_names[:] = retained
        for name in file_names:
            candidate = current_path / name
            if candidate.suffix in {".pyc", ".pyo"}:
                found[candidate] = "python-cache"
    for candidate in ROOT.iterdir():
        if candidate.is_file() and candidate.suffix.lower() == ".zip":
            found[candidate] = "release"
    if include_release:
        latest_release = ROOT / "dist" / "vibeflow-distribution"
        if latest_release.exists() or latest_release.is_symlink():
            found[latest_release] = "current-release"
    # Keep only highest-level targets so deletion plans stay short and stable.
    ordered = sorted(found, key=lambda item: (len(item.parts), str(item)))
    selected: list[CleanupTarget] = []
    for path in ordered:
        if any(parent.path == path or parent.path in path.parents for parent in selected):
            continue
        selected.append(CleanupTarget(path=path, kind=found[path]))
    return tuple(selected)


def validate_targets(
    targets: Iterable[CleanupTarget],
    *,
    tracked: frozenset[Path],
) -> tuple[CleanupTarget, ...]:
    safe: list[CleanupTarget] = []
    for target in targets:
        if _is_protected(target.path):
            raise RuntimeError(f"refusing protected cleanup target: {target.path}")
        authorized_root_zip = (
            target.kind == "release"
            and target.path.is_file()
            and target.path.parent.absolute() == ROOT.absolute()
            and target.path.suffix.lower() == ".zip"
        )
        if _contains_tracked(target.path, tracked) and not authorized_root_zip:
            raise RuntimeError(f"refusing cleanup target containing tracked files: {target.path}")
        safe.append(target)
    return tuple(safe)


def remove_targets(targets: Iterable[CleanupTarget]) -> None:
    for target in targets:
        path = target.path
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
        elif path.is_dir():
            shutil.rmtree(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="remove validated artifacts; the default only prints the plan",
    )
    parser.add_argument(
        "--include-release",
        action="store_true",
        help=(
            "include the current dist/vibeflow-distribution release; "
            "versioned archive files are always protected"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        targets = validate_targets(
            discover_targets(include_release=args.include_release),
            tracked=_tracked_paths(),
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"cleanup refused: {exc}")
        return 2
    action = "REMOVE" if args.apply else "WOULD_REMOVE"
    for target in targets:
        print(f"{action}\t{target.kind}\t{target.path.relative_to(ROOT)}")
    if args.apply:
        remove_targets(targets)
    print(f"cleanup targets: {len(targets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
