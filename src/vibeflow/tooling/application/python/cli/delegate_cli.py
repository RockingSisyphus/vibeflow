from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from vibeflow.tooling.project.diagnostic_sink import core_diagnostic_sink
from vibeflow.targets.python.sdk.loading import source_paths
from vibeflow.core.findings import HealthReport
from vibeflow.tooling.application.python.run_directory import InvalidRunIdError, parse_run_id_argument, validate_run_id
from vibeflow.tooling.application.python.delegate_contract import (
    CLI_ARGV_TYPE,
    extract_delegate_cli_exit_code,
)


def add_delegate_cli_parser(subparsers, add_runtime_options: Callable[[object], None]) -> None:
    parser = subparsers.add_parser(
        "delegate-cli",
        help="run a graph with delegated business argv, standard streams, and exit status",
        allow_abbrev=False,
    )
    parser.add_argument("--config", required=True, type=_non_empty_path_argument)
    parser.add_argument(
        "--workspace",
        required=True,
        type=_non_empty_path_argument,
        help="workspace vibeflow_config.jsonc path",
    )
    parser.add_argument("--run-root", required=False, help="directory where run artifacts are created")
    parser.add_argument(
        "--run-id",
        required=False,
        type=parse_run_id_argument,
        help="optional deterministic run id for tests or controlled runs",
    )
    parser.add_argument("--preview-root", help="override offline preview directory")
    parser.add_argument("--entry", help="named workflow entry")
    add_runtime_options(parser)


def _non_empty_path_argument(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("must be a non-empty path")
    return value


def handle_delegate_cli(args) -> int:
    from vibeflow.tooling.application.python.cli import (
        workspace_or_report,
        _runtime_options_from_args,
    )
    from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
    from vibeflow.tooling.application.python.execution import (CheckedRunError, CheckedRunResult, _new_run_id, _write_refused_artifacts)
    from vibeflow.tooling.application.python.run_directory import RunDirectoryExistsError

    try:
        actual_run_id = _new_run_id() if args.run_id is None else validate_run_id(args.run_id)
    except InvalidRunIdError:
        _minimal_stderr("invalid run id")
        return 1
    # Business-capable nodes may change cwd.  Anchor ownership and all later
    # artifact/log writes before execution so they cannot drift to a different
    # relative directory or overwrite a foreign run after chdir().
    run_root = (Path(args.run_root) if args.run_root else Path("runs")).resolve()
    expected_run_dir = run_root / actual_run_id
    messages = [
        f"INFO CLI.DELEGATE.START run_id={_single_line(actual_run_id)} config={_single_line(Path(args.config))}",
    ]
    from vibeflow.targets.python.runtime.observation import current_observation
    observer = current_observation()
    if observer is not None:
        observer.write_kernel(messages.pop())

    def collect(message: str) -> None:
        line = "CORE " + _single_line(message)
        observer = current_observation()
        if observer is not None:
            observer.write_kernel(line)
        else:
            messages.append(line)

    owned_run_dir: Path | None = None
    try:
        owned_run_dir = getattr(args, "_prepared_run_dir", None) or _prepare_run_dir(run_root, actual_run_id)
        with core_diagnostic_sink(collect):
            workspace = workspace_or_report(Path(args.workspace))
            if isinstance(workspace, HealthReport):
                _write_refused_artifacts(owned_run_dir, workspace, include_effective_policy=True)
                result = CheckedRunResult(actual_run_id, owned_run_dir, workspace)
                raise CheckedRunError("delegate CLI refused: workspace load failed", result)

            initial = {CLI_ARGV_TYPE: list(getattr(args, "delegate_argv", ()))}
            options = _runtime_options_from_args(args)
            from vibeflow.tooling.application.python.workspace_service import run_workspace_checked

            with source_paths((workspace.root_for_path(Path(args.config).resolve()).path, workspace.root)):
                result = run_workspace_checked(
                    Path(args.config),
                    workspace=workspace,
                    initial=initial,
                    run_root=run_root,
                    run_id=actual_run_id,
                    runtime_options=options,
                    delegate_cli=True,
                    _prepared_run_dir=owned_run_dir,
                    preview_root=getattr(args, "preview_root", None),
                entry=getattr(args, "entry", None),
                )
    except RunDirectoryExistsError:
        _minimal_stderr("run directory already exists")
        return 1
    except CheckedRunError as exc:
        messages.extend(
            (
                f"ERROR CLI.DELEGATE.FAIL stage=health status={exc.result.health.status} reason={_single_line(exc)}",
                _artifact_line(exc.result.run_dir),
                "INFO CLI.DELEGATE.END status=ERROR exit_code=1",
            )
        )
        return _finish_with_log(exc.result.run_dir, messages, 1)
    except SystemExit:
        if owned_run_dir is None:
            _minimal_stderr("cannot create delegate CLI run directory")
            return 1
        messages.extend(
            (
                "ERROR CLI.DELEGATE.FAIL stage=runtime type=SystemExit",
                _artifact_line(expected_run_dir),
                "INFO CLI.DELEGATE.END status=ERROR exit_code=1",
            )
        )
        return _finish_with_log(expected_run_dir, messages, 1)
    except Exception as exc:  # noqa: BLE001 - delegate mode must keep core diagnostics off business streams.
        if owned_run_dir is None:
            _minimal_stderr("cannot create delegate CLI run directory")
            return 1
        messages.extend(
            (
                f"ERROR CLI.DELEGATE.FAIL stage=runtime type={type(exc).__name__}",
                _artifact_line(expected_run_dir),
                "INFO CLI.DELEGATE.END status=ERROR exit_code=1",
            )
        )
        return _finish_with_log(expected_run_dir, messages, 1)

    exit_code, exit_error = extract_delegate_cli_exit_code(result.context)
    if exit_error is not None or exit_code is None:
        messages.extend(
            (
                f"ERROR CLI.DELEGATE.FAIL stage=exit_code reason={_single_line(exit_error or 'missing exit code')}",
                _artifact_line(result.run_dir),
                "INFO CLI.DELEGATE.END status=ERROR exit_code=1",
            )
        )
        return _finish_with_log(result.run_dir, messages, 1)
    messages.extend(
        (
            _artifact_line(result.run_dir),
            f"INFO CLI.DELEGATE.END status={result.health.status} exit_code={exit_code}",
        )
    )
    return _finish_with_log(result.run_dir, messages, exit_code)


def _artifact_line(run_dir: Path) -> str:
    return f"INFO CLI.DELEGATE.ARTIFACTS run_dir={_single_line(run_dir)} health=health_report.json trace=runtime_trace.jsonl"


def _single_line(message: str) -> str:
    return str(message).replace("\r", "\\r").replace("\n", "\\n")


def _finish_with_log(run_dir: Path, messages: list[str], exit_code: int) -> int:
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        from vibeflow.targets.python.runtime.observation import current_observation
        observer = current_observation()
        if observer is not None:
            observer.write_kernel("\n".join(messages))
            if exit_code != 0:
                failures = [message for message in messages if message.startswith("ERROR ")]
                observer.transition("failed", "; ".join(failures) or f"program exited with code {exit_code}")
        else:
            with (run_dir / "vibeflow.log").open("a", encoding="utf-8") as stream:
                stream.write("\n".join(messages) + "\n")
    except OSError:
        _minimal_stderr("cannot write delegate CLI run log")
        return 1
    return exit_code


def _minimal_stderr(message: str) -> None:
    print(f"vibeflow delegate-cli: {message}", file=sys.stderr)
