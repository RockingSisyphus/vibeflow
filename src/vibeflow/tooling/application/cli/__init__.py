"""Target-neutral command dispatcher.

Only project configuration is inspected here.  Target applications are loaded
after the owning root has been identified, so a rejected command never imports
the wrong Target closure.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from vibeflow.tooling.project.architecture_types import WorkspaceConfigError
from vibeflow.tooling.project.diagnostic_sink import core_diagnostic_sink
from vibeflow.tooling.project.workspace_loader import (
    find_project_config,
    load_project_target,
    load_workspace_config,
)


_PYTHON_ONLY_COMMANDS = frozenset({"inspect-node", "run", "delegate-cli"})
_JAVASCRIPT_ONLY_COMMANDS = frozenset({"build"})
_SHARED_COMMANDS = frozenset(
    {
        "validate",
        "inspect-config",
        "export-mermaid",
        "export-architecture",
        "export-ascii",
        "export-svg",
        "review",
        "quality-check",
    }
)


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[0] in {"-h", "--help"}:
        return _show_root_help(raw_args)
    command = raw_args[0]
    if command not in (
        _PYTHON_ONLY_COMMANDS | _JAVASCRIPT_ONLY_COMMANDS | _SHARED_COMMANDS
    ):
        parser = build_parser()
        parser.error(f"unknown command: {command}")
        return 2

    if command in _SHARED_COMMANDS and _is_command_help(raw_args):
        return _show_shared_command_help(command)
    if _is_target_specific_help(command, raw_args):
        return _dispatch_target_help(command, raw_args)

    try:
        # Target discovery is metadata routing, not the command's formal
        # configuration load.  Suppress optional parser trace here so the
        # selected Application can capture and publish it in its own diagnostic
        # context exactly once.
        with core_diagnostic_sink(lambda _message: None):
            target = _command_target(command, raw_args)
    except WorkspaceConfigError as exc:
        return _print_error(exc.rule_id, exc.message, details=exc.source_location)

    if command in _PYTHON_ONLY_COMMANDS and target != "python":
        return _target_mismatch(command, expected="python", actual=target)
    if command in _JAVASCRIPT_ONLY_COMMANDS and target != "javascript":
        return _target_mismatch(
            command,
            expected="javascript",
            actual=target or "undeclared",
        )

    if target == "javascript":
        from vibeflow.tooling.application.javascript.cli import main as target_main

        return target_main(raw_args)
    if target == "mixed":
        return _dispatch_mixed_workspace(command, raw_args)

    from vibeflow.tooling.application.python.cli import main as target_main

    return target_main(raw_args)


def build_parser() -> argparse.ArgumentParser:
    """Build the target-neutral command index used for root help/errors."""

    parser = argparse.ArgumentParser(prog="vibeflow")
    commands = parser.add_subparsers(dest="command")
    for name, help_text in (
        ("build", "compile a JavaScript workflow into AOT output"),
        ("validate", "validate a workflow configuration"),
        ("inspect-node", "inspect a Python node implementation"),
        ("inspect-config", "inspect a workflow configuration"),
        ("export-mermaid", "export a workflow as Mermaid"),
        ("export-architecture", "export a workflow architecture document"),
        ("export-ascii", "export a workflow as ASCII"),
        ("export-svg", "render a workflow as SVG"),
        ("review", "review a workflow"),
        ("run", "run a Python workflow"),
        ("delegate-cli", "run a delegated Python CLI workflow"),
        ("quality-check", "check a project"),
    ):
        commands.add_parser(name, help=help_text, add_help=False)
    return parser


def _command_target(command: str, args: list[str]) -> str:
    workspace_value = _option_value(args, "--workspace")
    config_value = _option_value(args, "--config")
    path_value = _option_value(args, "--path")
    explicit_target = _option_value(args, "--project-target")

    if workspace_value:
        workspace = load_workspace_config(workspace_value)
        selected_path = config_value or path_value
        if selected_path:
            root = workspace.root_for_path(Path(selected_path).expanduser().resolve())
            if root is None:
                raise WorkspaceConfigError(
                    "WORKSPACE.CONFIG.OUTSIDE_ROOT",
                    f"path is not under any workspace root: {Path(selected_path).expanduser().resolve()}",
                    {"path": str(Path(selected_path).expanduser().resolve())},
                )
            return root.project_target
        targets = {root.project_target for root in workspace.roots}
        if len(targets) == 1:
            return next(iter(targets))
        return "mixed"

    module_value = _option_value(args, "--module")
    discovery_path = path_value or config_value or module_value
    if command == "quality-check" and not discovery_path:
        discovery_path = "."
    if discovery_path:
        project_config = find_project_config(discovery_path)
        if project_config is not None:
            discovered_target = load_project_target(project_config)
            if explicit_target and explicit_target != discovered_target:
                raise WorkspaceConfigError(
                    "CLI.PROJECT_TARGET.MISMATCH",
                    "--project-target conflicts with the owning project config",
                    {
                        "path": str(project_config),
                        "expected": discovered_target,
                        "actual": explicit_target,
                    },
                )
            return discovered_target
    if explicit_target and command == "quality-check":
        if explicit_target not in {"python", "javascript"}:
            raise WorkspaceConfigError(
                "WORKSPACE.PROJECT_TARGET.INVALID",
                "--project-target must be exactly 'python' or 'javascript'",
                {"field": "--project-target", "value": explicit_target},
            )
        return explicit_target
    subject = discovery_path or "."
    message = (
        "quality-check --path outside a VibeFlow root requires --project-target"
        if command == "quality-check" and path_value
        else "command path is not owned by a vibeflow_project.jsonc with project_target"
    )
    raise WorkspaceConfigError(
        "WORKSPACE.PROJECT_TARGET.MISSING",
        message,
        {
            "path": str(Path(subject).expanduser().resolve()),
            "field": "project_target",
        },
    )


def _option_value(args: list[str], name: str) -> str:
    kernel_args = args[: args.index("--")] if "--" in args else args
    prefix = f"{name}="
    for index, item in enumerate(kernel_args):
        if item.startswith(prefix):
            return item[len(prefix) :]
        if item == name and index + 1 < len(kernel_args):
            return kernel_args[index + 1]
    return ""


def _dispatch_mixed_workspace(command: str, args: list[str]) -> int:
    if command != "quality-check":
        return _print_error(
            "CLI.PROJECT_TARGET.MISMATCH",
            f"{command} must resolve to exactly one project root",
        )
    try:
        from vibeflow.tooling.application.workspace_quality import main as quality_main
    except ImportError:
        return _print_error(
            "CLI.PROJECT_TARGET.MISMATCH",
            "quality-check for a mixed-target workspace is not available",
        )
    return quality_main(args)


def _is_target_specific_help(command: str, args: list[str]) -> bool:
    return command in (
        _PYTHON_ONLY_COMMANDS | _JAVASCRIPT_ONLY_COMMANDS
    ) and _is_command_help(args)


def _is_command_help(args: list[str]) -> bool:
    kernel_args = args[: args.index("--")] if "--" in args else args
    return any(item in {"-h", "--help"} for item in kernel_args[1:])


def _show_shared_command_help(command: str) -> int:
    descriptions = {
        "validate": "validate a workflow configuration",
        "inspect-config": "inspect a workflow configuration",
        "export-mermaid": "export a workflow as Mermaid",
        "export-architecture": "export a workflow architecture document",
        "export-ascii": "export a workflow as ASCII",
        "export-svg": "render a workflow as SVG",
        "review": "review a workflow",
        "quality-check": "check project architecture and maintainability",
    }
    parser = argparse.ArgumentParser(
        prog=f"vibeflow {command}",
        description=descriptions[command],
        epilog=(
            "The owning vibeflow_project.jsonc selects the Python or "
            "JavaScript command implementation."
        ),
    )
    parser.add_argument("--workspace", help="workspace vibeflow_config.jsonc")
    if command == "quality-check":
        parser.add_argument("--path", help="project root or source path")
        parser.add_argument("--config", help="workflow JSONC path")
        parser.add_argument(
            "--project-target",
            choices=("python", "javascript"),
            help="required for a path outside a configured project root",
        )
        parser.add_argument("--json", action="store_true")
    else:
        parser.add_argument("--config", required=True, help="workflow JSONC path")
        if command == "validate":
            parser.add_argument("--json", action="store_true")
        if command.startswith("export-") or command == "review":
            parser.add_argument("--output", help="output file")
        if command == "export-architecture":
            parser.add_argument("--check", action="store_true")
    parser.print_help()
    return 0


def _dispatch_target_help(command: str, args: list[str]) -> int:
    if command in _JAVASCRIPT_ONLY_COMMANDS:
        from vibeflow.tooling.application.javascript.cli import main as target_main

        return target_main(args)
    from vibeflow.tooling.application.python.cli import main as target_main

    return target_main(args)


def _target_mismatch(command: str, *, expected: str, actual: str) -> int:
    return _print_error(
        "CLI.PROJECT_TARGET.MISMATCH",
        f"{command} requires project_target {expected!r}, got {actual!r}",
        details={"command": command, "expected": expected, "actual": actual},
    )


def _print_error(
    code: str,
    message: str,
    *,
    details: object | None = None,
) -> int:
    payload: dict[str, object] = {
        "status": "ERROR",
        "code": code,
        "error": message,
    }
    if details:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1


def _show_root_help(raw_args: list[str]) -> int:
    parser = build_parser()
    if raw_args:
        parser.print_help()
        return 0
    parser.print_usage(sys.stderr)
    return 2


__all__ = ["build_parser", "main"]
