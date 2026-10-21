from __future__ import annotations

from tests.fixtures.support.plugins import Resource, resource as sdk_resource

import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.targets.javascript.build import toolchain as javascript_toolchain
from vibeflow.tooling.application.javascript.cli import main
from vibeflow.tooling.application.cli import main as dispatch_main


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SANDBOX = REPOSITORY_ROOT / "sandbox/javascript/minimal"


def _toolchain_root() -> Path:
    configured = os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT")
    return (
        Path(configured).expanduser().resolve()
        if configured
        else SANDBOX / "project"
    )


def _copy_minimal(
    tmp_path: Path,
    *,
    toolchain: Path,
) -> Path:
    sandbox = tmp_path / "minimal"
    shutil.copytree(
        SANDBOX,
        sandbox,
        ignore=shutil.ignore_patterns(
            "node_modules",
            "__pycache__",
            "*.pyc",
        ),
    )
    project_config_path = sandbox / "project/vibeflow_project.jsonc"
    project_config = json.loads(
        project_config_path.read_text(encoding="utf-8")
    )

    project_config_path.write_text(
        json.dumps(project_config, indent=2) + "\n",
        encoding="utf-8",
    )
    (sandbox / "project/node_modules").symlink_to(
        toolchain / "node_modules",
        target_is_directory=True,
    )
    return sandbox


def _write_json(path: Path, payload: object) -> None:
    if not isinstance(path, Resource):
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_neutral_audit_driver_does_not_require_build_lock_or_esbuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_root = tmp_path / "package"
    package_root.mkdir()
    _write_json(package_root / "package.json", {"private": True})
    captured: list[dict[str, object]] = []

    def fake_run_driver(request, *, node_command):
        captured.append(dict(request))
        assert node_command == "node"
        return {
            "ok": True,
            "probe": {"node": "22.12.0", "typescript": "7.0.0"},
            "audit": {"checked": True},
        }

    monkeypatch.setattr(javascript_toolchain, "_run_driver", fake_run_driver)

    result = javascript_toolchain.run_audit_driver(
        {"typecheckFiles": []},
        package_root=package_root,
    )

    assert result.toolchain.to_dict() == {
        "node": "22.12.0",
        "typescript": "7.0.0",
    }
    assert captured[0]["command"] == "audit"
    assert not (package_root / "package-lock.json").exists()


def test_validate_audits_only_selected_node_and_base_lib_sources(
    tmp_path: Path,
) -> None:
    from vibeflow.tooling.application.javascript.audit import (
        JavascriptAuditRequest,
        audit_javascript_project,
    )

    sandbox = _copy_minimal(tmp_path, toolchain=_toolchain_root())
    project = sandbox / "project"
    _write_json(
        sdk_resource(project, "base_lib", "example.unused"),
        {
            "kind": "base_lib",
            "id": "example.unused",
            "display_name": "Unused helper",
            "description": "Only the project quality closure owns this source.",
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "base_lib/unused.ts",
                    },
                }
            ],
            "dependencies": [],
            "external_packages": [],
        },
    )
    _write_json(
        sdk_resource(project, "node", "example.unused"),
        {'node_type': 'vibeflow.node',
            "kind": "node",
            'id': "example.unused",
            "display_name": "Unused node",

            "description": "Not selected by greeting.jsonc.",
            "version": "1.0.0",
            "flow_kind": "process",
            "contract": {
                "requires": [],
                "provides": [],
                "params_schema": {},
                "params_defaults": {},
                "input_semantics": {},
                "output_semantics": {},
            },
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "completion": "immediate",
                    "source": {
                        "kind": "file",
                        "ref": "nodes/unused.ts",
                        "export": "run",
                    },
                }
            ],
            "base_libs": ["example.unused"],
            "capabilities": [],
        },
    )
    (project / "base_lib/unused.ts").write_text(
        "export const unused = true;\n",
        encoding="utf-8",
    )
    (project / "nodes/unused.ts").write_text(
        "export function run() { return {}; }\n",
        encoding="utf-8",
    )
    request = {
        "workspace": sandbox / "vibeflow_config.jsonc",
        "config": project / "configs/greeting.jsonc",
        "audit_sources": False,
    }
    selected = audit_javascript_project(JavascriptAuditRequest(**request))

    assert str(project / "nodes/greet.ts") in selected.source_files
    assert str(project / "base_lib/text.ts") in selected.source_files
    assert str(project / "nodes/unused.ts") not in selected.source_files
    assert str(project / "base_lib/unused.ts") not in selected.source_files
    from vibeflow.tooling.project.preparation import ProjectPreparation
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    workspace=load_workspace_config(sandbox / "vibeflow_config.jsonc")
    files = ProjectPreparation(workspace).source_facts(workspace.roots[0]).files
    assert {"nodes/unused.ts","base_lib/unused.ts"} <= {item.path for item in files}




def test_minimal_javascript_validate_needs_no_platform_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    sandbox = _copy_minimal(tmp_path, toolchain=toolchain)

    exit_code = main(
        [
            "validate",
            "--workspace",
            str(sandbox / "vibeflow_config.jsonc"),
            "--config",
            str(sandbox / "project/configs/greeting.jsonc"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["project_target"] == "javascript"
    assert payload["workflow_id"] == "greeting"






def test_project_quality_detects_browser_only_discarded_fetch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    from tests.targets.javascript.test_quality_sandbox import _project_case
    workspace, project, config = _project_case(tmp_path)
    sandbox = workspace.parent
    manifest_path = sdk_resource(project, 'node', 'example.greet')
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["implementations"][0]["targets"] = ["browser"]
    _write_json(manifest_path, manifest)
    (project / "nodes/greet.ts").write_text(
        "export async function run(): Promise<{ readonly greeting: string }> {\n"
        "  void fetch('https://example.invalid/audit');\n"
        "  return { greeting: 'ignored' };\n"
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "quality-check",
            "--workspace",
            str(sandbox / "vibeflow_config.jsonc"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = payload["reports"][0]["diagnostics"]
    assert exit_code == 1
    assert payload["status"] == "FAIL"
    assert "VF_PROMISE_UNOWNED" in {
        item.get("rule_id", item.get("code")) for item in diagnostics
    }


def test_project_quality_does_not_register_unselected_plugin_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    sandbox = _copy_minimal(tmp_path, toolchain=toolchain)
    project = sandbox / "project"
    package = project / "plugins/unselected"
    package.mkdir()
    (package / "plugin.ts").write_text('import {definePlugin,defineNodeType} from "@vibeflow/plugin";\n'
        'throw new Error("UNSELECTED_PLUGIN_WAS_LOADED");\n'
        'export const plugin=definePlugin({id:"example.unselected",resources:[defineNodeType({id:"unused.shell"})]});\n')
    config = project / "configs/greeting.jsonc"

    validate_exit = main(
        [
            "validate",
            "--workspace",
            str(sandbox / "vibeflow_config.jsonc"),
            "--config",
            str(config),
            "--json",
        ]
    )
    validate_payload = json.loads(capsys.readouterr().out)
    assert validate_exit == 0
    assert validate_payload["status"] == "PASS"

    quality_exit = main(
        [
            "quality-check",
            "--workspace",
            str(sandbox / "vibeflow_config.jsonc"),
            "--json",
        ]
    )
    quality_payload = json.loads(capsys.readouterr().out)
    # Files remain in project source metrics, but an unselected plugin is not a
    # contributed resource. There is no project-wide resource registration.
    assert quality_exit == 0
    assert quality_payload["status"] in {"PASS", "CONCERNS"}
    report = quality_payload["reports"][0]
    assert "example.greet" in report["rule_checks"]["subjects"]
    assert "plugin:example.unselected" not in report["rule_checks"]["subjects"]
    assert not any("plugins/unselected.ts" in file for file in report["source_files"])
    assert all("UNSELECTED_PLUGIN_WAS_LOADED" not in str(item) for item in quality_payload["reports"])




# Publish controlled case inputs as fixed SDK plugins before formal entrypoints.
from vibeflow.tooling.application.javascript.audit import audit_javascript_project
