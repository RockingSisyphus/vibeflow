from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.resources import as_file
import json
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any, Mapping

from vibeflow.targets.javascript.resources import resource


NODE_MINIMUM = (22, 12, 0)
TYPESCRIPT_MINIMUM = (7, 0, 0)
TYPESCRIPT_MAXIMUM = (8, 0, 0)
ESBUILD_MINIMUM = (0, 28, 0)
ESBUILD_MAXIMUM = (0, 29, 0)
LOCK_FILES = ("package-lock.json",)
UNVERIFIED_LOCK_FILES = ("pnpm-lock.yaml", "yarn.lock")


class AotToolchainError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: tuple[Mapping[str, Any], ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.diagnostics = diagnostics


@dataclass(frozen=True)
class ToolchainInfo:
    node: str
    typescript: str
    esbuild: str
    lock_sha256: str
    lock_files: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "typescript": self.typescript,
            "esbuild": self.esbuild,
            "lock_sha256": self.lock_sha256,
            "lock_files": list(self.lock_files),
        }


@dataclass(frozen=True)
class AuditToolchainInfo:
    """The platform-neutral parser toolchain used outside AOT builds."""

    node: str
    typescript: str

    def to_dict(self) -> dict[str, str]:
        return {
            "node": self.node,
            "typescript": self.typescript,
        }


@dataclass(frozen=True)
class DriverBuildResult:
    toolchain: ToolchainInfo
    outputs: tuple[str, ...]
    inputs: tuple[str, ...]


@dataclass(frozen=True)
class DriverAuditResult:
    toolchain: AuditToolchainInfo


def probe_toolchain(
    package_root: str | Path,
    *,
    node_command: str = "node",
) -> ToolchainInfo:
    root = _validated_package_root(package_root)
    lock_files, lock_sha256 = _lock_identity(root)
    payload = _run_driver(
        {
            "command": "probe",
            "packageRoot": str(root),
        },
        node_command=node_command,
    )
    probe = payload.get("probe")
    if not isinstance(probe, Mapping):
        raise AotToolchainError(
            "VF_PROTOCOL",
            "toolchain driver omitted its probe result",
        )
    info = ToolchainInfo(
        node=str(probe.get("node", "")),
        typescript=str(probe.get("typescript", "")),
        esbuild=str(probe.get("esbuild", "")),
        lock_sha256=lock_sha256,
        lock_files=lock_files,
    )
    _validate_versions(info)
    _validate_lock_tool_versions(root, lock_files, info)
    return info


def run_build_driver(
    request: Mapping[str, Any],
    *,
    package_root: str | Path,
    node_command: str = "node",
) -> DriverBuildResult:
    root = _validated_package_root(package_root)
    lock_files, lock_sha256 = _lock_identity(root)
    payload = _run_driver(
        {
            **dict(request),
            "command": "build",
            "packageRoot": str(root),
        },
        node_command=node_command,
    )
    probe = payload.get("probe")
    build = payload.get("build")
    if not isinstance(probe, Mapping) or not isinstance(build, Mapping):
        raise AotToolchainError(
            "VF_PROTOCOL",
            "toolchain driver returned an incomplete build result",
        )
    info = ToolchainInfo(
        node=str(probe.get("node", "")),
        typescript=str(probe.get("typescript", "")),
        esbuild=str(probe.get("esbuild", "")),
        lock_sha256=lock_sha256,
        lock_files=lock_files,
    )
    _validate_versions(info)
    _validate_lock_tool_versions(root, lock_files, info)
    return DriverBuildResult(
        toolchain=info,
        outputs=tuple(sorted(str(item) for item in build.get("outputs", ()))),
        inputs=tuple(sorted(str(item) for item in build.get("inputs", ()))),
    )


def run_audit_driver(
    request: Mapping[str, Any],
    *,
    package_root: str | Path,
    node_command: str = "node",
) -> DriverAuditResult:
    """Run only VibeFlow ownership/completion audits, without bundling.

    The audit intentionally ignores ordinary TypeScript semantic diagnostics
    and runtime-platform API compatibility.  Those belong to project-selected
    language tools and tests rather than the VibeFlow architecture contract.
    """

    root = _validated_package_root(package_root)
    payload = _run_driver(
        {
            **dict(request),
            "command": "audit",
            "packageRoot": str(root),
            "target": "neutral",
            "profile": "",
            "contractCheckFiles": [],
        },
        node_command=node_command,
    )
    probe = payload.get("probe")
    audit = payload.get("audit")
    if not isinstance(probe, Mapping) or not isinstance(audit, Mapping):
        raise AotToolchainError(
            "VF_PROTOCOL",
            "toolchain driver returned an incomplete audit result",
        )
    info = AuditToolchainInfo(
        node=str(probe.get("node", "")),
        typescript=str(probe.get("typescript", "")),
    )
    _validate_audit_versions(info)
    return DriverAuditResult(toolchain=info)


def _validated_package_root(value: str | Path) -> Path:
    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise AotToolchainError(
            "VF_TOOLCHAIN_MISSING",
            f"JavaScript package_root does not exist: {root}",
        )
    if not (root / "package.json").is_file():
        raise AotToolchainError(
            "VF_TOOLCHAIN_MISSING",
            f"JavaScript package_root has no package.json: {root}",
        )
    return root


def _lock_identity(root: Path) -> tuple[tuple[str, ...], str]:
    paths = tuple(
        root / name
        for name in (*LOCK_FILES, *UNVERIFIED_LOCK_FILES)
        if (root / name).is_file()
    )
    if not paths:
        raise AotToolchainError(
            "VF_TOOLCHAIN_MISSING",
            (
                "JavaScript package_root must contain package-lock.json"
            ),
        )
    if len(paths) != 1:
        raise AotToolchainError(
            "VF_TOOLCHAIN_LOCK",
            (
                "JavaScript package_root must contain exactly one supported "
                f"lockfile, found {[path.name for path in paths]}"
            ),
        )
    if paths[0].name != "package-lock.json":
        raise AotToolchainError(
            "VF_TOOLCHAIN_LOCK",
            (
                f"{paths[0].name} cannot yet be verified against installed "
                "TypeScript/esbuild versions; use package-lock.json"
            ),
        )
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return tuple(path.name for path in paths), digest.hexdigest()


def _validate_lock_tool_versions(
    root: Path,
    lock_files: tuple[str, ...],
    info: ToolchainInfo,
) -> None:
    if lock_files != ("package-lock.json",):
        return
    lock_path = root / "package-lock.json"
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AotToolchainError(
            "VF_TOOLCHAIN_LOCK",
            f"package-lock.json cannot be parsed: {lock_path}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise AotToolchainError(
            "VF_TOOLCHAIN_LOCK",
            "package-lock.json must contain a JSON object",
        )
    for package, actual in (
        ("typescript", info.typescript),
        ("esbuild", info.esbuild),
    ):
        locked = _package_lock_version(payload, package)
        if not locked:
            raise AotToolchainError(
                "VF_TOOLCHAIN_LOCK",
                f"package-lock.json does not lock required package '{package}'",
            )
        if _normalized_exact_version(locked) != _normalized_exact_version(actual):
            raise AotToolchainError(
                "VF_TOOLCHAIN_LOCK",
                (
                    f"installed {package} version {actual} does not match "
                    f"package-lock.json version {locked}"
                ),
            )


def _package_lock_version(
    payload: Mapping[str, Any],
    package: str,
) -> str:
    packages = payload.get("packages")
    if isinstance(packages, Mapping):
        entry = packages.get(f"node_modules/{package}")
        if isinstance(entry, Mapping) and entry.get("version"):
            return str(entry["version"])
    dependencies = payload.get("dependencies")
    if isinstance(dependencies, Mapping):
        entry = dependencies.get(package)
        if isinstance(entry, Mapping) and entry.get("version"):
            return str(entry["version"])
    return ""


def _normalized_exact_version(value: str) -> tuple[int, int, int]:
    return _version_tuple(str(value).split("-", 1)[0], subject="package version")


def _run_driver(
    request: Mapping[str, Any],
    *,
    node_command: str,
) -> Mapping[str, Any]:
    request_text = json.dumps(
        dict(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="vibeflow-aot-",
        delete=False,
    ) as handle:
        handle.write(request_text)
        request_path = Path(handle.name)
    try:
        driver = resource("toolchain_driver.mjs")
        with as_file(driver) as driver_path:
            try:
                completed = subprocess.run(
                    [node_command, str(driver_path), str(request_path)],
                    check=False,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=180,
                )
            except FileNotFoundError as exc:
                raise AotToolchainError(
                    "VF_TOOLCHAIN_MISSING",
                    f"Node.js executable was not found: {node_command}",
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise AotToolchainError(
                    "VF_TOOLCHAIN_TIMEOUT",
                    "JavaScript build driver timed out",
                ) from exc
    finally:
        request_path.unlink(missing_ok=True)
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise AotToolchainError(
            "VF_PROTOCOL",
            f"JavaScript build driver returned invalid JSON: {detail}",
        ) from exc
    if not isinstance(payload, Mapping):
        raise AotToolchainError(
            "VF_PROTOCOL",
            "JavaScript build driver result must be an object",
        )
    if not bool(payload.get("ok")):
        error = payload.get("error")
        error_mapping = error if isinstance(error, Mapping) else {}
        details = error_mapping.get("details")
        detail_mapping = details if isinstance(details, Mapping) else {}
        diagnostic_values = detail_mapping.get("diagnostics", ())
        diagnostics = tuple(
            dict(item)
            for item in diagnostic_values
            if isinstance(item, Mapping)
        )
        raise AotToolchainError(
            str(error_mapping.get("code", "VF_TOOLCHAIN_INTERNAL")),
            str(error_mapping.get("message", "JavaScript build driver failed")),
            diagnostics=diagnostics,
        )
    if completed.returncode != 0:
        raise AotToolchainError(
            "VF_PROTOCOL",
            "JavaScript build driver exited unsuccessfully with an ok result",
        )
    return payload


def _validate_versions(info: ToolchainInfo) -> None:
    node = _version_tuple(info.node, subject="Node.js")
    typescript = _version_tuple(info.typescript, subject="TypeScript")
    esbuild = _version_tuple(info.esbuild, subject="esbuild")
    if node < NODE_MINIMUM:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"Node.js >=22.12 is required, found {info.node}",
        )
    if not TYPESCRIPT_MINIMUM <= typescript < TYPESCRIPT_MAXIMUM:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"TypeScript >=7 <8 is required, found {info.typescript}",
        )
    if not ESBUILD_MINIMUM <= esbuild < ESBUILD_MAXIMUM:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"esbuild >=0.28 <0.29 is required, found {info.esbuild}",
        )


def _validate_audit_versions(info: AuditToolchainInfo) -> None:
    node = _version_tuple(info.node, subject="Node.js")
    typescript = _version_tuple(info.typescript, subject="TypeScript")
    if node < NODE_MINIMUM:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"Node.js >=22.12 is required, found {info.node}",
        )
    if not TYPESCRIPT_MINIMUM <= typescript < TYPESCRIPT_MAXIMUM:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"TypeScript >=7 <8 is required, found {info.typescript}",
        )


def _version_tuple(value: str, *, subject: str) -> tuple[int, int, int]:
    match = re.match(r"^v?(\d+)\.(\d+)(?:\.(\d+))?", str(value).strip())
    if match is None:
        raise AotToolchainError(
            "VF_TOOLCHAIN_VERSION",
            f"{subject} returned an invalid version: {value!r}",
        )
    return (
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3) or 0),
    )


__all__ = [
    "AotToolchainError",
    "AuditToolchainInfo",
    "DriverAuditResult",
    "DriverBuildResult",
    "ToolchainInfo",
    "probe_toolchain",
    "run_audit_driver",
    "run_build_driver",
]
