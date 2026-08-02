"""Gates for direct WorkflowPlan + JavaScript binding emission."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Mapping

import pytest

from tests.targets.javascript.strict_aot_project_build import _request, _write
from tests.targets.javascript.test_aot_core import _fake_driver
from vibeflow.targets.javascript.build import BuildRequest, build_aot
from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
from vibeflow.tooling.application.javascript_build import (
    ProjectBuildRequest,
    prepare_project_build,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TYPESCRIPT_SANDBOX = REPOSITORY_ROOT / "sandbox/javascript/integration"
TYPESCRIPT_PROJECT = TYPESCRIPT_SANDBOX / "project"
TYPESCRIPT_WORKSPACE = TYPESCRIPT_SANDBOX / "vibeflow_config.jsonc"
TYPESCRIPT_HOST_WORKSPACE = (
    TYPESCRIPT_SANDBOX / "vibeflow_host_config.jsonc"
)

EMITTED_FIELDS = (
    "source",
    "declarations",
    "plan_sha256",
    "implementation_modules",
    "implementation_bindings",
    "host_extensions",
)


def _emitted_bytes(emitted: object) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    for name in EMITTED_FIELDS:
        value = getattr(emitted, name)
        if isinstance(value, str):
            result[name] = value.encode("utf-8")
        else:
            result[name] = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
    return result


def _bound_emission(prepared: object) -> object:
    bindings = getattr(prepared, "javascript_bindings")
    assert bindings is not None
    return emit_workflow_module(
        getattr(prepared, "plan"),
        javascript_bindings=bindings,
    )


@pytest.mark.parametrize(
    "config_name",
    (
        "linear.jsonc",
        "nodeset.jsonc",
        "loop.jsonc",
        "async_capability.jsonc",
        "detached.jsonc",
        "host_extension.jsonc",
        "permanent_port_host.jsonc",
    ),
)
def test_real_projects_emit_deterministic_bound_modules(
    tmp_path: Path,
    config_name: str,
) -> None:
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=(
                TYPESCRIPT_HOST_WORKSPACE
                if config_name
                in {"host_extension.jsonc", "permanent_port_host.jsonc"}
                else TYPESCRIPT_WORKSPACE
            ),
            config=TYPESCRIPT_PROJECT / "configs" / config_name,
            out_dir=tmp_path / config_name,
            target="node",
            profile="single-esm",
        )
    )

    first = _bound_emission(prepared)
    second = _bound_emission(prepared)

    assert _emitted_bytes(first) == _emitted_bytes(second)
    assert tuple(_emitted_bytes(first)) == EMITTED_FIELDS


def test_bound_emission_preserves_unsorted_nested_schema_member_order(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)
    schema_path = (
        Path(request.config).parent
        / "manifests/data/value.out.jsonc"
    )
    descriptor = json.loads(schema_path.read_text(encoding="utf-8"))
    descriptor["schema"] = {
        "type": "object",
        "properties": {
            "z": {
                "type": "object",
                "properties": {
                    "z": {"type": "string"},
                    "a": {"type": "number"},
                },
                "required": ["z", "a"],
            },
            "a": {"type": "boolean"},
        },
        "required": ["z", "a"],
    }
    _write(schema_path, descriptor)
    prepared = prepare_project_build(request)

    canonical = _bound_emission(prepared)

    ordered_declaration = (
        'readonly "answer": { readonly "z": { readonly "z": string; '
        'readonly "a": number; readonly [key: string]: unknown }; '
        'readonly "a": boolean; readonly [key: string]: unknown };'
    )
    assert ordered_declaration in canonical.declarations


def _project_build_request(
    prepared: object,
    *,
    out_dir: Path,
    profile: str,
    html_template: Path | None = None,
    app_entry: Path | None = None,
) -> BuildRequest:
    return BuildRequest(
        plan=getattr(prepared, "plan"),
        project_root=getattr(prepared, "root").path,
        package_root=getattr(prepared, "package_root"),
        out_dir=out_dir,
        target="browser" if profile == "web-app" else "node",
        profile=profile,
        implementation_by_type=getattr(
            prepared,
            "implementation_by_type",
        ),
        external_packages=getattr(prepared, "external_packages"),
        import_policy=getattr(prepared, "import_policy"),
        host_extensions=getattr(prepared, "host_extensions"),
        html_template=html_template,
        app_entry=app_entry,
        javascript_bindings=getattr(prepared, "javascript_bindings"),
    )


def _file_hashes(out_dir: Path, files: tuple[str, ...]) -> Mapping[str, str]:
    return {
        relative: sha256((out_dir / relative).read_bytes()).hexdigest()
        for relative in files
    }


@pytest.mark.parametrize(
    "profile",
    ("esm-module", "single-esm", "web-app"),
)
def test_all_profiles_build_deterministically_from_binding_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    import vibeflow.targets.javascript.build.builder as builder_module

    project_request = _request(
        tmp_path / "fixture",
        target="browser" if profile == "web-app" else "node",
        profile=profile,
    )
    prepared = prepare_project_build(project_request)
    project = prepared.root.path
    html_template = project / "index.template.html"
    app_entry = project / "src/app.ts"
    html_template.write_text(
        "<!doctype html><body><!-- VIBEFLOW_APP_ENTRY --></body>\n",
        encoding="utf-8",
    )
    app_entry.write_text(
        'import { runWorkflow } from "@vibeflow/workflow";\n'
        "void runWorkflow;\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(builder_module, "run_build_driver", _fake_driver)
    first_out = tmp_path / f"first-{profile}"
    second_out = tmp_path / f"second-{profile}"

    first = build_aot(
        _project_build_request(
            prepared,
            out_dir=first_out,
            profile=profile,
            html_template=html_template if profile == "web-app" else None,
            app_entry=app_entry if profile == "web-app" else None,
        )
    )
    second = build_aot(
        _project_build_request(
            prepared,
            out_dir=second_out,
            profile=profile,
            html_template=html_template if profile == "web-app" else None,
            app_entry=app_entry if profile == "web-app" else None,
        )
    )

    assert second.files == first.files
    assert _file_hashes(second_out, second.files) == _file_hashes(
        first_out,
        first.files,
    )
    assert second.manifest.read_bytes() == first.manifest.read_bytes()
