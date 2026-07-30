from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any, Mapping

from vibeflow.aot.emitter import EmittedWorkflow
from vibeflow.aot.errors import AotBuildError
from vibeflow.aot.model import PROFILES, TARGETS, WorkflowSpec
from vibeflow.aot.publish import (
    AotPublishError,
    atomic_publish_directory,
    validate_owned_build_directory,
)
from vibeflow.aot.toolchain import DriverBuildResult


BUILD_MANIFEST_FORMAT = "vibeflow.aot-build.v1"
WEB_APP_MARKER = "<!-- VIBEFLOW_APP_ENTRY -->"
SOURCEMAP_MODES = frozenset({"none", "external", "inline"})


def validate_modes(request: Any) -> tuple[str, str, str]:
    target = str(request.target).strip()
    profile = str(request.profile).strip()
    sourcemap = str(request.sourcemap).strip()
    if target not in TARGETS:
        raise AotBuildError(
            "VF_BUILD_TARGET",
            f"target must be one of {sorted(TARGETS)}",
        )
    if profile not in PROFILES:
        raise AotBuildError(
            "VF_BUILD_PROFILE",
            f"profile must be one of {sorted(PROFILES)}",
        )
    if profile == "web-app" and target != "browser":
        raise AotBuildError(
            "VF_BUILD_PROFILE",
            "web-app profile is only valid for the browser target",
        )
    if sourcemap not in SOURCEMAP_MODES:
        raise AotBuildError(
            "VF_BUILD_SOURCEMAP",
            f"sourcemap must be one of {sorted(SOURCEMAP_MODES)}",
        )
    return target, profile, sourcemap


def entry_name(profile: str, supplied: str) -> str:
    value = str(supplied).strip()
    if not value:
        return "workflow.js" if profile == "esm-module" else "index.js"
    if Path(value).name != value or value in {".", ".."}:
        raise AotBuildError(
            "VF_BUILD_PATH",
            "entry_name must be a plain file name",
        )
    if not value.endswith(".js"):
        value = f"{value}.js"
    return value


def web_inputs(
    request: Any,
    *,
    project_root: Path,
    target: str,
    profile: str,
) -> tuple[str | None, Path | None]:
    if profile != "web-app":
        if request.html_template is not None or request.app_entry is not None:
            raise AotBuildError(
                "VF_BUILD_PROFILE",
                "html_template and app_entry are only valid for web-app",
            )
        return None, None
    if request.html_template is None or request.app_entry is None:
        raise AotBuildError(
            "VF_BUILD_PROFILE",
            "web-app requires both html_template and app_entry",
        )
    html_path = resolve_under_project(
        request.html_template,
        project_root=project_root,
        subject="html_template",
        require_file=True,
    )
    app_entry = resolve_under_project(
        request.app_entry,
        project_root=project_root,
        subject="app_entry",
        require_file=True,
    )
    html = html_path.read_text(encoding="utf-8")
    count = html.count(WEB_APP_MARKER)
    if count != 1:
        raise AotBuildError(
            "VF_BUILD_HTML",
            (
                "HTML template must contain exactly one "
                f"{WEB_APP_MARKER!r} marker; found {count}"
            ),
        )
    return html, app_entry


def resolve_under_project(
    value: str | Path,
    *,
    project_root: Path,
    subject: str,
    require_file: bool,
) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = project_root / path
    path = path.resolve()
    if path != project_root and project_root not in path.parents:
        raise AotBuildError(
            "VF_BUILD_PATH",
            f"{subject} must stay within project_root: {path}",
        )
    if require_file and not path.is_file():
        raise AotBuildError(
            "VF_BUILD_PATH",
            f"{subject} does not exist: {path}",
        )
    if not require_file and not path.is_dir():
        raise AotBuildError(
            "VF_BUILD_PATH",
            f"{subject} does not exist: {path}",
        )
    return path


def resolved_implementations(
    workflow: WorkflowSpec,
    *,
    project_root: Path,
    overrides: Mapping[str, object],
) -> dict[str, object]:
    resolved: dict[str, object] = dict(overrides)

    def visit(plan: WorkflowSpec) -> None:
        for node in plan.nodes:
            if node.implementation is not None and node.type_used not in resolved:
                implementation = node.implementation
                module_path = Path(implementation.module).expanduser()
                candidate = (
                    module_path
                    if module_path.is_absolute()
                    else project_root / module_path
                )
                if candidate.is_file():
                    resolved[node.type_used] = {
                        **implementation.to_dict(),
                        "module": str(candidate.resolve()),
                    }
            if node.subplan is not None:
                visit(node.subplan)

    visit(workflow)
    for type_key, value in tuple(resolved.items()):
        if isinstance(value, (str, Path)):
            module = Path(value).expanduser()
            candidate = module if module.is_absolute() else project_root / module
            if candidate.is_file():
                resolved[type_key] = str(candidate.resolve())
        elif isinstance(value, Mapping):
            module_value = value.get(
                "module",
                value.get("entry", value.get("ref", "")),
            )
            if module_value:
                module = Path(str(module_value)).expanduser()
                candidate = module if module.is_absolute() else project_root / module
                if candidate.is_file():
                    resolved[type_key] = {
                        **dict(value),
                        "module": str(candidate.resolve()),
                    }
    return resolved


def write_profile_companions(
    staging: Path,
    *,
    emitted: EmittedWorkflow,
    profile: str,
    entry_name: str,
    html_template: str | None,
) -> None:
    declaration_name = (
        f"{Path(entry_name).stem}.d.ts"
        if profile != "web-app"
        else "workflow.d.ts"
    )
    (staging / declaration_name).write_text(
        emitted.declarations,
        encoding="utf-8",
    )
    if profile == "web-app":
        assert html_template is not None
        html = html_template.replace(
            WEB_APP_MARKER,
            f'<script type="module" src="./{entry_name}"></script>',
        )
        (staging / "index.html").write_text(html, encoding="utf-8")


def driver_import_policy(
    supplied: Mapping[str, Any],
    *,
    external_packages: tuple[str, ...],
    generated_root: Path,
) -> dict[str, Any]:
    policy = dict(supplied)
    owners = [
        dict(item)
        for item in policy.get("owners", ())
        if isinstance(item, Mapping)
    ]
    owners.append(
        {
            "path": str(generated_root),
            "kind": "generated",
            "id": "vibeflow.aot.generated",
        }
    )
    allowed = {
        str(item)
        for item in policy.get("allowed_external_packages", ())
    }
    allowed.update(str(item) for item in external_packages)
    return {
        "owners": owners,
        "nodeBaseLibs": {
            str(key): [str(item) for item in value]
            for key, value in (
                policy.get("node_base_libs", policy.get("nodeBaseLibs", {}))
                or {}
            ).items()
        },
        "baseLibDependencies": {
            str(key): [str(item) for item in value]
            for key, value in (
                policy.get(
                    "base_lib_dependencies",
                    policy.get("baseLibDependencies", {}),
                )
                or {}
            ).items()
        },
        "hostExtensionDependencies": {
            str(key): [str(item) for item in value]
            for key, value in (
                policy.get(
                    "host_extension_dependencies",
                    policy.get("hostExtensionDependencies", {}),
                )
                or {}
            ).items()
        },
        "allowedExternalPackages": sorted(allowed),
    }


def validate_profile_output(
    staging: Path,
    *,
    profile: str,
    entry_name: str,
) -> None:
    entry = staging / entry_name
    if not entry.is_file():
        raise AotBuildError(
            "VF_BUILD_OUTPUT",
            f"build driver did not produce expected entry: {entry_name}",
        )
    if profile == "single-esm":
        runtime_js = [
            path
            for path in staging.rglob("*.js")
            if path.is_file() and path.name != entry_name
        ]
        if runtime_js:
            names = sorted(path.relative_to(staging).as_posix() for path in runtime_js)
            raise AotBuildError(
                "VF_BUILD_CHUNK",
                f"single-esm produced companion JavaScript chunks: {names}",
            )
        companions = [
            path
            for path in staging.rglob("*")
            if path.is_file()
            and path.suffix not in {".js", ".map", ".ts"}
        ]
        if companions:
            names = sorted(path.relative_to(staging).as_posix() for path in companions)
            raise AotBuildError(
                "VF_BUILD_CHUNK",
                f"single-esm produced non-inline companion assets: {names}",
            )


def build_manifest(
    workflow: WorkflowSpec,
    *,
    emitted: EmittedWorkflow,
    driver_result: DriverBuildResult,
    target: str,
    profile: str,
    entry_name: str,
    external_packages: tuple[str, ...],
    staging: Path,
) -> dict[str, Any]:
    files = {}
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        relative = path.relative_to(staging).as_posix()
        files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "format": BUILD_MANIFEST_FORMAT,
        "abi_version": workflow.abi_version,
        "workflow_id": workflow.workflow_id,
        "entry_mode": workflow.entry_mode,
        "target": target,
        "profile": profile,
        "entry": "index.html" if profile == "web-app" else entry_name,
        "plan_sha256": emitted.plan_sha256,
        "toolchain": driver_result.toolchain.to_dict(),
        "external_packages": sorted(set(external_packages)),
        "host_extensions": list(emitted.host_extensions),
        "files": files,
    }


def validate_existing_target(out_dir: Path, *, replace: bool) -> None:
    if not os.path.lexists(out_dir):
        return
    if not replace:
        raise AotBuildError(
            "VF_BUILD_EXISTS",
            f"output directory already exists: {out_dir}",
        )
    try:
        validate_owned_build_directory(
            out_dir,
            manifest_format=BUILD_MANIFEST_FORMAT,
        )
    except AotPublishError as exc:
        raise AotBuildError(exc.code, str(exc)) from exc


def publish(
    staging: Path,
    out_dir: Path,
    *,
    replace: bool,
    build_root: Path,
) -> None:
    del build_root
    try:
        atomic_publish_directory(
            staging,
            out_dir,
            replace=replace,
            manifest_format=BUILD_MANIFEST_FORMAT,
        )
    except AotPublishError as exc:
        raise AotBuildError(exc.code, str(exc)) from exc


__all__ = [
    "BUILD_MANIFEST_FORMAT",
    "SOURCEMAP_MODES",
    "WEB_APP_MARKER",
    "build_manifest",
    "driver_import_policy",
    "entry_name",
    "publish",
    "resolve_under_project",
    "resolved_implementations",
    "validate_existing_target",
    "validate_modes",
    "validate_profile_output",
    "web_inputs",
    "write_profile_companions",
]
