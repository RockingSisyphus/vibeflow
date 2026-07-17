from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable, Iterator, Mapping

from vibeflow.diagnostics import core_diagnostic_sink
from vibeflow.health.types import HealthFinding, HealthReport
from vibeflow.run_directory import InvalidRunIdError, parse_run_id_argument, validate_run_id


CLI_ARGV_TYPE = "cli.argv"
CLI_EXIT_CODE_TYPE = "cli.exit_code"


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
    parser.add_argument("--policy", required=False, help="explicit kernel_policy.jsonc/governance.jsonc path")
    parser.add_argument("--run-root", required=False, help="directory where run artifacts are created")
    parser.add_argument(
        "--run-id",
        required=False,
        type=parse_run_id_argument,
        help="optional deterministic run id for tests or controlled runs",
    )
    add_runtime_options(parser)


def _non_empty_path_argument(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("must be a non-empty path")
    return value


def validate_delegate_cli_graph_contract(graph, report: HealthReport) -> HealthReport:
    findings: list[HealthFinding] = []
    argv_inputs = [
        item
        for item in graph.inputs
        if item.key == CLI_ARGV_TYPE or item.type == CLI_ARGV_TYPE
    ]
    if (
        len(argv_inputs) != 1
        or argv_inputs[0].key != CLI_ARGV_TYPE
        or argv_inputs[0].type != CLI_ARGV_TYPE
    ):
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.ARGV_INPUT",
                "delegate-cli requires exactly one pipeline input with key and type 'cli.argv'",
                details={
                    "matches": len(argv_inputs),
                    "inputs": [
                        {"key": item.key, "type": item.type}
                        for item in argv_inputs
                    ],
                },
            )
        )

    exit_outputs = [item for item in graph.outputs if item.type == CLI_EXIT_CODE_TYPE]
    if len(exit_outputs) != 1 or exit_outputs[0].cardinality != "exactly_one":
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.EXIT_OUTPUT",
                "delegate-cli requires exactly one pipeline output of type 'cli.exit_code' with cardinality 'exactly_one'",
                details={
                    "matches": len(exit_outputs),
                    "cardinalities": [item.cardinality for item in exit_outputs],
                },
            )
        )

    exit_providers = [
        (node.id, provider.key, provider.type, node.async_mode)
        for node in graph.nodes
        for provider in node.provides
        if provider.key == CLI_EXIT_CODE_TYPE or provider.type == CLI_EXIT_CODE_TYPE
    ]
    if (
        len(exit_providers) != 1
        or exit_providers[0][1] != CLI_EXIT_CODE_TYPE
        or exit_providers[0][2] != CLI_EXIT_CODE_TYPE
        or exit_providers[0][3] == "detached"
    ):
        findings.append(
            _contract_finding(
                "CLI.DELEGATE.EXIT_PROVIDER",
                "delegate-cli requires exactly one provider whose key and type are both 'cli.exit_code'",
                details={
                    "matches": len(exit_providers),
                    "providers": [
                        {"node": node_id, "key": key, "type": data_type, "async": async_mode}
                        for node_id, key, data_type, async_mode in exit_providers
                    ],
                },
            )
        )

    if not findings:
        return report
    status = "ERROR" if report.status == "ERROR" else "FAIL"
    return replace(report, status=status, errors=(*report.errors, *findings))


def extract_delegate_cli_exit_code(context: object) -> tuple[int | None, str | None]:
    if context is None or not hasattr(context, "get"):
        return None, "delegate CLI result does not expose cli.exit_code"
    try:
        payload = context.get(CLI_EXIT_CODE_TYPE)
    except (KeyError, TypeError, ValueError):
        return None, "delegate CLI result is missing cli.exit_code"
    if not isinstance(payload, Mapping):
        return None, "delegate CLI result cli.exit_code must be a DataEnvelope payload"
    if payload.get("key") != CLI_EXIT_CODE_TYPE or payload.get("type") != CLI_EXIT_CODE_TYPE:
        return None, "delegate CLI exit provider must use key and type cli.exit_code"
    value = payload.get("value")
    if type(value) is not int or not 0 <= value <= 255:
        return None, "delegate CLI exit value must be an integer from 0 to 255"
    return value, None


def handle_delegate_cli(args) -> int:
    from vibeflow.cli import _load_workspace_for_cli, _runtime_options_from_args
    from vibeflow.runner import (
        CheckedRunError,
        CheckedRunResult,
        RunDirectoryExistsError,
        _new_run_id,
        _prepare_run_dir,
        _write_refused_artifacts,
    )

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

    def collect(message: str) -> None:
        messages.append("CORE " + _single_line(message))

    owned_run_dir: Path | None = None
    try:
        owned_run_dir = _prepare_run_dir(run_root, actual_run_id)
        with core_diagnostic_sink(collect):
            workspace = _load_workspace_for_cli(Path(args.workspace))
            if isinstance(workspace, HealthReport):
                _write_refused_artifacts(owned_run_dir, workspace, include_effective_policy=True)
                result = CheckedRunResult(actual_run_id, owned_run_dir, workspace)
                raise CheckedRunError("delegate CLI refused: workspace load failed", result)

            initial = {CLI_ARGV_TYPE: list(getattr(args, "delegate_argv", ()))}
            options = _runtime_options_from_args(args)
            from vibeflow.workspace import run_workspace_checked

            with _workspace_import_paths(workspace):
                result = run_workspace_checked(
                    Path(args.config),
                    workspace=workspace,
                    initial=initial,
                    run_root=run_root,
                    run_id=actual_run_id,
                    runtime_options=options,
                    delegate_cli=True,
                    _prepared_run_dir=owned_run_dir,
                )
    except RunDirectoryExistsError:
        _minimal_stderr("run directory already exists")
        return 1
    except CheckedRunError as exc:
        messages.extend(
            (
                f"ERROR CLI.DELEGATE.FAIL stage=health status={exc.result.health.status}",
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


def _contract_finding(rule_id: str, message: str, *, details: Mapping[str, object]) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="pipeline",
        object_id="pipeline",
        failure_layer="contract",
        message=message,
        suggested_fix_type="fix_config",
        details=dict(details),
    )


def _artifact_line(run_dir: Path) -> str:
    return f"INFO CLI.DELEGATE.ARTIFACTS run_dir={_single_line(run_dir)} health=health_report.json trace=runtime_trace.jsonl"


def _single_line(message: str) -> str:
    return str(message).replace("\r", "\\r").replace("\n", "\\n")


@contextmanager
def _workspace_import_paths(workspace: object) -> Iterator[None]:
    inserted: list[str] = []
    roots = tuple(getattr(workspace, "roots", ()) or ())
    for root in reversed(roots):
        value = str(getattr(root, "path", "") or "")
        if value and value not in sys.path:
            sys.path.insert(0, value)
            inserted.append(value)
    try:
        yield
    finally:
        for value in inserted:
            if value in sys.path:
                sys.path.remove(value)


def _finish_with_log(run_dir: Path, messages: list[str], exit_code: int) -> int:
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "vibeflow.log").write_text("\n".join(messages) + "\n", encoding="utf-8")
    except OSError:
        _minimal_stderr("cannot write delegate CLI run log")
        return 1
    return exit_code


def _minimal_stderr(message: str) -> None:
    print(f"vibeflow delegate-cli: {message}", file=sys.stderr)
