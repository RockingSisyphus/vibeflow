from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import unquote, urlsplit
import zipfile
from pathlib import Path

sys.dont_write_bytecode = True

try:
    from .profile_config import (
        DistributionProfile,
        DistributionProfileError,
        PROFILE_NAMES,
        load_distribution_profiles,
    )
except ImportError:  # direct ``python distribution/build.py`` execution
    from profile_config import (
        DistributionProfile,
        DistributionProfileError,
        PROFILE_NAMES,
        load_distribution_profiles,
    )

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dist" / "vibeflow-distribution"
DEFAULT_AUTONOMOUS_OUTPUT = ROOT / "dist" / "vibeflow-distribution-autonomous"
DEFAULT_ARCHIVE_DIR = ROOT / "archive"
ARCHIVE_ROOT_NAME = "vibeflow-distribution"
MINIMAL_PROJECTS_RELATIVE = Path("distribution/minimal_projects")
PROFILES_PATH = ROOT / "distribution" / "profiles.jsonc"
PYTHON_STANDARD_DIRS = (
    "nodes",
    "configs",
)
MANIFEST_RELATIVE = Path("kernel/MANIFEST.sha256")
KERNEL_ZIP_RELATIVE = Path("kernel/vibeflow-kernel.zip")
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
ARCHIVE_NAME = f"vibeflow-distribution-{VERSION}.zip"
AUTONOMOUS_ARCHIVE_NAME = f"vibeflow-distribution-autonomous-{VERSION}.zip"
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


@dataclass(frozen=True)
class ReleaseSetArtifacts:
    collaborative: DistributionArtifacts
    autonomous: DistributionArtifacts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the copyable VibeFlow distribution directory and deterministic ZIP."
    )
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--output-dir",
        type=Path,
        help=f"distribution directory to publish (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--autonomous-output-dir",
        type=Path,
        help="autonomous distribution directory when --profile all",
    )
    parser.add_argument(
        "--profile",
        choices=("all", *PROFILE_NAMES),
        default="all",
        help="distribution profile to publish (default: all)",
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
    if output is None:
        output = DEFAULT_AUTONOMOUS_OUTPUT if args.profile == "autonomous" else DEFAULT_OUTPUT
    try:
        if args.profile == "all":
            autonomous_output = args.autonomous_output_dir or _default_autonomous_sibling(output)
            release_set = build_release_set(
                output,
                autonomous_output=autonomous_output,
                archive_dir=args.archive_dir,
                replace=not args.keep_existing,
            )
            artifacts_list = (release_set.collaborative, release_set.autonomous)
        else:
            if args.autonomous_output_dir is not None:
                raise BuildDistributionError("--autonomous-output-dir is only valid with --profile all")
            artifacts_list = (
                build_release(
                    output,
                    archive_dir=args.archive_dir,
                    replace=not args.keep_existing,
                    profile=args.profile,
                ),
            )
    except BuildDistributionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for artifacts in artifacts_list:
        print(f"built distribution directory: {artifacts.directory}")
        print(f"built distribution archive: {artifacts.archive}")
    return 0


def build_release(
    output: Path = DEFAULT_OUTPUT,
    *,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    replace: bool = True,
    run_self_check: bool = True,
    profile: str = "collaborative",
) -> DistributionArtifacts:
    profiles = _load_profiles()
    selected = _select_profile(profiles, profile)
    output = _safe_output_path(output)
    archive_dir = _safe_archive_dir(archive_dir)
    archive = archive_dir / _archive_name(profile)
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
        _populate_distribution(staged_output, profile=selected)
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


def build_release_set(
    collaborative_output: Path = DEFAULT_OUTPUT,
    *,
    autonomous_output: Path = DEFAULT_AUTONOMOUS_OUTPUT,
    archive_dir: Path = DEFAULT_ARCHIVE_DIR,
    replace: bool = True,
    run_self_check: bool = True,
) -> ReleaseSetArtifacts:
    profiles = _load_profiles()
    outputs = {
        "collaborative": _safe_output_path(collaborative_output),
        "autonomous": _safe_output_path(autonomous_output),
    }
    archive_dir = _safe_archive_dir(archive_dir)
    archives = {name: archive_dir / _archive_name(name) for name in PROFILE_NAMES}
    targets = [*outputs.values(), *archives.values()]
    for left_index, left in enumerate(targets):
        for right in targets[left_index + 1 :]:
            if left == right or left in right.parents or right in left.parents:
                raise BuildDistributionError(f"release-set paths must not overlap: {left}; {right}")
    if not replace:
        existing = [path for path in targets if path.exists()]
        if existing:
            raise BuildDistributionError(f"release target already exists: {existing[0]}")
    if run_self_check:
        _run_core_self_check()

    staging: dict[Path, tuple[Path, Path]] = {}
    try:
        for name in PROFILE_NAMES:
            output = outputs[name]
            archive = archives[name]
            output.parent.mkdir(parents=True, exist_ok=True)
            archive.parent.mkdir(parents=True, exist_ok=True)
            output_root = Path(tempfile.mkdtemp(prefix=f".{output.name}.vibeflow-build-", dir=output.parent))
            archive_root = Path(tempfile.mkdtemp(prefix=f".{archive.name}.vibeflow-build-", dir=archive.parent))
            staged_output = output_root / "payload"
            staged_archive = archive_root / archive.name
            staging[output] = (staged_output, output_root)
            staging[archive] = (staged_archive, archive_root)
            _populate_distribution(staged_output, profile=profiles[name])
            _verify_staged_distribution(staged_output)
            _write_distribution_archive(staged_output, staged_archive)
            _verify_distribution_archive(staged_output, staged_archive)
        _publish_release_targets(staging, replace=replace)
    finally:
        for _, root in staging.values():
            if root.exists():
                _remove_tree(root)
    return ReleaseSetArtifacts(
        collaborative=DistributionArtifacts(outputs["collaborative"], archives["collaborative"]),
        autonomous=DistributionArtifacts(outputs["autonomous"], archives["autonomous"]),
    )


def build_distribution(
    output: Path,
    *,
    replace: bool = True,
    run_self_check: bool = True,
    profile: str = "collaborative",
) -> Path:
    """Build only a directory for programmatic tests and compatibility callers.

    The command-line release builder always uses :func:`build_release` and
    publishes the matching deterministic outer ZIP as well.
    """

    selected = _select_profile(_load_profiles(), profile)
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
        _populate_distribution(staged_output, profile=selected)
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
    allowed_repository_outputs = {DEFAULT_OUTPUT.resolve(), DEFAULT_AUTONOMOUS_OUTPUT.resolve()}
    if (resolved == ROOT or ROOT in resolved.parents) and resolved not in allowed_repository_outputs:
        raise BuildDistributionError(
            "distribution output inside the source repository must be the canonical release path: "
            f"{resolved}"
        )
    return resolved


def _default_autonomous_sibling(collaborative_output: Path) -> Path:
    return collaborative_output.with_name(f"{collaborative_output.name}-autonomous")


def _archive_name(profile: str) -> str:
    return ARCHIVE_NAME if profile == "collaborative" else AUTONOMOUS_ARCHIVE_NAME


def _load_profiles() -> dict[str, DistributionProfile]:
    try:
        return load_distribution_profiles(PROFILES_PATH)
    except DistributionProfileError as exc:
        raise BuildDistributionError(str(exc)) from exc


def _select_profile(
    profiles: dict[str, DistributionProfile], profile: str
) -> DistributionProfile:
    try:
        return profiles[profile]
    except KeyError as exc:
        raise BuildDistributionError(f"unknown distribution profile: {profile}") from exc


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


def _populate_distribution(output: Path, *, profile: DistributionProfile | None = None) -> None:
    profile = profile or _select_profile(_load_profiles(), "collaborative")
    output.mkdir(parents=True)
    _copy_tree(
        ROOT / "distribution" / "kernel_development_pack" / "project_template",
        output,
        excluded_top_level={"project", "AGENTS.md", "README.md"},
    )
    _copy_tree(
        ROOT / MINIMAL_PROJECTS_RELATIVE / "python_project",
        output / "python_project",
    )
    _copy_tree(
        ROOT / MINIMAL_PROJECTS_RELATIVE / "javascript_project",
        output / "javascript_project",
    )
    _write_profile_assets(output, profile)
    _copy_mermaid_renderer_config(output)
    _copy_license(output)
    _copy_third_party_notices(output)
    _write_kernel_archive(ROOT / "src" / "vibeflow", output / KERNEL_ZIP_RELATIVE)
    _ensure_standard_project_dirs(output)
    _write_workspace_config(output)
    _write_python_architecture(output)
    _write_javascript_architecture(output)
    _write_distribution_metadata(output, profile=profile)
    _write_kernel_manifest(output)
    _normalize_output_modes(output)


def _write_profile_assets(output: Path, profile: DistributionProfile) -> None:
    prompt_parts = [path.read_text(encoding="utf-8").rstrip() for path in profile.prompt_fragments]
    (output / "AGENTS.md").write_text("\n\n".join(prompt_parts) + "\n", encoding="utf-8")
    profile_title = "人机协同" if profile.name == "collaborative" else "无人值守"
    (output / "README.md").write_text(
        f"# VibeFlow {VERSION} {profile_title}开发包\n\n"
        "本发行包包含相同内核下的最小 Python Runtime 与 JavaScript AOT 项目。"
        "先阅读 `AGENTS.md` 和 `kernel/docs/README.md`。\n",
        encoding="utf-8",
    )
    docs_root = output / "kernel" / "docs"
    docs_root.mkdir(parents=True, exist_ok=True)
    for source in profile.documents:
        destination = docs_root / source.relative_to(ROOT / "docs")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    profile_document = next(
        source.relative_to(ROOT / "docs").as_posix()
        for source in profile.documents
        if source.parent.name == "profiles"
    )
    links = [
        f"- [{source.stem}]({source.relative_to(ROOT / 'docs').as_posix()})"
        for source in profile.documents
    ]
    (docs_root / "README.md").write_text(
        "# VibeFlow 使用者文档\n\n"
        f"当前开发协议：[{profile.name}]({profile_document})。\n\n"
        "按任务阅读以下规范：\n\n"
        + "\n".join(links)
        + "\n",
        encoding="utf-8",
    )


def _publish_release_targets(
    staging: dict[Path, tuple[Path, Path]], *, replace: bool
) -> None:
    backups: dict[Path, Path] = {}
    published: list[Path] = []
    try:
        for target, (staged, root) in staging.items():
            if target.exists():
                if not replace:
                    raise BuildDistributionError(f"release target already exists: {target}")
                backup = root / "previous"
                os.replace(target, backup)
                backups[target] = backup
            os.replace(staged, target)
            published.append(target)
    except BaseException as exc:
        rollback_errors: list[str] = []
        for target in reversed(published):
            try:
                if target.is_dir() and not target.is_symlink():
                    _remove_tree(target)
                elif target.exists() or target.is_symlink():
                    target.unlink()
            except OSError as rollback_exc:
                rollback_errors.append(f"remove {target}: {rollback_exc}")
        for target, backup in backups.items():
            try:
                if backup.exists():
                    os.replace(backup, target)
            except OSError as rollback_exc:
                rollback_errors.append(f"restore {target}: {rollback_exc}")
        if rollback_errors:
            raise BuildDistributionError(
                "release-set publication failed and rollback was incomplete: "
                + "; ".join(rollback_errors)
            ) from exc
        raise
    for backup in backups.values():
        if backup.is_dir():
            _remove_tree(backup)
        elif backup.exists():
            backup.unlink()


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

    _verify_profile_assets(output)

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)
    checks = (
        ("kernel integrity", [sys.executable, "run.py", "verify-kernel"]),
        (
            "Python minimal project validation",
            [
                sys.executable,
                "run.py",
                "validate",
                "--config",
                "python_project/configs/main.jsonc",
            ],
        ),
        (
            "Python workflow execution probe",
            [
                sys.executable,
                "run.py",
                "run",
                "--config",
                "python_project/configs/main.jsonc",
                "--input",
                "python_project/probe_input.json",
                "--run-root",
                str(output.parent / "probe-runs"),
                "--run-id",
                "distribution-probe",
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


def _verify_profile_assets(output: Path) -> None:
    try:
        metadata = json.loads((output / "DISTRIBUTION.json").read_text(encoding="utf-8"))
        profile = _select_profile(_load_profiles(), str(metadata.get("development_profile", "")))
    except (OSError, json.JSONDecodeError, BuildDistributionError) as exc:
        raise BuildDistributionError(f"distribution profile metadata is invalid: {exc}") from exc
    if (
        metadata.get("agent_protocol") != dict(profile.agent_protocol)
        or metadata.get("agent_automation") != dict(profile.agent_automation)
    ):
        raise BuildDistributionError("distribution metadata does not match the selected agent protocol")
    expected_prompt = "\n\n".join(
        path.read_text(encoding="utf-8").rstrip()
        for path in profile.prompt_fragments
    ) + "\n"
    if (output / "AGENTS.md").read_text(encoding="utf-8") != expected_prompt:
        raise BuildDistributionError("generated AGENTS.md does not match its distribution profile")
    docs_root = output / "kernel" / "docs"
    actual_docs = sorted(
        path.relative_to(docs_root)
        for path in docs_root.rglob("*.md")
        if path.is_file() and path.name != "README.md"
    )
    expected_paths = sorted(source.relative_to(ROOT / "docs") for source in profile.documents)
    if actual_docs != expected_paths:
        raise BuildDistributionError("generated profile document set is incomplete or contains extras")
    for source in profile.documents:
        relative = source.relative_to(ROOT / "docs")
        if (docs_root / relative).read_bytes() != source.read_bytes():
            raise BuildDistributionError(f"generated profile document differs from source: {relative}")
    _verify_distribution_document_links(output)


def _verify_distribution_document_links(output: Path) -> None:
    """Resolve packaged guidance links from their published locations."""

    documents = [output / "AGENTS.md", output / "README.md"]
    documents.extend(sorted((output / "kernel" / "docs").rglob("*.md")))
    for document in documents:
        source = document.read_text(encoding="utf-8")
        for raw_target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", source):
            target = raw_target.strip()
            if target.startswith("<") and target.endswith(">"):
                target = target[1:-1].strip()
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                if parsed.scheme == "file":
                    raise BuildDistributionError(
                        f"distribution document uses a file URI: {document.relative_to(output)}: {target}"
                    )
                continue
            if not parsed.path:
                continue
            relative = Path(unquote(parsed.path))
            if relative.is_absolute():
                raise BuildDistributionError(
                    f"distribution document uses an absolute link: {document.relative_to(output)}: {target}"
                )
            destination = (document.parent / relative).resolve()
            try:
                destination.relative_to(output.resolve())
            except ValueError as exc:
                raise BuildDistributionError(
                    f"distribution document link escapes the package: {document.relative_to(output)}: {target}"
                ) from exc
            if not destination.is_file():
                raise BuildDistributionError(
                    f"distribution document link is missing in the package: {document.relative_to(output)}: {target}"
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
    specs = (("configs/main.jsonc", "ARCHITECTURE.jsonc"),)
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


def _write_python_architecture(output: Path) -> None:
    script = """
import sys
from vibeflow.tooling.application.cli import main
raise SystemExit(main(sys.argv[1:]))
""".strip()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(ROOT / "src")
    command = [
        sys.executable,
        "-c",
        script,
        "export-architecture",
        "--workspace",
        str(output / "vibeflow_config.jsonc"),
        "--config",
        str(output / "python_project" / "configs" / "main.jsonc"),
        "--output",
        str(output / "python_project" / "ARCHITECTURE.jsonc"),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BuildDistributionError(
            "failed to generate Python Architecture document: "
            + (completed.stderr.strip() or completed.stdout.strip())
        )


def _write_distribution_metadata(output: Path, *, profile: DistributionProfile) -> None:
    kernel_archive = output / KERNEL_ZIP_RELATIVE
    payload = {
        "schema": "vibeflow.distribution.v2",
        "version": VERSION,
        "development_profile": profile.name,
        "agent_protocol": dict(profile.agent_protocol),
        "agent_automation": dict(profile.agent_automation),
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
