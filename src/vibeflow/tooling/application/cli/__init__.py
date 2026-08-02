"""Target-neutral command dispatcher.

The dispatcher inspects only the command name.  JavaScript builds and Python
runtime commands then load their own application closure lazily.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence


_PYTHON_COMMANDS = frozenset(
    {
        "validate",
        "inspect-node",
        "inspect-config",
        "export-mermaid",
        "export-architecture",
        "export-ascii",
        "export-svg",
        "review",
        "run",
        "delegate-cli",
        "quality-check",
    }
)
_JAVASCRIPT_COMMANDS = frozenset({"build"})


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args or raw_args[0] in {"-h", "--help"}:
        return _show_root_help(raw_args)
    command = raw_args[0]
    if command in _JAVASCRIPT_COMMANDS:
        from vibeflow.tooling.application.javascript.cli import main as js_main

        return js_main(raw_args)
    if command in _PYTHON_COMMANDS:
        from vibeflow.tooling.application.python.cli import main as python_main

        return python_main(raw_args)
    parser = build_parser()
    parser.error(f"unknown command: {command}")
    return 2


def build_parser() -> argparse.ArgumentParser:
    """Build the target-neutral command index used for root help/errors."""

    parser = argparse.ArgumentParser(prog="vibeflow")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser(
        "build",
        help="compile a workflow into JavaScript/TypeScript AOT output",
        add_help=False,
    )
    for name, help_text in (
        ("validate", "validate a Python workflow configuration"),
        ("inspect-node", "inspect a Python node implementation"),
        ("inspect-config", "inspect a Python workflow configuration"),
        ("export-mermaid", "export a Python workflow as Mermaid"),
        ("export-architecture", "export a Python architecture document"),
        ("export-ascii", "export a Python workflow as ASCII"),
        ("export-svg", "render a Python workflow as SVG"),
        ("review", "review a Python workflow"),
        ("run", "run a Python workflow"),
        ("delegate-cli", "run a delegated Python CLI workflow"),
        ("quality-check", "check a Python project"),
    ):
        commands.add_parser(name, help=help_text, add_help=False)
    return parser


def _show_root_help(raw_args: list[str]) -> int:
    parser = build_parser()
    if raw_args:
        parser.print_help()
        return 0
    parser.print_usage(sys.stderr)
    return 2


__all__ = ["build_parser", "main"]
