from __future__ import annotations

import builtins
import json
from pathlib import Path
import subprocess
import sys

import pytest

from vibeflow.tooling.application.cli import main as cli_main
from vibeflow.tooling.project.config_loader import (
    ConfigLoadError,
    load_config_document,
    load_workspace_config_document,
)
from vibeflow.tooling.project.workspace_loader import load_workspace_config


def _project(
    tmp_path: Path,
    *,
    target: str,
) -> tuple[Path, Path]:
    root = tmp_path / "project"
    root.mkdir()
    project_config: dict[str, object] = {"project_target": target}
    if target == "javascript":
        project_config.update(
            {
                "javascript": {"package_root": "."},
            }
        )
    (root / "vibeflow_project.jsonc").write_text(
        json.dumps(project_config),
        encoding="utf-8",
    )
    config = root / "main.jsonc"
    config.write_text("{}", encoding="utf-8")
    workspace = tmp_path / "vibeflow_config.jsonc"
    workspace.write_text(
        json.dumps({"roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )
    return workspace, config


def test_run_rejects_javascript_root_without_importing_python_target(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    workspace, config = _project(tmp_path, target="javascript")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "vibeflow.targets.python" or name.startswith(
            "vibeflow.targets.python."
        ):
            raise AssertionError(f"unexpected Python Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    code = cli_main(
        ["run", "--workspace", str(workspace), "--config", str(config)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "CLI.PROJECT_TARGET.MISMATCH"
    assert payload["details"]["actual"] == "javascript"


def test_build_dispatches_python_root_without_importing_javascript_target(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    workspace, config = _project(tmp_path, target="python")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "vibeflow.targets.javascript" or name.startswith(
            "vibeflow.targets.javascript."
        ):
            raise AssertionError(f"unexpected JavaScript Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    def build(request):
        assert Path(request.workspace) == workspace
        from vibeflow.core.findings import HealthReport
        from vibeflow.tooling.application.python.build import PythonBuildResult
        return PythonBuildResult(out_dir=tmp_path/'bundle',entry=tmp_path/'bundle/run.py',
            manifest=tmp_path/'bundle/vibeflow-build.json',files=(),toolchain={},health=HealthReport(status="PASS"))
    from vibeflow.tooling.application.python import build as application_build
    monkeypatch.setattr(application_build,'build_python_aot',build)
    code = cli_main(["build","--workspace",str(workspace),"--config",str(config),"--out-dir",str(tmp_path/'bundle')])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload['status'] == 'PASS'
    assert payload['entry'].endswith('/bundle/run.py')


def test_shared_command_dispatches_javascript_root_without_python_import(
    tmp_path,
    monkeypatch,
) -> None:
    workspace, config = _project(tmp_path, target="javascript")
    captured: list[list[str]] = []

    def fake_javascript_main(args):
        captured.append(list(args))
        return 17

    monkeypatch.setattr(
        "vibeflow.tooling.application.javascript.cli.main",
        fake_javascript_main,
    )
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "vibeflow.targets.python" or name.startswith(
            "vibeflow.targets.python."
        ):
            raise AssertionError(f"unexpected Python Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    args = [
        "validate",
        "--workspace",
        str(workspace),
        "--config",
        str(config),
        "--json",
    ]

    assert cli_main(args) == 17
    assert captured == [args]


def test_python_application_services_reject_javascript_owned_workflow(
    tmp_path,
) -> None:
    from vibeflow.tooling.application.python.execution import CheckedRunError
    from vibeflow.tooling.application.python.workspace_service import (
        load_workspace_graph_for_export,
        run_workspace_checked,
        validate_workspace_config_path,
    )

    workspace_path, config = _project(tmp_path, target="javascript")
    workspace = load_workspace_config(workspace_path)

    validation = validate_workspace_config_path(config, workspace=workspace)
    graph, compiled, registry, resources, export_error = (
        load_workspace_graph_for_export(config, workspace=workspace)
    )

    assert validation.status == "ERROR"
    assert validation.errors[0].rule_id == "CLI.PROJECT_TARGET.MISMATCH"
    assert (graph, compiled, registry) == (None, None, None)
    assert resources.base_libs == ()
    assert resources.plugins == ()
    assert export_error is not None
    assert export_error.errors[0].rule_id == "CLI.PROJECT_TARGET.MISMATCH"
    with pytest.raises(CheckedRunError) as captured:
        run_workspace_checked(
            config,
            workspace=workspace,
            run_root=tmp_path / "runs",
            run_id="reject-javascript-target",
        )
    assert captured.value.result.health.errors[0].rule_id == (
        "CLI.PROJECT_TARGET.MISMATCH"
    )


def test_python_review_rejects_javascript_root_before_publishing(
    tmp_path,
    capsys,
) -> None:
    from vibeflow.tooling.application.python.cli import main as python_main

    workspace, config = _project(tmp_path, target="javascript")
    project_config_path = config.parent / "vibeflow_project.jsonc"
    project_config = json.loads(project_config_path.read_text(encoding="utf-8"))
    project_config["architecture"] = {
        "documents": [
            {"workflow": "main.jsonc", "document": "ARCHITECTURE.jsonc"}
        ]
    }
    project_config_path.write_text(
        json.dumps(project_config),
        encoding="utf-8",
    )
    architecture = config.parent / "ARCHITECTURE.jsonc"
    output = tmp_path / "review.svg"
    architecture.write_text("old architecture\n", encoding="utf-8")
    output.write_text("old review\n", encoding="utf-8")

    exit_code = python_main(
        [
            "review",
            "--workspace",
            str(workspace),
            "--config",
            str(config),
            "--output",
            str(output),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["failed_stage"] == "workspace"
    assert payload["error"]["rule_id"] == "CLI.PROJECT_TARGET.MISMATCH"
    assert architecture.read_text(encoding="utf-8") == "old architecture\n"
    assert output.read_text(encoding="utf-8") == "old review\n"


def test_quality_path_rejects_an_unregistered_directory(
    tmp_path,
    capsys,
) -> None:
    (tmp_path / "registered").mkdir()
    (tmp_path / "registered/vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (tmp_path / "vibeflow_config.jsonc").write_text(json.dumps({"roots":[{"id":"registered","path":"registered"}]}))
    directory = tmp_path / "unregistered"
    directory.mkdir()
    code = cli_main(["quality-check", "--path", str(directory), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "WORKSPACE.ROOT.UNREGISTERED"


def test_cli_reports_missing_project_target_before_loading_target(
    tmp_path,
    capsys,
) -> None:
    workspace, config = _project(tmp_path, target="python")
    project_config = config.parent / "vibeflow_project.jsonc"
    project_config.write_text("{}", encoding="utf-8")

    code = cli_main(
        ["validate", "--workspace", str(workspace), "--config", str(config)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "WORKSPACE.PROJECT_TARGET.MISSING"


def test_project_command_does_not_infer_target_when_no_project_config_exists(
    tmp_path,
    capsys,
) -> None:
    config = tmp_path / "workflow.jsonc"
    config.write_text("{}", encoding="utf-8")

    code = cli_main(["validate", "--config", str(config), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "WORKSPACE.PROJECT_TARGET.MISSING"
    assert payload["details"]["field"] == "project_target"


def test_validate_discovers_project_and_rejects_private_cross_target_nodeset_import(
    tmp_path,
    capsys,
) -> None:
    python_root = tmp_path / "python_project"
    javascript_root = tmp_path / "javascript_project"
    python_configs = python_root / "configs"
    javascript_configs = javascript_root / "configs"
    python_configs.mkdir(parents=True)
    javascript_configs.mkdir(parents=True)
    (tmp_path / "vibeflow_config.jsonc").write_text(json.dumps({"roots":[
        {"id":"python","path":"python_project"}, {"id":"javascript","path":"javascript_project"}]}))
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
            }
        ),
        encoding="utf-8",
    )
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    imported = javascript_configs / "foreign.jsonc"
    imported.write_text(
        json.dumps(
            {
                "type_key": "foreign.flow",
                "display_name": "Foreign flow",
                "description": "Belongs to the JavaScript Target.",
                "requires": [],
                "provides": [],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )
    workflow = python_configs / "main.jsonc"
    workflow.write_text(
        json.dumps(
            {
                "nodeset_imports": [
                    {
                        "path": "../../javascript_project/configs/foreign.jsonc",
                    }
                ],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )

    code = cli_main(["validate", "--config", str(workflow), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    # Loading records policy facts; malformed graphs still fail their schema.
    assert payload["errors"][0]["rule_id"] == "CONFIG.SCHEMA.NODES_NON_EMPTY"


def test_workspace_rejects_cross_target_nodeset_outside_declared_roots(
    tmp_path,
) -> None:
    workspace_dir = tmp_path / "workspace"
    javascript_root = workspace_dir / "javascript_project"
    python_root = tmp_path / "external" / "python_project"
    javascript_configs = javascript_root / "configs"
    python_configs = python_root / "configs"
    javascript_configs.mkdir(parents=True)
    python_configs.mkdir(parents=True)
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
            }
        ),
        encoding="utf-8",
    )
    imported = python_configs / "foreign.jsonc"
    imported.write_text(
        json.dumps(
            {
                "type_key": "foreign.flow",
                "display_name": "Foreign flow",
                "description": "Owned by an unregistered Python root.",
                "requires": [],
                "provides": [],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )
    workflow = javascript_configs / "main.jsonc"
    workflow.write_text(
        json.dumps(
            {
                "nodeset_imports": [
                    {
                        "path": str(imported),
                    }
                ],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )
    workspace_path = workspace_dir / "vibeflow_config.jsonc"
    workspace_path.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "javascript", "path": "javascript_project"}
                ]
            }
        ),
        encoding="utf-8",
    )
    workspace = load_workspace_config(workspace_path)

    document = load_workspace_config_document(workflow, workspace=workspace)
    assert document.nodeset_imports[0]["import_root"] == ""
    assert document.nodeset_imports[0]["source_target"] == "javascript"
    assert document.nodeset_imports[0]["import_target"] == "python"


def test_low_level_document_reader_can_parse_without_running_a_project(
    tmp_path,
) -> None:
    imported = tmp_path / "nodeset_types" / "shared.jsonc"
    imported.parent.mkdir()
    imported.write_text(
        json.dumps(
            {
                "type_key": "shared.flow",
                "display_name": "Shared flow",
                "description": "A low-level fixture without project metadata.",
                "requires": [],
                "provides": [],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )
    workflow = tmp_path / "main.jsonc"
    workflow.write_text(
        json.dumps(
            {
                "nodeset_imports": [{"path": "nodeset_types/shared.jsonc"}],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )

    document = load_config_document(workflow)

    assert document.data["nodeset_types"][0]["type_key"] == "shared.flow"


@pytest.mark.parametrize("command", ("run", "build", "inspect-node"))
def test_target_specific_commands_also_require_an_owning_project_root(
    tmp_path,
    capsys,
    command: str,
) -> None:
    config = tmp_path / "workflow.jsonc"
    module = tmp_path / "node.py"
    config.write_text("{}", encoding="utf-8")
    module.write_text("class Node: pass\n", encoding="utf-8")
    arguments = (
        ["inspect-node", "--node-id", "demo.node", "--module", str(module)]
        if command == "inspect-node"
        else [command, "--config", str(config)]
    )

    code = cli_main(arguments)
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "WORKSPACE.PROJECT_TARGET.MISSING"


def test_missing_workspace_is_rejected_by_neutral_loader_without_target_import(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("vibeflow.targets."):
            raise AssertionError(f"unexpected Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    code = cli_main(
        [
            "build",
            "--workspace",
            str(tmp_path / "missing.jsonc"),
            "--config",
            str(tmp_path / "workflow.jsonc"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "CONFIG.READ"


@pytest.mark.parametrize(
    "command",
    (
        "validate",
        "inspect-config",
        "export-mermaid",
        "export-architecture",
        "export-ascii",
        "export-svg",
        "review",
    ),
)
def test_shared_command_help_needs_no_project_or_target_import(
    command,
    monkeypatch,
    capsys,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("vibeflow.targets.") or name.startswith(
            "vibeflow.tooling.application.python"
        ) or name.startswith("vibeflow.tooling.application.javascript"):
            raise AssertionError(f"unexpected Target import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert cli_main([command, "--help"]) == 0
    output = capsys.readouterr()
    assert f"usage: vibeflow {command}" in output.out
    assert "--config" in output.out
    assert "PROJECT_TARGET.MISSING" not in output.out
    assert output.err == ""


def test_shared_javascript_svg_help_exposes_nodeset_diagnostics(capsys) -> None:
    assert cli_main(["export-svg", "--help"]) == 0

    output = capsys.readouterr()
    assert "--expand-nodesets" in output.out
    assert "--collapse-nodeset_types" in output.out
    assert "--hide-contract" in output.out
    assert "--hide-semantics" in output.out
    assert "--mermaid-layout" in output.out
    assert "--review-fragment-max-width" in output.out
