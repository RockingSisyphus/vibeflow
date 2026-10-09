"""Capture an explicit frozen product snapshot or full verification input map.

All file types participate. Products and input file counts come from each
capture; no historical snapshot or gate directory is selected by default.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


GENERATED = {"__pycache__", "node_modules", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
INPUT_ROOTS = ("src", "tests", "tools", "sandbox", "quality", "distribution", "pyproject.toml")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(repo: Path, roots: tuple[str, ...]) -> dict:
    result = {}
    for name in roots:
        root = repo / name
        paths = (root,) if root.is_file() else root.rglob("*")
        for path in paths:
            if path.is_file() and not (GENERATED & set(path.relative_to(repo).parts)) and path.suffix not in (".pyc", ".pyo"):
                result[path.relative_to(repo).as_posix()] = sha(path)
    return dict(sorted(result.items()))


def differences(before: dict, after: dict) -> dict:
    return {"missing": sorted(before.keys() - after.keys()), "added": sorted(after.keys() - before.keys()),
            "changed": {name: {"before": before[name], "after": after[name]}
                        for name in sorted(before.keys() & after.keys()) if before[name] != after[name]}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("product", "inputs"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--destination", type=Path, help="new root containing copied vibeflow/; product only")
    parser.add_argument("--reference", type=Path, help="optional explicit prior product/input manifest")
    args = parser.parse_args()
    repo = args.repo.resolve(strict=True)
    if args.report.exists() or args.destination is not None and args.destination.exists():
        parser.error("evidence already exists; preserve it and select fresh paths")
    if args.kind == "product" and args.destination is None:
        parser.error("product snapshot requires a new --destination")
    if args.kind == "inputs" and args.destination is not None:
        parser.error("input capture does not copy product files")
    roots = ("src/vibeflow",) if args.kind == "product" else INPUT_ROOTS
    first = collect(repo, roots)
    report = {"captured_utc": datetime.now(timezone.utc).isoformat(), "repo": str(repo),
              "kind": args.kind, "roots": list(roots), "all_file_types": True,
              "excluded_generated_directories": sorted(GENERATED), "excluded_bytecode_suffixes": [".pyc", ".pyo"]}
    if args.kind == "product":
        destination = args.destination.resolve()
        destination.mkdir(parents=True)
        for name in first:
            target = destination / Path(name).relative_to("src")
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as out:
                out.write((repo / name).read_bytes())
        captured = {str(Path(name).relative_to("src")): sha(destination / Path(name).relative_to("src")) for name in first}
        report.update(snapshot=str(destination), product_file_count=len(captured), files=captured)
        copied_matches = captured == {str(Path(name).relative_to("src")): value for name, value in first.items()}
        report["copied_files_match_capture"] = copied_matches
    else:
        report.update(file_count=len(first), files=first)
        copied_matches = True
    second = collect(repo, roots)
    report["source_unchanged_during_capture"] = first == second
    report["capture_changes"] = differences(first, second)
    if args.reference:
        reference = json.loads(args.reference.read_text())
        previous = reference["files"] if isinstance(reference.get("files"), dict) else reference
        report["explicit_reference"] = str(args.reference.resolve())
        report["reference_sha256"] = sha(args.reference)
        report["reference_comparison"] = differences(previous, report["files"])
        report["matches_reference"] = previous == report["files"]
    report["pass"] = copied_matches and first == second
    if args.kind == "inputs" and args.reference:
        report["pass"] = report["pass"] and report["matches_reference"]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as out:
        json.dump(report, out, indent=2)
        out.write("\n")
    print(json.dumps({key: report[key] for key in ("kind", "pass", "source_unchanged_during_capture")}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
