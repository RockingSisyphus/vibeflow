#!/usr/bin/env python3
"""Read all product bytes without importing or extracting product code."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile
from email.parser import BytesParser


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_files(root: Path, *, installed: bool = False) -> tuple[dict, list]:
    files, generated = {}, []
    for path in sorted((root / "vibeflow").rglob("*")):
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        if installed and "__pycache__" in path.parts and path.suffix in {".pyc", ".pyo"}:
            generated.append(name)
        else:
            files[name] = file_sha(path)
    return files, generated


def zip_files(archive: zipfile.ZipFile, *, kernel: bool = False) -> dict:
    names = [info.filename for info in archive.infolist() if not info.is_dir()]
    if len(names) != len(set(names)):
        raise ValueError("ZIP has duplicate file names")
    if kernel and any(not name.startswith("vibeflow/") for name in names):
        raise ValueError("kernel has files outside vibeflow/")
    return {name: sha(archive.read(name)) for name in names if name.startswith("vibeflow/")}


def compare(actual: dict, expected: dict) -> dict:
    missing = sorted(expected.keys() - actual.keys())
    extra = sorted(actual.keys() - expected.keys())
    changed = {name: {"expected": expected[name], "actual": actual[name]}
               for name in sorted(expected.keys() & actual.keys())
               if actual[name] != expected[name]}
    return {"passed": not (missing or extra or changed), "file_count": len(actual),
            "missing": missing, "extra": extra, "changed": changed, "files": actual}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="directory containing frozen vibeflow/")
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("report already exists; preserve it and select a fresh output")
    gate, snapshot = args.gate.resolve(), args.snapshot.resolve()
    manifest = json.loads(args.manifest.read_text())
    expected = manifest["files"]
    if manifest["product_file_count"] != 334 or len(expected) != 334:
        raise ValueError("expected frozen manifest must contain exactly 334 product files")
    driver = "vibeflow/targets/javascript/resources/toolchain_driver.mjs"
    report = {"gate": str(gate), "manifest": str(args.manifest.resolve()),
              "manifest_sha256": file_sha(args.manifest), "snapshot": str(snapshot),
              "script_sha256": file_sha(Path(__file__)), "expected_file_count": 334,
              "expected_driver_sha256": expected[driver], "comparisons": {}, "artifacts": {},
              "metadata_checks": {}, "probe_error": None}
    try:
        actual, _ = directory_files(snapshot)
        report["comparisons"]["frozen_snapshot"] = compare(actual, expected)
        interpreter = gate / "wheel-venv/bin/python"
        locator = "import importlib.util,json,sysconfig; s=importlib.util.find_spec('vibeflow'); print(json.dumps({'purelib':sysconfig.get_path('purelib'),'origin':s.origin if s else None}))"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        located = json.loads(subprocess.check_output([str(interpreter), "-I", "-B", "-c", locator],
                                                    text=True, env=env))
        purelib = Path(located["purelib"]).resolve()
        origin = Path(located["origin"]).resolve()
        if not purelib.is_relative_to((gate / "wheel-venv").resolve()) or origin != purelib / "vibeflow/__init__.py":
            raise ValueError("wheel import origin is outside its isolated installed package")
        actual, generated = directory_files(purelib, installed=True)
        report["comparisons"]["installed_wheel"] = dict(compare(actual, expected),
            origin=str(origin), purelib=str(purelib), excluded_generated_bytecode=generated)
        wheels = sorted((gate / "wheel-dist").glob("*.whl"))
        if len(wheels) != 1:
            raise ValueError("expected one fresh wheel")
        wheel = wheels[0]
        with zipfile.ZipFile(wheel) as archive:
            report["comparisons"]["wheel_archive"] = compare(zip_files(archive), expected)
            metas = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
            if len(metas) != 1:
                raise ValueError("expected one wheel METADATA")
            wheel_meta = BytesParser().parsebytes(archive.read(metas[0]))
        report["artifacts"]["wheel"] = {"path": str(wheel), "sha256": file_sha(wheel),
            "name": wheel_meta["Name"], "version": wheel_meta["Version"]}
        distributions = {}
        for profile, directory in (("collaborative", "distribution"), ("autonomous", "distribution-autonomous")):
            root = gate / directory
            meta_path = root / "DISTRIBUTION.json"
            meta = json.loads(meta_path.read_text())
            if meta["development_profile"] != profile:
                raise ValueError("distribution profile metadata mismatch")
            kernel = root / meta["kernel"]["archive"]
            kernel_hash = file_sha(kernel)
            with zipfile.ZipFile(kernel) as archive:
                report["comparisons"][profile + "_kernel"] = compare(zip_files(archive, kernel=True), expected)
            distributions[profile] = (meta, kernel_hash)
            report["artifacts"][profile + "_kernel"] = {"path": str(kernel), "sha256": kernel_hash,
                "metadata_path": str(meta_path), "metadata_sha256": file_sha(meta_path), "metadata": meta}
            report["metadata_checks"][profile + "_kernel_sha256"] = kernel_hash == meta["kernel"]["sha256"]
            report["metadata_checks"][profile + "_wheel_version"] = meta["version"] == wheel_meta["Version"]
        seen = set()
        for outer in sorted((gate / "archives").glob("*.zip")):
            with zipfile.ZipFile(outer) as archive:
                metas = [name for name in archive.namelist() if name.endswith("/DISTRIBUTION.json")]
                if len(metas) != 1:
                    raise ValueError("expected one DISTRIBUTION.json per profile archive")
                meta = json.loads(archive.read(metas[0]))
                profile = meta["development_profile"]
                if profile not in distributions or profile in seen:
                    raise ValueError("unknown or duplicate profile archive")
                seen.add(profile)
                embedded_name = str(PurePosixPath(metas[0]).parent / meta["kernel"]["archive"])
                embedded = archive.read(embedded_name)
                embedded_hash = sha(embedded)
                with zipfile.ZipFile(io.BytesIO(embedded)) as kernel:
                    report["comparisons"][profile + "_embedded_kernel"] = compare(zip_files(kernel, kernel=True), expected)
                direct_meta, direct_hash = distributions[profile]
                report["metadata_checks"][profile + "_archive_metadata"] = meta == direct_meta
                report["metadata_checks"][profile + "_embedded_sha256"] = embedded_hash == direct_hash == meta["kernel"]["sha256"]
                report["artifacts"][profile + "_distribution_archive"] = {"path": str(outer),
                    "sha256": file_sha(outer), "embedded_kernel_member": embedded_name,
                    "embedded_kernel_sha256": embedded_hash, "metadata": meta}
        if seen != {"collaborative", "autonomous"}:
            raise ValueError("both profile archives are required")
        for value in report["comparisons"].values():
            value["driver_sha256_matches"] = value["files"].get(driver) == expected[driver]
        report["passed"] = (len(report["comparisons"]) == 7
            and all(value["passed"] and value["file_count"] == 334 and value["driver_sha256_matches"]
                    for value in report["comparisons"].values())
            and all(report["metadata_checks"].values()))
    except Exception as exc:
        report["probe_error"] = f"{type(exc).__name__}: {exc}"
        report["passed"] = False
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open("x") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({key: report[key] for key in ("passed", "expected_file_count", "probe_error")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
