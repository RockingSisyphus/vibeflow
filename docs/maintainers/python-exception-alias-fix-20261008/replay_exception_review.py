"""Replay unchanged F05 review scripts from one isolated selected product."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import runpy
import sys
import zipfile


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    select = parser.add_mutually_exclusive_group()
    select.add_argument("--source", type=Path)
    select.add_argument("--kernel", type=Path)
    parser.add_argument("--review", choices=("static", "cli"), required=True)
    parser.add_argument("--expect", choices=("before", "fixed"), required=True)
    parser.add_argument("--manifest", type=Path,
                        help="explicit frozen product manifest required for fixed replay")
    parser.add_argument("--work", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--origin-report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists() or args.origin_report.exists():
        parser.error("evidence exists; preserve it and select fresh output paths")
    if args.review == "cli" and (args.work is None or args.work.exists()):
        parser.error("CLI review requires a new --work directory")
    if args.expect == "fixed" and args.manifest is None:
        parser.error("fixed replay requires this run's explicit --manifest")
    evidence = Path(__file__).resolve().parent
    repo = evidence.parents[2]
    protection = json.loads((evidence / "before-F05-source-and-protection.json").read_text())
    protected = protection["protected_new_audit_and_original_scripts"]
    expected_manifest = json.loads(args.manifest.read_text()) if args.manifest else protection
    expected_files = expected_manifest["files"]
    expected_count = expected_manifest["product_file_count"]
    if expected_count != len(expected_files) or not expected_count:
        raise ValueError("invalid frozen product manifest file count")
    for record in protected:
        if sha(repo / record["path"]) != record["sha256"]:
            raise ValueError("protected original review changed: " + record["path"])
    script_name = "reproduce_exception_alias.py" if args.review == "static" else "reproduce_exception_cli.py"
    script = evidence / script_name
    record = next(row for row in protected if Path(row["path"]).name == script_name)
    if sha(script) != record["sha256"]:
        raise ValueError("preserved review script differs from original")
    if args.source:
        product, kind = args.source.resolve(strict=True), "source_snapshot"
    elif args.kernel:
        product, kind = args.kernel.resolve(strict=True), "kernel_zip"
    else:
        distribution = importlib.metadata.distribution("vibeflow")
        if not distribution.read_text("WHEEL") or json.loads(distribution.read_text("direct_url.json") or "{}").get("dir_info", {}).get("editable"):
            raise ValueError("installed product must be a noneditable wheel")
        product, kind = Path(distribution.locate_file("")).resolve(strict=True), "installed_wheel"
    prefix = str(product / "vibeflow") + "/"

    def product_files() -> dict:
        if args.kernel:
            with zipfile.ZipFile(product) as archive:
                return {name: hashlib.sha256(archive.read(name)).hexdigest()
                        for name in archive.namelist() if name.startswith("vibeflow/") and not name.endswith("/")}
        root = product / "vibeflow"
        return {"vibeflow/" + path.relative_to(root).as_posix(): sha(path)
                for path in root.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix not in (".pyc", ".pyo")}

    before = product_files()
    if before != expected_files:
        raise ValueError("selected product differs from the explicit frozen manifest")
    sys.path.insert(0, str(product))
    sys.path.insert(0, str(evidence))  # Explicit input-only sibling CASES import.
    previous_argv = sys.argv
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.origin_report.parent.mkdir(parents=True, exist_ok=True)
    sys.argv = [str(script), "--product", str(product), "--report", str(args.report.resolve())]
    if args.review == "cli":
        sys.argv += ["--work", str(args.work.resolve())]
    try:
        runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = previous_argv
    raw = json.loads(args.report.read_text())
    modules = {name: str(getattr(module, "__file__", "") or "")
               for name, module in sys.modules.items() if name == "vibeflow" or name.startswith("vibeflow.")}
    foreign = {name: path for name, path in modules.items() if not path.startswith(prefix)}
    cli_origins = [row["origin"] for row in raw["rows"]] if args.review == "cli" else []
    child_origins_valid = all(not row["foreign"] and row["origin"] == prefix + "__init__.py" for row in cli_origins)
    expected_before = lambda row: row["case"] == "separate_statements_control"
    expected_state_observed = (raw["count"] == 16 and
        all(row["actual"] == (expected_before(row) if args.expect == "before" else row["expected"])
            for row in raw["rows"]))
    route_valid = all(row["state"] == "completed" for row in raw["rows"]) if args.review == "static" else all(
        row["status"] == ("FAIL" if row["actual"] else "PASS") and row["exit"] == (1 if row["actual"] else 0)
        for row in raw["rows"])
    after = product_files()
    originals_unchanged = all(sha(repo / row["path"]) == row["sha256"] for row in protected) and sha(script) == record["sha256"]
    result = {"product": {"kind": kind, "path": str(product), "expected_origin_prefix": prefix},
              "review": args.review, "expected_state": args.expect, "original_script": str(script),
              "original_script_sha256": record["sha256"], "original_expectations_modified": False,
              "count": raw["count"], "raw_original_expectation_mismatches": raw["mismatches"],
              "expected_state_observed": expected_state_observed, "formal_route_status_valid": route_valid,
              "loaded_product_modules": modules, "foreign_product_modules": foreign,
              "cli_child_product_origins": cli_origins, "cli_child_origins_valid": child_origins_valid,
              "product_files_sha256": before, "product_files_sha256_after": after,
              "expected_manifest": str(args.manifest.resolve()) if args.manifest else str(evidence / "before-F05-source-and-protection.json"),
              "expected_product_file_count": expected_count,
              "selected_product_files_match_expected_manifest": before == expected_files == after,
              "product_files_unchanged": before == after,
              "protected_original_review_and_scripts_unchanged": originals_unchanged,
              "pass": expected_state_observed and route_valid and not foreign and child_origins_valid and before == after and originals_unchanged}
    with args.origin_report.open("x") as out:
        json.dump(result, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(json.dumps({key: result[key] for key in ("review", "count", "raw_original_expectation_mismatches", "expected_state_observed", "pass")}))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
