from __future__ import annotations

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
    project_config["quality_enabled"] = True
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
        project / "manifests/base_lib/unused.jsonc",
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
        project / "manifests/nodes/unused.jsonc",
        {
            "kind": "node",
            "type_key": "example.unused",
            "display_name": "Unused node",
            "category": "example",
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
    complete = audit_javascript_project(
        JavascriptAuditRequest(
            **request,
            audit_registered_resources=True,
        )
    )

    assert str(project / "nodes/greet.ts") in selected.source_files
    assert str(project / "base_lib/text.ts") in selected.source_files
    assert str(project / "nodes/unused.ts") not in selected.source_files
    assert str(project / "base_lib/unused.ts") not in selected.source_files
    assert str(project / "nodes/unused.ts") in complete.source_files
    assert str(project / "base_lib/unused.ts") in complete.source_files


def test_homogeneous_javascript_quality_respects_disabled_root(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    project = tmp_path / "project"
    config = project / "configs/main.jsonc"
    config.parent.mkdir(parents=True)
    _write_json(
        project / "vibeflow_project.jsonc",
        {
            "project_target": "javascript",
            "quality_enabled": False,
            "descriptors": {},
            "javascript": {"package_root": "."},
        },
    )
    _write_json(config, {"pipeline": {"nodes": []}})
    workspace = tmp_path / "vibeflow_config.jsonc"
    _write_json(workspace, {"roots": [{"id": "js", "path": "project"}]})

    exit_code = dispatch_main(
        [
            "quality-check",
            "--workspace",
            str(workspace),
            "--config",
            str(config),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["project_target"] == "javascript"
    assert payload["reports"] == []
    assert payload["skipped"] == "quality_enabled=false"
    assert payload["result_code"] == "VIBEFLOW_QUALITY_PASS"
    assert payload["checked"] == []


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


def test_standalone_quality_uses_explicit_javascript_target(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    project = tmp_path / "standalone"
    project.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(toolchain / name, project / name)
    (project / "node_modules").symlink_to(
        toolchain / "node_modules",
        target_is_directory=True,
    )
    (project / "source.ts").write_text(
        "const projectTypeError: string = 42;\n"
        "export function inspect() {\n"
        "  void (globalThis as any).process;\n"
        "  return projectTypeError;\n"
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "quality-check",
            "--path",
            str(project),
            "--project-target",
            "javascript",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["project_target"] == "javascript"
    assert payload["source_files"] == [str(project / "source.ts")]


def test_standalone_quality_reports_unowned_long_lived_work(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    project = tmp_path / "standalone"
    project.mkdir()
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(toolchain / name, project / name)
    (project / "node_modules").symlink_to(
        toolchain / "node_modules",
        target_is_directory=True,
    )
    (project / "source.ts").write_text(
        "export function install() {\n"
        "  addEventListener('message', () => {});\n"
        "}\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "quality-check",
            "--path",
            str(project),
            "--project-target",
            "javascript",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = payload["reports"][0]["diagnostics"]
    assert exit_code == 1
    assert payload["status"] == "FAIL"
    assert "VF_SOURCE_LISTENER_UNOWNED" in {
        item["code"] for item in diagnostics
    }


def test_project_quality_detects_browser_only_discarded_fetch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    sandbox = _copy_minimal(tmp_path, toolchain=toolchain)
    project = sandbox / "project"
    manifest_path = project / "manifests/nodes/greet.jsonc"
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
            "--config",
            str(project / "configs/greeting.jsonc"),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    diagnostics = payload["reports"][0]["diagnostics"]
    assert exit_code == 1
    assert payload["status"] == "FAIL"
    assert "VF_PROMISE_UNOWNED" in {
        item["code"] for item in diagnostics
    }


def test_project_quality_audits_unselected_implemented_plugin_and_host(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    sandbox = _copy_minimal(tmp_path, toolchain=toolchain)
    project = sandbox / "project"
    project_config_path = project / "vibeflow_project.jsonc"
    project_config = json.loads(
        project_config_path.read_text(encoding="utf-8")
    )
    project_config["descriptors"]["plugins"] = ["manifests/plugins"]
    project_config["descriptors"]["host_extensions"] = [
        "manifests/host_extensions"
    ]
    _write_json(project_config_path, project_config)
    _write_json(
        project / "manifests/plugins/unselected.jsonc",
        {
            "kind": "plugin",
            "id": "example.unselected_plugin",
            "type": "runtime",
            "targets": ["browser"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser"],
                    "source": {
                        "kind": "file",
                        "ref": "plugins/unselected.ts",
                        "export": "createPlugin",
                    },
                }
            ],
            "dependencies": [],
            "external_packages": [],
            "config": {"schema": {}, "defaults": {}},
        },
    )
    (project / "plugins").mkdir()
    (project / "plugins/unselected.ts").write_text(
        "export function createPlugin() {\n"
        "  return { beforeRun() { addEventListener('message', () => {}); } };\n"
        "}\n",
        encoding="utf-8",
    )
    _write_json(
        project / "manifests/host_extensions/unselected.jsonc",
        {
            "kind": "host_extension",
            "id": "example.unselected_host",
            "targets": ["browser"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser"],
                    "source": {
                        "kind": "file",
                        "ref": "host/unselected.ts",
                        "export": "createHostExtension",
                    },
                }
            ],
            "provides": [],
            "dependencies": [],
            "external_packages": [],
        },
    )
    (project / "host").mkdir()
    (project / "host/unselected.ts").write_text(
        "import { run } from '../nodes/greet.ts';\n"
        "export function createHostExtension() {\n"
        "  void run;\n"
        "  return { start() {}, stop() {} };\n"
        "}\n",
        encoding="utf-8",
    )
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
            "--config",
            str(config),
            "--json",
        ]
    )
    quality_payload = json.loads(capsys.readouterr().out)
    diagnostics = quality_payload["reports"][0]["diagnostics"]
    codes = {item["code"] for item in diagnostics}
    owners = {
        item.get("owner", {}).get("id")
        for item in diagnostics
    }
    assert quality_exit == 1
    assert quality_payload["status"] == "FAIL"
    assert "VF_PLUGIN_LONG_LIVED_LISTENER" in codes
    assert "VF_IMPORT_LAYER" in codes
    assert {
        "example.unselected_plugin",
        "example.unselected_host",
    } <= owners


def test_dispatched_quality_path_uses_project_config_without_workspace(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    toolchain = _toolchain_root()
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("the JavaScript sandbox toolchain has not been installed")
    sandbox = _copy_minimal(tmp_path, toolchain=toolchain)
    project = sandbox / "project"
    (sandbox / "vibeflow_config.jsonc").unlink()

    exit_code = dispatch_main(
        [
            "quality-check",
            "--path",
            str(project),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["project_target"] == "javascript"
    assert payload["reports"]
    assert not (project / "vibeflow_config.jsonc").exists()
