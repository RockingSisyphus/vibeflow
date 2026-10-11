"""Command-line interface for repository checks."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence

from .models import Finding, Report, SourceLocation, make_report
from .profiles import PROFILE_NAMES, RepositoryCheckError, run_profile


def build_parser(default_root: Path | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vibeflow-repo-quality",
        description="Check the VibeFlow repository without importing VibeFlow.",
    )
    parser.add_argument("--profile", choices=PROFILE_NAMES, default="all")
    parser.add_argument(
        "--root",
        type=Path,
        default=default_root or Path.cwd(),
        help="VibeFlow repository root (default: current directory)",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--node",
        help="Node.js executable used by javascript-target (default: node on PATH)",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    default_root: Path | None = None,
) -> int:
    parser = build_parser(default_root)
    arguments = parser.parse_args(argv)
    try:
        report = run_profile(
            arguments.root,
            arguments.profile,
            node_executable=arguments.node,
        )
    except RepositoryCheckError as exc:
        report = _failure_report(
            arguments.profile,
            arguments.root,
            "CHECKER_CONFIGURATION",
            str(exc),
        )
        print(
            report.to_json() if arguments.format == "json" else report.to_text(),
            file=sys.stderr,
        )
        return 2
    except Exception as exc:  # The tool must distinguish its own failure from findings.
        report = _failure_report(
            arguments.profile,
            arguments.root,
            "CHECKER_INTERNAL",
            f"{type(exc).__name__}: {exc}",
        )
        print(
            report.to_json() if arguments.format == "json" else report.to_text(),
            file=sys.stderr,
        )
        return 2
    print(report.to_json() if arguments.format == "json" else report.to_text())
    return 0 if report.ok else 1


def _failure_report(profile: str, root: Path, code: str, message: str) -> Report:
    return make_report(
        profile,
        [
            Finding(
                code=code,
                severity="error",
                subject_type="quality_checker",
                subject_id=profile,
                source_location=SourceLocation(str(root), 1, 0),
                message=message,
                suggested_fix="Correct the checker configuration or execution environment and run it again.",
            )
        ],
    )


__all__ = ["build_parser", "main"]
