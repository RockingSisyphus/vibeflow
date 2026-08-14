from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from vibeflow.tooling.application.javascript.build import ProjectBuildError
from vibeflow.tooling.application.javascript.cli import build_parser, main


def test_build_parser_exposes_the_three_aot_profiles() -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "build",
            "--workspace",
            "vibeflow_config.jsonc",
            "--config",
            "project/configs/main.jsonc",
            "--target",
            "browser",
            "--profile",
            "single-esm",
            "--out-dir",
            "dist",
        ]
    )

    assert args.command == "build"
    assert args.profile == "single-esm"
    assert args.sourcemap == "external"
    assert not args.replace


def test_build_cli_prints_one_machine_readable_success_object(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / "dist"
    toolchain = SimpleNamespace(
        to_dict=lambda: {
            "node": "22.12.0",
            "typescript": "7.0.0",
            "esbuild": "0.28.0",
            "lock_sha256": "abc",
            "lock_files": ["package-lock.json"],
        }
    )
    result = SimpleNamespace(
        prepared=SimpleNamespace(plan=SimpleNamespace(workflow_id="demo.workflow")),
        out_dir=out_dir,
        entry=out_dir / "workflow.js",
        manifest=out_dir / "vibeflow-build.json",
        files=("workflow.js", "workflow.d.ts", "vibeflow-build.json"),
        build=SimpleNamespace(toolchain=toolchain),
    )

    monkeypatch.setattr(
        "vibeflow.tooling.application.javascript.build.build_project_aot",
        lambda request: result,
    )

    status = main(
        [
            "build",
            "--workspace",
            str(tmp_path / "vibeflow_config.jsonc"),
            "--config",
            str(tmp_path / "project/configs/main.jsonc"),
            "--target",
            "node",
            "--profile",
            "esm-module",
            "--out-dir",
            str(out_dir),
        ]
    )

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["workflow_id"] == "demo.workflow"
    assert payload["entry"] == str(out_dir / "workflow.js")


def test_build_cli_preserves_stable_error_codes(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    def fail(_request):
        raise ProjectBuildError(
            "VF_AOT_INPUT_REQUIRED",
            "JS AOT inputs must declare required",
        )

    monkeypatch.setattr("vibeflow.tooling.application.javascript.build.build_project_aot", fail)

    status = main(
        [
            "build",
            "--workspace",
            str(tmp_path / "vibeflow_config.jsonc"),
            "--config",
            str(tmp_path / "project/configs/main.jsonc"),
            "--target",
            "browser",
            "--profile",
            "single-esm",
            "--out-dir",
            str(tmp_path / "dist"),
        ]
    )

    assert status == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert payload["code"] == "VF_AOT_INPUT_REQUIRED"
    assert payload["error"] == "JS AOT inputs must declare required"
    assert payload["result_code"] == "VIBEFLOW_BUILD_ERROR"
    assert payload["checked"] == []
