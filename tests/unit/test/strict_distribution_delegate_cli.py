from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from build_distribution import build_distribution


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SOURCE_RUNNER = (
    REPOSITORY_ROOT
    / "distribution"
    / "kernel_development_pack"
    / "project_template"
    / "run.py"
)


def _load_kernel_cli_args(source_path: Path, workspace_path: Path):
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    assignments = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"COMMAND_ALIASES", "WORKSPACE_COMMANDS"}
    }
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_kernel_cli_args"
    )
    namespace = {
        "COMMAND_ALIASES": assignments["COMMAND_ALIASES"],
        "WORKSPACE_COMMANDS": assignments["WORKSPACE_COMMANDS"],
        "WORKSPACE_CONFIG_PATH": workspace_path,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"),
        namespace,
    )
    return assignments, namespace["_kernel_cli_args"]


@pytest.mark.parametrize(
    ("core_options", "business_argv", "expect_injected"),
    [
        (["--config", "main.jsonc"], ["--input", "data.yaml", "--verbose"], True),
        (
            ["--config", "main.jsonc"],
            ["--workspace", "business-workspace", "--verbose"],
            True,
        ),
        (
            ["--config", "main.jsonc"],
            ["--workspace=business-workspace", "--verbose"],
            True,
        ),
        (
            ["--workspace", "custom.jsonc", "--config", "main.jsonc"],
            ["--verbose"],
            False,
        ),
        (
            ["--workspace=custom.jsonc", "--config", "main.jsonc"],
            ["--verbose"],
            False,
        ),
        (
            ["--workspace-mode", "custom", "--config", "main.jsonc"],
            ["--verbose"],
            True,
        ),
    ],
)
def test_delegate_cli_workspace_detection_stops_at_passthrough_separator(
    tmp_path: Path,
    core_options: list[str],
    business_argv: list[str],
    expect_injected: bool,
) -> None:
    workspace_path = tmp_path / "vibeflow_config.jsonc"
    workspace_path.write_text("{}", encoding="utf-8")
    assignments, kernel_cli_args = _load_kernel_cli_args(SOURCE_RUNNER, workspace_path)

    original = ["delegate-cli", *core_options, "--", *business_argv]
    forwarded = kernel_cli_args(original)

    assert "delegate-cli" in assignments["WORKSPACE_COMMANDS"]
    assert "run-cli" not in assignments["WORKSPACE_COMMANDS"]
    separator = forwarded.index("--")
    assert forwarded[separator + 1 :] == business_argv
    assert forwarded[0] == "delegate-cli"
    if expect_injected:
        assert forwarded[1:3] == ["--workspace", str(workspace_path)]
        assert forwarded[3:separator] == core_options
    else:
        assert forwarded[1:separator] == core_options


def test_delegate_cli_does_not_inject_workspace_when_distribution_has_none(
    tmp_path: Path,
) -> None:
    missing_workspace = tmp_path / "missing-vibeflow-config.jsonc"
    assignments, kernel_cli_args = _load_kernel_cli_args(SOURCE_RUNNER, missing_workspace)
    original = [
        "delegate-cli",
        "--config",
        "main.jsonc",
        "--",
        "--workspace=business-workspace",
    ]

    assert "delegate-cli" in assignments["WORKSPACE_COMMANDS"]
    assert kernel_cli_args(original) == original


def test_built_distribution_preserves_delegate_cli_passthrough_rules(
    tmp_path: Path,
) -> None:
    output = tmp_path / "distribution"
    build_distribution(output, run_self_check=False)
    built_runner = output / "run.py"
    built_workspace = output / "vibeflow_config.jsonc"
    assignments, kernel_cli_args = _load_kernel_cli_args(built_runner, built_workspace)
    original = [
        "delegate-cli",
        "--config",
        "project/configs/main.jsonc",
        "--",
        "--workspace",
        "business-workspace",
        "--input",
        "data.yaml",
        "--verbose",
    ]

    forwarded = kernel_cli_args(original)

    assert built_runner.read_bytes() == SOURCE_RUNNER.read_bytes()
    assert "delegate-cli" in assignments["WORKSPACE_COMMANDS"]
    assert "run-cli" not in assignments["WORKSPACE_COMMANDS"]
    assert forwarded == [
        "delegate-cli",
        "--workspace",
        str(built_workspace),
        "--config",
        "project/configs/main.jsonc",
        "--",
        "--workspace",
        "business-workspace",
        "--input",
        "data.yaml",
        "--verbose",
    ]


def test_built_delegate_cli_uses_explicit_workspace_for_lazy_imports_and_logs_core_trace(
    tmp_path: Path,
) -> None:
    distribution = tmp_path / "distribution"
    build_distribution(distribution, run_self_check=False)
    (distribution / "project" / "lazy_helper.py").write_text("CODE = 7\n", encoding="utf-8")

    custom = tmp_path / "custom"
    project = custom / "project"
    nodes = project / "nodes"
    nodes.mkdir(parents=True)
    (nodes / "__init__.py").write_text("", encoding="utf-8")
    (project / "lazy_helper.py").write_text("CODE = 13\n", encoding="utf-8")
    (custom / "vibeflow_config.jsonc").write_text(
        json.dumps(
            {
                "policy": {},
                "roots": [{"id": "custom", "path": "project"}],
            }
        ),
        encoding="utf-8",
    )
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "registry": "registry.py:build_node_registry",
                "quality_enabled": False,
            }
        ),
        encoding="utf-8",
    )
    (project / "registry.py").write_text(
        textwrap.dedent(
            """
            from vibeflow import NodeRegistry
            from nodes.cli_nodes import StartNode, ExitNode, EndNode

            def build_node_registry():
                registry = NodeRegistry()
                registry.register("custom.start", StartNode, config_schema={}, config_defaults={})
                registry.register("custom.exit", ExitNode, config_schema={}, config_defaults={})
                registry.register("custom.end", EndNode, config_schema={}, config_defaults={})
                return registry
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (nodes / "cli_nodes.py").write_text(
        textwrap.dedent(
            """
            from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

            class StartNode:
                NODE_INFO = NodeInfo("custom.start", "Start", "test", "Starts the CLI.", "0.1.0", "terminal")
                CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))
                def run_pure(self, inputs, params):
                    return {}

            class ExitNode:
                NODE_INFO = NodeInfo("custom.exit", "Exit", "test", "Loads a workspace-local helper lazily.", "0.1.0", "io")
                CONTRACT = NodeContract(
                    requires=(DataRequirement("cli.argv", "exactly_one"),),
                    provides=(DataProvider("cli.exit_code", "cli.exit_code"),),
                    input_semantics={"cli.argv": ("business argv",)},
                    output_semantics={"cli.exit_code": ("business exit",)},
                    output_schema={"cli.exit_code": {"type": "integer"}},
                    examples=({"inputs": {"cli.argv": {"key": "cli.argv", "type": "cli.argv", "value": [], "source_node": "example"}}, "params": {}},),
                )
                def run_pure(self, inputs, params):
                    import lazy_helper
                    print(lazy_helper.__file__)
                    return {"cli.exit_code": lazy_helper.CODE}

            class EndNode:
                NODE_INFO = NodeInfo("custom.end", "End", "test", "Ends the CLI.", "0.1.0", "terminal")
                CONTRACT = NodeContract(
                    requires=(DataRequirement("cli.exit_code", "exactly_one"),),
                    input_semantics={"cli.exit_code": ("business exit",)},
                    examples=({"inputs": {"cli.exit_code": {"key": "cli.exit_code", "type": "cli.exit_code", "value": 0, "source_node": "example"}}, "params": {}},),
                )
                def run_pure(self, inputs, params):
                    return {}
            """
        ).lstrip(),
        encoding="utf-8",
    )
    config = project / "main.jsonc"
    config.write_text(
        json.dumps(
            {
                "pipeline": {
                    "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                    "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                    "nodes": [
                        {"id": "start", "type_used": "custom.start"},
                        {
                            "id": "exit",
                            "type_used": "custom.exit",
                            "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                            "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}],
                        },
                        {
                            "id": "end",
                            "type_used": "custom.end",
                            "requires": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                        },
                    ],
                    "edges": [["start", "exit"], ["exit", "end"]],
                }
            }
        ),
        encoding="utf-8",
    )
    run_root = tmp_path / "runs"
    env = dict(os.environ)
    env["VIBEFLOW_CONFIG_TRACE"] = "1"

    completed = subprocess.run(
        [
            sys.executable,
            str(distribution / "run.py"),
            "delegate-cli",
            "--workspace",
            str(custom / "vibeflow_config.jsonc"),
            "--config",
            str(config),
            "--run-root",
            str(run_root),
            "--run-id",
            "custom-workspace",
            "--",
        ],
        cwd=distribution,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 13
    assert completed.stdout == f"{project / 'lazy_helper.py'}\n"
    assert completed.stderr == ""
    log = (run_root / "custom-workspace" / "vibeflow.log").read_text(encoding="utf-8")
    assert "[vibeflow config]" in log
    assert str(distribution / "project" / "lazy_helper.py") not in completed.stdout
