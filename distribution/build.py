from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "vibeflow-distribution"
DEFAULT_ARCHIVE_DIR = ROOT / "archive"
ARCHIVE_ROOT_NAME = "vibeflow-distribution"
PYTHON_TEMPLATE_RELATIVE = Path("distribution/kernel_development_pack/project_template/project")
JAVASCRIPT_TEMPLATE_RELATIVE = Path("sandbox/javascript/integration/project")
JAVASCRIPT_TEMPLATE_FILES = (
    "package.json",
    "package-lock.json",
    "configs/linear.jsonc",
    "configs/plugins.jsonc",
    "configs/host_extension.jsonc",
    "configs/browser_permanent_port_host.jsonc",
    "configs/nodesets/permanent_port_body.jsonc",
    "base_lib/math.ts",
    "nodes/add.ts",
    "nodes/subtract.ts",
    "nodes/terminal.ts",
    "nodes/host_double.ts",
    "nodes/math.ts",
    "plugins/policy_audit.ts",
    "plugins/compiler_audit.ts",
    "plugins/runtime_audit.ts",
    "host_extensions/math_host.ts",
    "host_extensions/browser_port_host.ts",
    "web/app.ts",
    "web/index.template.html",
    "web/browser_host_app.ts",
    "web/browser_host.template.html",
    "manifests/base_lib/math.jsonc",
    "manifests/capabilities/host-math.jsonc",
    "manifests/host_extensions/math-host.jsonc",
    "manifests/host_extensions/browser-port-host.jsonc",
    "manifests/nodes/add.jsonc",
    "manifests/nodes/subtract.jsonc",
    "manifests/nodes/terminal.jsonc",
    "manifests/nodes/host-double.jsonc",
    "manifests/nodes/math.jsonc",
    "manifests/plugins/policy-audit.jsonc",
    "manifests/plugins/compiler-audit.jsonc",
    "manifests/plugins/runtime-audit.jsonc",
    "manifests/data/x.jsonc",
    "manifests/data/addend.jsonc",
    "manifests/data/subtrahend.jsonc",
    "manifests/data/sum.jsonc",
    "manifests/data/subtrahend-forwarded.jsonc",
    "manifests/data/math-result.jsonc",
    "manifests/data/number.jsonc",
)
EXTRA_DOCS = (
    ("developer_guide.md", "10_Kernel能力与项目开发指南.md"),
    ("js_aot_build.md", "11_JS_TS与Web_AOT构建指南.md"),
)
PYTHON_STANDARD_DIRS = (
    "nodes",
    "base_lib",
    "plugins",
    "configs",
    "configs/nodesets",
    "stubs",
)
MANIFEST_RELATIVE = Path("kernel/MANIFEST.sha256")
KERNEL_ZIP_RELATIVE = Path("kernel/vibeflow-kernel.zip")
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
ARCHIVE_NAME = f"vibeflow-distribution-{VERSION}.zip"
PROTECTED_FILES = (
    "run.py",
    "DISTRIBUTION.json",
    "kernel/README.md",
    "kernel/LICENSE",
    KERNEL_ZIP_RELATIVE.as_posix(),
    "kernel/THIRD_PARTY_NOTICES.md",
    "kernel/tools/mermaid-renderer/package.json",
    "kernel/tools/mermaid-renderer/package-lock.json",
)
PROTECTED_DIRS = (
    "kernel/docs",
    "kernel/vibeflow",
)


class BuildDistributionError(RuntimeError):
    pass


@dataclass(frozen=True)
class DistributionArtifacts:
    directory: Path
    archive: Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the copyable VibeFlow distribution directory and deterministic ZIP."
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"distribution directory to publish (default: {DEFAULT_OUTPUT})",
    )
    output_group.add_argument(
        "--output",
        type=Path,
        dest="legacy_output",
        help="deprecated alias for --output-dir",
    )
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help=f"directory for {ARCHIVE_NAME} (default: {DEFAULT_ARCHIVE_DIR})",
    )
    parser.add_argument("--keep-existing", action="store_true", help="fail instead of replacing an existing output directory")
    args = parser.parse_args()
    output = args.legacy_output if args.legacy_output is not None else args.output_dir
    try:
        artifacts = build_release(
            output,
            archive_dir=args.archive_dir,
            replace=not args.keep_existing,
        )
    except BuildDistributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"built distribution directory: {artifacts.directory}")
    print(f"built distribution archive: {artifacts.archive}")
    return 0


def build_release(
    output: Path = DEFAULT_OUTPUT,
    *,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    replace: bool = True,
    run_self_check: bool = True,
) -> DistributionArtifacts:
    output = _safe_output_path(output)
    archive_dir = _safe_archive_dir(archive_dir)
    archive = archive_dir / ARCHIVE_NAME
    _validate_release_paths(output=output, archive=archive)
    if output.exists() and not replace:
        raise BuildDistributionError(f"output already exists: {output}")
    if archive.exists() and not replace:
        raise BuildDistributionError(f"archive already exists: {archive}")
    if run_self_check:
        _run_core_self_check()

    output.parent.mkdir(parents=True, exist_ok=True)
    archive_dir.mkdir(parents=True, exist_ok=True)
    output_staging_root = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.vibeflow-build-", dir=output.parent)
    )
    archive_staging_root = Path(
        tempfile.mkdtemp(prefix=f".{ARCHIVE_NAME}.vibeflow-build-", dir=archive_dir)
    )
    staged_output = output_staging_root / "payload"
    staged_archive = archive_staging_root / ARCHIVE_NAME
    try:
        _populate_distribution(staged_output)
        _verify_staged_distribution(staged_output)
        _write_distribution_archive(staged_output, staged_archive)
        _verify_distribution_archive(staged_output, staged_archive)
        _publish_release_pair(
            staged_output,
            staged_archive,
            output,
            archive,
            replace=replace,
            output_staging_root=output_staging_root,
            archive_staging_root=archive_staging_root,
        )
    finally:
        for staging_root in (output_staging_root, archive_staging_root):
            if staging_root.exists():
                _remove_tree(staging_root)
    return DistributionArtifacts(directory=output, archive=archive)


def build_distribution(
    output: Path,
    *,
    replace: bool = True,
    run_self_check: bool = True,
) -> Path:
    """Build only a directory for programmatic tests and compatibility callers.

    The command-line release builder always uses :func:`build_release` and
    publishes the matching deterministic outer ZIP as well.
    """

    output = _safe_output_path(output)
    if output.exists() and not replace:
        raise BuildDistributionError(f"output already exists: {output}")
    if run_self_check:
        _run_core_self_check()
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=f".{output.name}.vibeflow-build-",
            dir=output.parent,
        )
    )
    staged_output = staging_root / "payload"
    try:
        _populate_distribution(staged_output)
        _verify_staged_distribution(staged_output)
        _publish_distribution(
            staged_output,
            output,
            replace=replace,
            staging_root=staging_root,
        )
    finally:
        if staging_root.exists():
            _remove_tree(staging_root)
    return output


def _safe_output_path(output: Path) -> Path:
    expanded = output.expanduser()
    if expanded.is_symlink():
        raise BuildDistributionError(
            f"distribution output must not be a symlink: {expanded}"
        )
    resolved = expanded.resolve()
    if resolved == Path(resolved.anchor):
        raise BuildDistributionError("distribution output must not be a filesystem root")
    if (resolved == ROOT or ROOT in resolved.parents) and resolved != DEFAULT_OUTPUT.resolve():
        raise BuildDistributionError(
            "distribution output inside the source repository must be the canonical release path: "
            f"{resolved}"
        )
    return resolved


def _safe_archive_dir(archive_dir: Path) -> Path:
    expanded = archive_dir.expanduser()
    if expanded.is_symlink():
        raise BuildDistributionError(
            f"distribution archive directory must not be a symlink: {expanded}"
        )
    resolved = expanded.resolve()
    if resolved == Path(resolved.anchor):
        raise BuildDistributionError("distribution archive directory must not be a filesystem root")
    if (resolved == ROOT or ROOT in resolved.parents) and resolved != DEFAULT_ARCHIVE_DIR.resolve():
        raise BuildDistributionError(
            "distribution archive inside the source repository must use the canonical release path: "
            f"{resolved}"
        )
    return resolved


def _validate_release_paths(*, output: Path, archive: Path) -> None:
    if output == archive or output in archive.parents or archive in output.parents:
        raise BuildDistributionError(
            "distribution output and archive paths must not overlap: "
            f"output={output}; archive={archive}"
        )


def _populate_distribution(output: Path) -> None:
    output.mkdir(parents=True)
    _copy_tree(
        ROOT / "distribution" / "kernel_development_pack" / "project_template",
        output,
        excluded_top_level={"project"},
    )
    _copy_tree(
        ROOT / PYTHON_TEMPLATE_RELATIVE,
        output / "python_project",
        excluded_top_level={"manifests"},
    )
    _copy_javascript_project(output / "javascript_project")
    _copy_tree(
        ROOT / "distribution" / "kernel_development_pack" / "docs",
        output / "kernel" / "docs",
    )
    _copy_mermaid_renderer_config(output)
    _copy_license(output)
    _copy_third_party_notices(output)
    _copy_extra_docs(output / "kernel" / "docs")
    _write_kernel_archive(ROOT / "src" / "vibeflow", output / KERNEL_ZIP_RELATIVE)
    _ensure_standard_project_dirs(output)
    _write_workspace_config(output)
    _write_javascript_architecture(output)
    _write_distribution_metadata(output)
    _write_kernel_manifest(output)
    _normalize_output_modes(output)


def _publish_distribution(
    staged_output: Path,
    output: Path,
    *,
    replace: bool,
    staging_root: Path,
) -> None:
    previous_output = staging_root / "previous"
    if output.exists():
        if not replace:
            raise BuildDistributionError(f"output already exists: {output}")
        os.replace(output, previous_output)
    try:
        os.replace(staged_output, output)
    except BaseException:
        if previous_output.exists() and not output.exists():
            os.replace(previous_output, output)
        raise
    if previous_output.exists():
        _remove_tree(previous_output)


def _publish_release_pair(
    staged_output: Path,
    staged_archive: Path,
    output: Path,
    archive: Path,
    *,
    replace: bool,
    output_staging_root: Path,
    archive_staging_root: Path,
) -> None:
    previous_output = output_staging_root / "previous"
    previous_archive = archive_staging_root / "previous.zip"
    if not replace:
        if output.exists():
            raise BuildDistributionError(f"output already exists: {output}")
        if archive.exists():
            raise BuildDistributionError(f"archive already exists: {archive}")

    output_backed_up = False
    archive_backed_up = False
    published_output = False
    published_archive = False
    try:
        if output.exists():
            os.replace(output, previous_output)
            output_backed_up = True
        if archive.exists():
            os.replace(archive, previous_archive)
            archive_backed_up = True
        os.replace(staged_output, output)
        published_output = True
        os.replace(staged_archive, archive)
        published_archive = True
    except BaseException as exc:
        rollback_errors: list[str] = []
        if published_archive and archive.exists():
            try:
                archive.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"remove new archive: {rollback_exc}")
        if published_output and output.exists():
            try:
                _remove_tree(output)
            except OSError as rollback_exc:
                rollback_errors.append(f"remove new directory: {rollback_exc}")
        if output_backed_up and previous_output.exists():
            try:
                os.replace(previous_output, output)
            except OSError as rollback_exc:
                rollback_errors.append(f"restore previous directory: {rollback_exc}")
        if archive_backed_up and previous_archive.exists():
            try:
                os.replace(previous_archive, archive)
            except OSError as rollback_exc:
                rollback_errors.append(f"restore previous archive: {rollback_exc}")
        if rollback_errors:
            raise BuildDistributionError(
                "release publication failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    if previous_output.exists():
        _remove_tree(previous_output)
    if previous_archive.exists():
        previous_archive.unlink()


def _run_core_self_check() -> None:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "quality/run.py",
        "--profile",
        "all",
    ]
    result = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        command_text = " ".join(command)
        raise BuildDistributionError(
            "refusing to build distribution because kernel self-check failed: "
            + command_text
        )


def _verify_staged_distribution(output: Path) -> None:
    """Exercise the staged launcher without importing from the source tree."""

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)
    checks = (
        ("kernel integrity", [sys.executable, "run.py", "verify-kernel"]),
        (
            "Python example validation",
            [
                sys.executable,
                "run.py",
                "validate",
                "--config",
                "python_project/configs/main.jsonc",
            ],
        ),
    )
    for label, command in checks:
        completed = subprocess.run(
            command,
            cwd=output,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            continue
        diagnostic = completed.stderr.strip() or completed.stdout.strip()
        raise BuildDistributionError(
            f"staged distribution {label} failed"
            + (f": {diagnostic}" if diagnostic else "")
        )


def _copy_tree(
    source: Path,
    target: Path,
    *,
    excluded_top_level: set[str] | None = None,
) -> None:
    excluded = excluded_top_level or set()
    for path in source.rglob("*"):
        relative = path.relative_to(source)
        if not relative.parts or relative.parts[0] in excluded or _ignored(relative):
            continue
        if path.is_symlink():
            raise BuildDistributionError(
                f"refusing to copy a symlink into the distribution: {path}"
            )
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


def _copy_javascript_project(target: Path) -> None:
    source_root = ROOT / JAVASCRIPT_TEMPLATE_RELATIVE
    for relative_text in JAVASCRIPT_TEMPLATE_FILES:
        relative = Path(relative_text)
        source = source_root / relative
        if not source.is_file():
            raise BuildDistributionError(
                f"JavaScript distribution template source is missing: {source}"
            )
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    package_payload = {
        "name": "vibeflow-javascript-example",
        "version": VERSION,
        "private": True,
        "type": "module",
        "devDependencies": {
            "esbuild": "0.28.1",
            "typescript": "7.0.2",
        },
    }
    (target / "package.json").write_text(
        json.dumps(package_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lock_path = target / "package-lock.json"
    lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
    lock_payload["name"] = package_payload["name"]
    lock_payload["version"] = VERSION
    root_package = lock_payload.get("packages", {}).get("")
    if not isinstance(root_package, dict):
        raise BuildDistributionError(
            "JavaScript template lockfile has no root package record"
        )
    root_package["name"] = package_payload["name"]
    root_package["version"] = VERSION
    lock_path.write_text(
        json.dumps(lock_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    project_config = {
        "project_target": "javascript",
        "descriptors": {
            "nodes": ["manifests/nodes"],
            "base_lib": ["manifests/base_lib"],
            "data_schemas": ["manifests/data"],
            "capabilities": ["manifests/capabilities"],
            "plugins": ["manifests/plugins"],
            "host_extensions": ["manifests/host_extensions"],
        },
        "javascript": {
            "package_root": ".",
            "external_packages": [],
        },
        "architecture": {
            "documents": [
                {
                    "workflow": "configs/linear.jsonc",
                    "document": "ARCHITECTURE.jsonc",
                },
                {
                    "workflow": "configs/browser_permanent_port_host.jsonc",
                    "document": "PERMANENT_PORT_ARCHITECTURE.jsonc",
                },
            ]
        },
        "quality_enabled": True,
    }
    (target / "vibeflow_project.jsonc").write_text(
        json.dumps(project_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def _copy_license(output: Path) -> None:
    source = ROOT / "LICENSE"
    if not source.is_file():
        raise BuildDistributionError(f"VibeFlow license file is missing: {source}")
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


def _write_distribution_archive(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        target,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        directories = [source, *(path for path in source.rglob("*") if path.is_dir())]
        for directory in sorted(
            directories,
            key=lambda item: (
                len(item.relative_to(source).parts),
                item.relative_to(source).as_posix(),
            ),
        ):
            relative = directory.relative_to(source)
            archive_name = ARCHIVE_ROOT_NAME
            if relative.parts:
                archive_name += "/" + relative.as_posix()
            info = zipfile.ZipInfo(archive_name.rstrip("/") + "/")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (0o40755 << 16) | 0x10
            archive.writestr(info, b"")
        for path in sorted(
            (path for path in source.rglob("*") if path.is_file()),
            key=lambda item: item.relative_to(source).as_posix(),
        ):
            relative = path.relative_to(source)
            info = zipfile.ZipInfo(f"{ARCHIVE_ROOT_NAME}/{relative.as_posix()}")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


def _verify_distribution_archive(source: Path, archive_path: Path) -> None:
    expected = {
        path.relative_to(source).as_posix(): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if not names or names[0] != f"{ARCHIVE_ROOT_NAME}/":
            raise BuildDistributionError(
                "distribution archive must have vibeflow-distribution/ as its only root"
            )
        unexpected_roots = {
            name.split("/", 1)[0]
            for name in names
            if name and name.split("/", 1)[0] != ARCHIVE_ROOT_NAME
        }
        if unexpected_roots:
            raise BuildDistributionError(
                f"distribution archive has unexpected roots: {sorted(unexpected_roots)}"
            )
        actual = {
            name.removeprefix(f"{ARCHIVE_ROOT_NAME}/"): archive.read(name)
            for name in names
            if not name.endswith("/")
        }
    if actual != expected:
        changed = sorted(
            key
            for key in set(actual) | set(expected)
            if actual.get(key) != expected.get(key)
        )
        raise BuildDistributionError(
            f"distribution archive verification failed for: {changed}"
        )


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
    for relative in PYTHON_STANDARD_DIRS:
        (output / "python_project" / relative).mkdir(parents=True, exist_ok=True)


def _write_workspace_config(output: Path) -> None:
    payload = {
        "policy": {},
        "roots": [
            {"id": "python-project", "path": "python_project"},
            {"id": "javascript-project", "path": "javascript_project"},
        ],
    }
    (output / "vibeflow_config.jsonc").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_javascript_architecture(output: Path) -> None:
    """Generate the canonical JS Architecture view without platform selection."""

    script = """
import os
import sys
from vibeflow.tooling.application.javascript.audit import (
    JavascriptAuditRequest,
    audit_javascript_project,
    render_architecture,
)

result = audit_javascript_project(
    JavascriptAuditRequest(
        workspace=os.environ["VF_DISTRIBUTION_WORKSPACE"],
        config=os.environ["VF_DISTRIBUTION_JS_CONFIG"],
        audit_sources=False,
    )
)
sys.stdout.write(render_architecture(result))
""".strip()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src")
    environment["VF_DISTRIBUTION_WORKSPACE"] = str(
        output / "vibeflow_config.jsonc"
    )
    specs = (
        ("configs/linear.jsonc", "ARCHITECTURE.jsonc"),
        (
            "configs/browser_permanent_port_host.jsonc",
            "PERMANENT_PORT_ARCHITECTURE.jsonc",
        ),
    )
    for config_relative, architecture_relative in specs:
        environment["VF_DISTRIBUTION_JS_CONFIG"] = str(
            output / "javascript_project" / config_relative
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise BuildDistributionError(
                "failed to generate JavaScript Architecture document for "
                f"{config_relative}: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )
        architecture = output / "javascript_project" / architecture_relative
        architecture.write_text(completed.stdout, encoding="utf-8")


def _write_distribution_metadata(output: Path) -> None:
    kernel_archive = output / KERNEL_ZIP_RELATIVE
    payload = {
        "schema": "vibeflow.distribution.v1",
        "version": VERSION,
        "roots": [
            {
                "id": "python-project",
                "path": "python_project",
                "project_target": "python",
            },
            {
                "id": "javascript-project",
                "path": "javascript_project",
                "project_target": "javascript",
            },
        ],
        "kernel": {
            "archive": KERNEL_ZIP_RELATIVE.as_posix(),
            "sha256": _hash_file(kernel_archive),
        },
    }
    (output / "DISTRIBUTION.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    if path.is_symlink() or not path.is_dir():
        path.unlink()
        return
    for item in sorted(path.rglob("*"), key=lambda candidate: len(candidate.parts), reverse=True):
        if item.is_symlink() or not item.is_dir():
            item.unlink()
        else:
            item.rmdir()
    path.rmdir()


def _ignored(relative: Path) -> bool:
    ignored_names = {
        "__pycache__",
        ".pytest_cache",
        ".artifacts",
        "runs",
        "reports",
        "node_modules",
    }
    return any(part in ignored_names or part.endswith(".pyc") for part in relative.parts)


if __name__ == "__main__":
    raise SystemExit(main())
