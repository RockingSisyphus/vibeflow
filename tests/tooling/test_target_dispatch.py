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
    if target == "python":
        project_config["registry"] = "registry.py:build_node_registry"
        (root / "registry.py").write_text(
            "def build_node_registry():\n    raise AssertionError('must not load')\n",
            encoding="utf-8",
        )
    else:
        project_config.update(
            {
                "descriptors": {},
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


def test_build_rejects_python_root_without_importing_javascript_target(
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
    code = cli_main(
        ["build", "--workspace", str(workspace), "--config", str(config)]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "CLI.PROJECT_TARGET.MISMATCH"
    assert payload["details"]["actual"] == "python"


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
    from vibeflow.tooling.application.python.runner import CheckedRunError
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
    assert resources.host_extensions == ()
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
    assert payload["failed_stage"] == "preflight"
    assert payload["error"]["rule_id"] == "CLI.PROJECT_TARGET.MISMATCH"
    assert architecture.read_text(encoding="utf-8") == "old architecture\n"
    assert output.read_text(encoding="utf-8") == "old review\n"


def test_quality_path_outside_project_requires_explicit_target(
    tmp_path,
    capsys,
) -> None:
    code = cli_main(["quality-check", "--path", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["code"] == "WORKSPACE.PROJECT_TARGET.MISSING"


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


def test_validate_without_workspace_rejects_cross_target_nodeset_import(
    tmp_path,
    capsys,
) -> None:
    python_root = tmp_path / "python_project"
    javascript_root = tmp_path / "javascript_project"
    python_configs = python_root / "configs"
    javascript_configs = javascript_root / "configs"
    python_configs.mkdir(parents=True)
    javascript_configs.mkdir(parents=True)
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
                "registry": "registry.py:build_node_registry",
            }
        ),
        encoding="utf-8",
    )
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "descriptors": {},
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
    assert payload["errors"][0]["rule_id"] == (
        "WORKSPACE.NODESET.TARGET_MISMATCH"
    )
    location = payload["errors"][0]["source_location"]
    assert location["source_target"] == "python"
    assert location["import_target"] == "javascript"


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
                "descriptors": {},
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
                "registry": "registry.py:build_node_registry",
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

    with pytest.raises(ConfigLoadError) as captured:
        load_workspace_config_document(workflow, workspace=workspace)

    assert captured.value.rule_id == "WORKSPACE.NODESET.TARGET_MISMATCH"
    assert captured.value.source_location["source_target"] == "javascript"
    assert captured.value.source_location["import_target"] == "python"


def test_low_level_nodeset_loader_without_project_configs_remains_compatible(
    tmp_path,
) -> None:
    imported = tmp_path / "nodesets" / "shared.jsonc"
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
                "nodeset_imports": [{"path": "nodesets/shared.jsonc"}],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )

    document = load_config_document(workflow)

    assert document.data["nodesets"][0]["type_key"] == "shared.flow"


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
        ["inspect-node", "--type", "demo.node", "--module", str(module)]
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


def test_mixed_workspace_quality_runs_each_root_in_an_isolated_process(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    python_root = tmp_path / "python_project"
    javascript_root = tmp_path / "javascript_project"
    python_root.mkdir()
    javascript_root.mkdir()
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
                "registry": "registry.py:build_node_registry",
            }
        ),
        encoding="utf-8",
    )
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "descriptors": {},
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    workspace = tmp_path / "vibeflow_config.jsonc"
    workspace.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "python", "path": "python_project"},
                    {"id": "javascript", "path": "javascript_project"},
                ]
            }
        ),
        encoding="utf-8",
    )
    import vibeflow.tooling.application.workspace_quality as aggregator

    child_calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(command, **kwargs):
        arguments = list(command[3:])
        child_calls.append((list(command), dict(kwargs)))
        target = arguments[arguments.index("--project-target") + 1]
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "PASS", "owner": target}),
            stderr="",
        )

    monkeypatch.setattr(aggregator.subprocess, "run", fake_run)
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("vibeflow.tooling.application.python.cli") or name.startswith(
            "vibeflow.tooling.application.javascript.cli"
        ):
            raise AssertionError(f"Target Application loaded in parent: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    code = cli_main(
        [
            "quality-check",
            "--workspace",
            str(workspace),
            "--json",
            "--max-lines",
            "50",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "PASS"
    assert [item["target"] for item in payload["roots"]] == [
        "python",
        "javascript",
    ]
    assert [item["report"]["owner"] for item in payload["roots"]] == [
        "python",
        "javascript",
    ]
    assert len(child_calls) == 2
    for command, options in child_calls:
        assert command[:3] == [sys.executable, "-m", "vibeflow"]
        arguments = command[3:]
        assert arguments[arguments.index("--workspace") + 1] == str(workspace)
        assert options["check"] is False
        assert options["stdout"] is subprocess.PIPE
        assert options["stderr"] is subprocess.PIPE
        assert "PYTHONPATH" in options["env"]
    assert "--max-lines" in child_calls[0][0]
    assert "--max-lines" not in child_calls[1][0]


def test_mixed_workspace_quality_keeps_workspace_for_external_roots(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    workspace_dir = tmp_path / "workspace"
    external_dir = tmp_path / "external"
    workspace_dir.mkdir()
    external_dir.mkdir()
    python_root = external_dir / "python_project"
    javascript_root = external_dir / "javascript_project"
    python_root.mkdir()
    javascript_root.mkdir()
    (python_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
                "registry": "registry.py:build_node_registry",
            }
        ),
        encoding="utf-8",
    )
    (javascript_root / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "javascript",
                "descriptors": {},
                "javascript": {"package_root": "."},
            }
        ),
        encoding="utf-8",
    )
    workspace = workspace_dir / "vibeflow_config.jsonc"
    workspace.write_text(
        json.dumps(
            {
                "roots": [
                    {"id": "python", "path": str(python_root)},
                    {"id": "javascript", "path": str(javascript_root)},
                ]
            }
        ),
        encoding="utf-8",
    )
    import vibeflow.tooling.application.workspace_quality as aggregator

    captured: list[list[str]] = []

    def fake_run(command, **_kwargs):
        captured.append(list(command[3:]))
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"status": "PASS"}),
            stderr="",
        )

    monkeypatch.setattr(aggregator.subprocess, "run", fake_run)

    assert cli_main(
        ["quality-check", "--workspace", str(workspace), "--json"]
    ) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert len(captured) == 2
    for arguments in captured:
        assert arguments[arguments.index("--workspace") + 1] == str(workspace)
