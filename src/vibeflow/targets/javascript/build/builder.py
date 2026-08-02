from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Mapping

from vibeflow.block_compiler.model import WorkflowPlan
from vibeflow.targets.javascript.frontend.build_contracts import (
    node_contract_check as _node_contract_check,
    validate_schema_subset as _validate_schema_subset,
)
from vibeflow.targets.javascript.build.build_support import (
    BUILD_MANIFEST_FORMAT,
    WEB_APP_MARKER,
    build_manifest as _manifest,
    driver_import_policy as _driver_import_policy,
    entry_name as _entry_name,
    publish as _publish,
    resolve_under_project as _resolve_under_project,
    resolved_implementations as _resolved_implementations,
    validate_existing_target as _validate_existing_target,
    validate_modes as _validate_modes,
    validate_profile_output as _validate_profile_output,
    web_inputs as _web_inputs,
    write_profile_companions as _write_profile_companions,
)
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.targets.javascript.frontend.bindings import JavascriptBindingPlan
from vibeflow.targets.javascript.frontend.emission_view import bound_workflow_view
from vibeflow.targets.javascript.frontend.errors import AotBuildError
from vibeflow.targets.javascript.frontend.model import (
    AotPlanError,
    WorkflowSpec,
    normalize_workflow_plan,
)
from vibeflow.targets.javascript.build.toolchain import (
    AotToolchainError,
    ToolchainInfo,
    run_build_driver,
)


@dataclass(frozen=True)
class BuildRequest:
    plan: WorkflowSpec | object
    project_root: str | Path
    package_root: str | Path
    out_dir: str | Path
    target: str
    profile: str
    implementation_by_type: Mapping[str, object] = field(default_factory=dict)
    external_packages: tuple[str, ...] = ()
    import_policy: Mapping[str, Any] = field(default_factory=dict)
    host_extensions: tuple[Mapping[str, Any], ...] = ()
    entry_name: str = ""
    sourcemap: str = "external"
    replace: bool = False
    html_template: str | Path | None = None
    app_entry: str | Path | None = None
    node_command: str = "node"
    javascript_bindings: JavascriptBindingPlan | None = None
    plugin_manifest: Mapping[str, Any] = field(default_factory=dict)
    audit_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class BuildResult:
    out_dir: Path
    entry: Path
    manifest: Path
    toolchain: ToolchainInfo
    files: tuple[str, ...]


def build_aot(request: BuildRequest) -> BuildResult:
    canonical = request.javascript_bindings is not None
    if canonical:
        if not isinstance(request.plan, WorkflowPlan):
            raise AotBuildError(
                "VF_PLAN",
                "canonical JavaScript build requires a WorkflowPlan",
            )
        try:
            workflow = bound_workflow_view(
                request.plan,
                request.javascript_bindings,
            )
        except AotPlanError as exc:
            raise AotBuildError(exc.code, str(exc)) from exc
        implementation_facts: Mapping[str, object] = {}
        import_policy = request.javascript_bindings.import_policy.to_value()
    else:
        try:
            workflow = normalize_workflow_plan(request.plan)
        except AotPlanError as exc:
            raise AotBuildError(exc.code, str(exc)) from exc
        implementation_facts = request.implementation_by_type
        import_policy = request.import_policy
    _validate_schema_subset(
        workflow,
        implementation_by_type=implementation_facts,
    )
    target, profile, sourcemap = _validate_modes(request)
    project_root = Path(request.project_root).expanduser().resolve()
    if not project_root.is_dir():
        raise AotBuildError(
            "VF_BUILD_PATH",
            f"project_root does not exist: {project_root}",
        )
    package_root = _resolve_under_project(
        request.package_root,
        project_root=project_root,
        subject="package_root",
        require_file=False,
    )
    out_dir = Path(request.out_dir).expanduser().resolve()
    if (
        out_dir == project_root
        or project_root in out_dir.parents
        and out_dir.name in {"", ".", ".."}
    ):
        raise AotBuildError(
            "VF_BUILD_PATH",
            "out_dir must name a dedicated build directory",
        )
    _validate_existing_target(out_dir, replace=request.replace)
    implementations = (
        {}
        if canonical
        else _resolved_implementations(
            workflow,
            project_root=project_root,
            overrides=request.implementation_by_type,
        )
    )
    emitted = (
        emit_workflow_module(
            request.plan,
            javascript_bindings=request.javascript_bindings,
        )
        if canonical
        else emit_workflow_module(
            workflow,
            implementation_by_type=implementations,
            host_extensions=request.host_extensions,
        )
    )
    entry_name = _entry_name(profile, request.entry_name)
    html_template, app_entry = _web_inputs(
        request,
        project_root=project_root,
        target=target,
        profile=profile,
    )
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    build_root = Path(
        tempfile.mkdtemp(
            prefix=f".{out_dir.name}.vibeflow-aot-",
            dir=out_dir.parent,
        )
    )
    source_dir = build_root / "source"
    staging = build_root / "dist"
    source_dir.mkdir()
    staging.mkdir()
    workflow_entry = source_dir / "workflow-entry.mjs"
    workflow_entry.write_text(emitted.source, encoding="utf-8")
    contract_check = source_dir / "node-contract-check.ts"
    contract_check.write_text(
        _node_contract_check(workflow, implementations),
        encoding="utf-8",
    )
    ambient_module: Path | None = None
    if profile == "web-app":
        ambient_module = source_dir / "vibeflow-workflow.d.ts"
        ambient_module.write_text(
            'declare module "@vibeflow/workflow" {\n'
            + "\n".join(f"  {line}" for line in emitted.declarations.splitlines())
            + "\n}\n",
            encoding="utf-8",
        )
    try:
        driver_request: dict[str, Any] = {
            "target": target,
            "profile": profile,
            "workflowEntry": str(workflow_entry),
            "outDir": str(staging),
            "entryName": entry_name,
            "sourcemap": sourcemap,
            "external": sorted(set(request.external_packages)),
            "typecheckFiles": [
                str(contract_check),
                *(str(item) for item in request.audit_sources),
            ],
            "importPolicy": _driver_import_policy(
                import_policy,
                external_packages=request.external_packages,
                generated_root=source_dir,
            ),
        }
        if app_entry is not None:
            driver_request["appEntry"] = str(app_entry)
            driver_request["typecheckFiles"].append(str(app_entry))
        if ambient_module is not None:
            driver_request["typecheckFiles"].append(str(ambient_module))
        driver_result = run_build_driver(
            driver_request,
            package_root=package_root,
            node_command=request.node_command,
        )
        _write_profile_companions(
            staging,
            emitted=emitted,
            profile=profile,
            entry_name=entry_name,
            html_template=html_template,
        )
        _validate_profile_output(
            staging,
            profile=profile,
            entry_name=entry_name,
        )
        manifest_payload = _manifest(
            workflow,
            emitted=emitted,
            driver_result=driver_result,
            target=target,
            profile=profile,
            entry_name=entry_name,
            external_packages=request.external_packages,
            staging=staging,
            plugin_manifest=request.plugin_manifest,
        )
        manifest_path = staging / "vibeflow-build.json"
        manifest_path.write_text(
            json.dumps(
                manifest_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        _publish(
            staging,
            out_dir,
            replace=request.replace,
            build_root=build_root,
        )
    except AotBuildError:
        raise
    except AotToolchainError as exc:
        raise AotBuildError(
            exc.code,
            str(exc),
            diagnostics=exc.diagnostics,
        ) from exc
    except Exception as exc:
        raise AotBuildError(
            "VF_BUILD_FAILED",
            f"JavaScript AOT build failed: {exc}",
        ) from exc
    finally:
        if build_root.exists():
            shutil.rmtree(build_root)
    entry_path = out_dir / ("index.html" if profile == "web-app" else entry_name)
    files = tuple(
        path.relative_to(out_dir).as_posix()
        for path in sorted(item for item in out_dir.rglob("*") if item.is_file())
    )
    return BuildResult(
        out_dir=out_dir,
        entry=entry_path,
        manifest=out_dir / "vibeflow-build.json",
        toolchain=driver_result.toolchain,
        files=files,
    )


__all__ = [
    "BUILD_MANIFEST_FORMAT",
    "WEB_APP_MARKER",
    "AotBuildError",
    "BuildRequest",
    "BuildResult",
    "build_aot",
]
