from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "vibeflow_distribution"
ROOT_README_GENERATED_AT_MARKER = "<!-- VIBEFLOW_DISTRIBUTION_GENERATED_AT -->"
EXTRA_DOCS = (
    ("developer_guide.md", "10_Kernel能力与项目开发指南.md"),
)
STANDARD_PROJECT_DIRS = (
    "project/nodes",
    "project/base_lib",
    "project/plugins",
    "project/configs",
    "project/configs/nodesets",
    "project/stubs",
)
MANIFEST_RELATIVE = Path("kernel/MANIFEST.sha256")
KERNEL_ZIP_RELATIVE = Path("kernel/vibeflow-kernel.zip")
PROTECTED_FILES = (
    "run.py",
    "kernel/README.md",
    KERNEL_ZIP_RELATIVE.as_posix(),
    "kernel/THIRD_PARTY_NOTICES.md",
    "kernel/tools/mermaid-renderer/package.json",
    "kernel/tools/mermaid-renderer/package-lock.json",
)
PROTECTED_DIRS = (
    "kernel/docs",
    "kernel/vibeflow",
)
CORE_SELF_CHECK_STRUCTURE_ARGS = (
    "--enable-structure-limits",
    "--warn-root-code-files",
    "150",
    "--max-root-code-files",
    "200",
    "--warn-code-dirs",
    "16",
    "--max-code-dirs",
    "24",
    "--warn-code-files-per-dir",
    "20",
    "--max-code-files-per-dir",
    "30",
    "--warn-code-dir-depth",
    "4",
    "--max-code-dir-depth",
    "5",
    "--warn-child-code-dirs-per-dir",
    "6",
    "--max-child-code-dirs-per-dir",
    "10",
    "--warn-root-level-code-files",
    "110",
    "--max-root-level-code-files",
    "120",
)


class BuildDistributionError(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a copyable VibeFlow distribution directory.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="directory to rebuild")
    parser.add_argument("--keep-existing", action="store_true", help="fail instead of replacing an existing output directory")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    try:
        build_distribution(output, replace=not args.keep_existing)
    except BuildDistributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"built distribution: {output}")
    return 0


def build_distribution(output: Path, *, replace: bool = True, run_self_check: bool = True) -> None:
    if run_self_check:
        _run_core_self_check()
    _prepare_output(output, replace=replace)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "project_template", output)
    _copy_tree(ROOT / "distribution" / "kernel_development_pack" / "docs", output / "kernel" / "docs")
    _copy_mermaid_renderer_config(output)
    _copy_third_party_notices(output)
    _copy_extra_docs(output / "kernel" / "docs")
    _write_kernel_archive(ROOT / "src" / "vibeflow", output / KERNEL_ZIP_RELATIVE)
    _ensure_standard_project_dirs(output)
    _write_root_readme(output)
    _write_kernel_manifest(output)
    _normalize_output_modes(output)


def _run_core_self_check() -> None:
    env = os.environ.copy()
    src_path = str(ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else os.pathsep.join((src_path, existing_pythonpath))
    command = [sys.executable, "-m", "vibeflow", "quality-check", "--path", "src/vibeflow", *CORE_SELF_CHECK_STRUCTURE_ARGS]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        command_text = " ".join(command)
        raise BuildDistributionError(
            "refusing to build distribution because kernel self-check failed: "
            + f"PYTHONPATH=src {command_text}"
        )


def _prepare_output(output: Path, *, replace: bool) -> None:
    if output.exists() and not replace:
        raise FileExistsError(f"output already exists: {output}")
    if output.exists():
        _remove_tree(output)
    output.mkdir(parents=True)


def _copy_tree(source: Path, target: Path) -> None:
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if _ignored(relative):
            continue
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(path.read_bytes())


def _copy_extra_docs(target: Path) -> None:
    for source_name, target_name in EXTRA_DOCS:
        source = ROOT / "docs" / source_name
        destination = target / target_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _copy_mermaid_renderer_config(output: Path) -> None:
    source = ROOT / "tools" / "mermaid-renderer"
    target = output / "kernel" / "tools" / "mermaid-renderer"
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        path = source / name
        if path.exists():
            (target / name).write_bytes(path.read_bytes())


def _copy_third_party_notices(output: Path) -> None:
    source = ROOT / "THIRD_PARTY_NOTICES.md"
    if source.exists():
        destination = output / "kernel" / source.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _write_kernel_archive(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
            relative_to_package = path.relative_to(source)
            if path.is_dir() or _ignored(relative_to_package):
                continue
            archive_relative = Path("vibeflow") / relative_to_package
            info = zipfile.ZipInfo(archive_relative.as_posix())
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def _write_kernel_manifest(output: Path) -> None:
    lines = []
    for relative in _iter_manifest_files(output):
        digest = _hash_file(output / relative)
        lines.append(f"{digest}  {relative.as_posix()}")
    path = output / MANIFEST_RELATIVE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _iter_manifest_files(output: Path) -> list[Path]:
    files: list[Path] = []
    for relative in PROTECTED_FILES:
        path = output / relative
        if path.is_file():
            files.append(Path(relative))
    for relative_dir in PROTECTED_DIRS:
        root = output / relative_dir
        if not root.exists():
            continue
        for path in root.rglob("*"):
            relative = path.relative_to(output)
            if path.is_file() and not _ignored(relative):
                files.append(relative)
    return sorted(set(files), key=lambda item: item.as_posix())


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_standard_project_dirs(output: Path) -> None:
    for relative in STANDARD_PROJECT_DIRS:
        (output / relative).mkdir(parents=True, exist_ok=True)


def _normalize_output_modes(output: Path) -> None:
    """Make the directory tree and its deterministic ZIP use identical modes.

    The project is commonly built under a collaborative ``umask 0002``, which
    otherwise leaves generated files at 0664 while the frozen ZIP correctly
    records portable 0644 entries.  Tree hashes include modes, so normalize the
    generated source tree before it is validated or frozen.
    """

    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise BuildDistributionError(
                f"refusing to normalize a distribution containing a symlink: {path}"
            )
        path.chmod(0o755 if path.is_dir() else 0o644)
    output.chmod(0o755)


def _remove_tree(path: Path) -> None:
    for item in sorted(path.rglob("*"), key=lambda candidate: len(candidate.parts), reverse=True):
        if item.is_dir():
            item.rmdir()
        else:
            item.unlink()
    path.rmdir()


def _ignored(relative: Path) -> bool:
    ignored_names = {"__pycache__", ".pytest_cache", "runs", "reports", "node_modules"}
    return any(part in ignored_names or part.endswith(".pyc") for part in relative.parts)


def _write_root_readme(output: Path) -> None:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is None:
        generated = datetime.now(timezone.utc)
    else:
        try:
            generated = datetime.fromtimestamp(int(source_date_epoch), timezone.utc)
        except (TypeError, ValueError, OverflowError) as exc:
            raise BuildDistributionError("SOURCE_DATE_EPOCH must be an integer Unix timestamp") from exc
    generated_at = generated.strftime("%Y-%m-%d %H:%M:%S UTC")
    path = output / "README.md"
    text = path.read_text(encoding="utf-8")
    marker_count = text.count(ROOT_README_GENERATED_AT_MARKER)
    if marker_count != 1:
        raise BuildDistributionError(
            "distribution project template README must contain exactly one "
            + ROOT_README_GENERATED_AT_MARKER
        )
    rendered = text.replace(
        ROOT_README_GENERATED_AT_MARKER,
        f"生成时间：{generated_at}",
    )
    path.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
