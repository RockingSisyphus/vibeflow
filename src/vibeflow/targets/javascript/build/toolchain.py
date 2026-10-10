from __future__ import annotations

from dataclasses import dataclass
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "typescript": self.typescript,
            "esbuild": self.esbuild,
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


@dataclass(frozen=True)
class DriverQualityResult:
    toolchain: AuditToolchainInfo
    files: tuple[Mapping[str, Any], ...]
    findings: tuple[Mapping[str, Any], ...]
    implementations: tuple[Mapping[str, Any], ...] = ()


def probe_toolchain(
    package_root: str | Path,
    *,
    node_command: str = "node",
) -> ToolchainInfo:
    root = _validated_package_root(package_root)
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
    )
    _validate_versions(info)
    return info


def run_build_driver(
    request: Mapping[str, Any],
    *,
    package_root: str | Path,
    node_command: str = "node",
) -> DriverBuildResult:
    root = _validated_package_root(package_root)
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
    )
    _validate_versions(info)
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


@dataclass(frozen=True)
class DriverRuleResult:
    toolchain: AuditToolchainInfo
    findings: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    local_sources: tuple[Mapping[str, Any], ...] = ()
    local_quality: Mapping[str, Any] | None = None


def run_rule_check_driver(
    request: Mapping[str, Any], *, package_root: str | Path,
    node_command: str = "node",
) -> DriverRuleResult:
    """Run only source-analysis topics requested by a selected Rule."""
    root = _validated_package_root(package_root)
    payload = _run_driver({**dict(request), "command": "rule-check", "packageRoot": str(root), "target": "neutral", "profile": "", "contractCheckFiles": []}, node_command=node_command)
    probe, result = payload.get("probe"), payload.get("rules")
    if not isinstance(probe, Mapping) or not isinstance(result, Mapping):
        raise AotToolchainError("VF_PROTOCOL", "source Rule driver omitted its result")
    findings, sources = result.get("findings"), result.get("sources")
    if not isinstance(findings, list) or not isinstance(sources, list) or not all(isinstance(value, Mapping) for value in (*findings, *sources)):
        raise AotToolchainError("VF_PROTOCOL", "source Rule driver returned invalid results")
    info = AuditToolchainInfo(str(probe.get("node", "")), str(probe.get("typescript", "")))
    _validate_audit_versions(info)
    return DriverRuleResult(info, tuple(findings), tuple(sources), tuple(result.get("local_sources", ())), result.get("local_quality"))


def run_quality_facts_driver(
    request: Mapping[str, Any],
    *,
    package_root: str | Path,
    node_command: str = "node",
) -> DriverQualityResult:
    """Extract syntax and architecture facts without ownership or type checks."""

    root = _validated_package_root(package_root)
    payload = _run_driver(
        {
            **dict(request),
            "command": "quality-facts",
            "packageRoot": str(root),
            "target": "neutral",
            "profile": "",
            "typecheckFiles": [],
            "contractCheckFiles": [],
        },
        node_command=node_command,
    )
    probe = payload.get("probe")
    quality = payload.get("quality")
    if not isinstance(probe, Mapping) or not isinstance(quality, Mapping):
        raise AotToolchainError("VF_PROTOCOL", "toolchain driver omitted quality facts")
    files = quality.get("files")
    findings = quality.get("findings")
    implementations = quality.get("implementations", [])
    if not isinstance(files, list) or not isinstance(findings, list) or not isinstance(implementations, list) or not all(
        isinstance(item, Mapping) for item in (*files, *findings, *implementations)
    ):
        raise AotToolchainError("VF_PROTOCOL", "toolchain driver returned invalid quality facts")
    info = AuditToolchainInfo(
        node=str(probe.get("node", "")),
        typescript=str(probe.get("typescript", "")),
    )
    _validate_audit_versions(info)
    return DriverQualityResult(info, tuple(files), tuple(findings), tuple(implementations))


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
    from vibeflow.targets.javascript.build.driver_session import current_scope
    active = current_scope()
    if active is not None:
        payload = active.request(request, node_command)
        return _driver_result(payload, 0)
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
        from vibeflow.targets.javascript.resources import materialized_resources
        with materialized_resources() as resource_directory:
            driver_path = resource_directory / "toolchain_driver.mjs"
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
    return _driver_result(payload, completed.returncode)


def _driver_result(payload, returncode):
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
    if returncode != 0:
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
    "DriverQualityResult",
    "ToolchainInfo",
    "probe_toolchain",
    "run_audit_driver",
    "run_rule_check_driver",
    "DriverRuleResult",
    "run_quality_facts_driver",
    "run_build_driver",
]
