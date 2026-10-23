from __future__ import annotations

import json

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from vibeflow.block_compiler.model import WorkflowPlan
from vibeflow.targets.javascript.frontend.build_contracts import (
    node_contract_check as _node_contract_check,
    runtime_plugin_contract_check as _runtime_plugin_contract_check,
    validate_schema_subset as _validate_schema_subset,
)
from vibeflow.targets.javascript.build.build_support import (
    BUILD_MANIFEST_FORMAT,
    WEB_APP_MARKER,
    build_manifest as _manifest,
    driver_import_policy as _driver_import_policy,
    entry_name as _entry_name,
    resolve_under_project as _resolve_under_project,
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
from vibeflow.targets.javascript.frontend.errors import AotPlanError

from vibeflow.targets.javascript.build.toolchain import (
    AotToolchainError,
    run_build_driver,
)


@dataclass(frozen=True)
class BuildRequest:
    plan: WorkflowPlan
    javascript_bindings: JavascriptBindingPlan
    project_root: str | Path
    package_root: str | Path
    out_dir: str | Path
    target: str
    profile: str
    external_packages: tuple[str, ...] = ()
    entry_name: str = ""
    sourcemap: str = "external"
    replace: bool = False
    html_template: str | Path | None = None
    app_entry: str | Path | None = None
    node_command: str = "node"
    plugin_manifest: Mapping[str, Any] = field(default_factory=dict)
    resource_use: Mapping[str, Any] | None = None
    audit_sources: tuple[str, ...] = ()
    workflow_launches: tuple = ()
    workflow_reference: Mapping | None = None


from vibeflow.targets.shared.aot import BuildResult, staged_build, write_manifest
from vibeflow.targets.shared.aot_publish import AotPublishError


def build_aot(request: BuildRequest) -> BuildResult:
    try:
        workflow = bound_workflow_view(request.plan, request.javascript_bindings)
    except (AotPlanError, TypeError) as exc:
        raise AotBuildError(getattr(exc, "code", "VF_PLAN"), str(exc)) from exc
    import_policy = request.javascript_bindings.import_policy.to_value()
    _validate_schema_subset(workflow)
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
    out_dir = Path(request.out_dir).expanduser().absolute()
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
    emitted = emit_workflow_module(
        request.plan, javascript_bindings=request.javascript_bindings,
        workflow_reference=request.workflow_reference, workflow_launches=request.workflow_launches,
    )
    entry_name = _entry_name(profile, request.entry_name)
    html_template, app_entry = _web_inputs(
        request,
        project_root=project_root,
        target=target,
        profile=profile,
    )
    try:
        with staged_build(out_dir, replace=request.replace) as staging:
            source_dir = staging.parent / "source"
            source_dir.mkdir()
            workflow_entry = source_dir / "workflow-entry.mjs"
            from vibeflow.targets.javascript.resources import read_text
            runtime_source = (read_text("node_observation.mjs") + "\n" if target == "node" else "") + emitted.source
            workflow_entry.write_text(runtime_source, encoding="utf-8")
            contract_check = source_dir / "node-contract-check.ts"
            contract_check.write_text(
                _node_contract_check(workflow),
                encoding="utf-8",
            )
            plugin_contract_check: Path | None = None
            if request.javascript_bindings.runtime_plugins:
                plugin_contract_check = source_dir / "runtime-plugin-contract-check.ts"
                plugin_contract_check.write_text(
                    _runtime_plugin_contract_check(request.javascript_bindings),
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
            driver_request: dict[str, Any] = {
                "target": target,
                "profile": profile,
                "workflowEntry": str(workflow_entry),
                "outDir": str(staging),
                "entryName": entry_name,
                "sourcemap": sourcemap,
                "external": sorted(set(request.external_packages)),
                "runtimeBindings": [{"module": module, "export": exported} for module, exported in emitted.implementation_bindings]
                    + [{"module": item.implementation.ref, "export": item.implementation.export} for item in request.javascript_bindings.runtime_plugins],
                "typecheckFiles": [
                    str(contract_check),
                    *(
                        [str(plugin_contract_check)]
                        if plugin_contract_check is not None
                        else []
                    ),
                    *(str(item) for item in request.audit_sources),
                ],
                "contractCheckFiles": [
                    str(contract_check),
                    *(
                        [str(plugin_contract_check)]
                        if plugin_contract_check is not None
                        else []
                    ),
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
            if request.resource_use is not None:
                (staging / "resource-use.json").write_text(json.dumps(dict(request.resource_use)), encoding="utf-8")
            from vibeflow.core.workflows.references import launch_document
            (staging / "workflow-launches.json").write_text(
                json.dumps(launch_document(request.workflow_launches, workflow=request.workflow_reference), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
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
            write_manifest(staging, manifest_payload)
    except AotBuildError:
        raise
    except AotPublishError as exc:
        raise AotBuildError(exc.code, str(exc)) from exc
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
