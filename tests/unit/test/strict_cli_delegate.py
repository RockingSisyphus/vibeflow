from __future__ import annotations

import sys
from pathlib import Path

import pytest

from vibeflow.cli import main
from vibeflow.cli.delegate_cli import extract_delegate_cli_exit_code, validate_delegate_cli_graph_contract
from vibeflow.data_contract import DataEnvelope, DataProvider, DataRequirement, RunResult
from vibeflow.diagnostics import emit_core_diagnostic
from vibeflow.graph_config import parse_graph_config
from vibeflow.health.types import HealthReport
from vibeflow.runner import CheckedRunResult
from vibeflow.node import NodeContract, NodeInfo
from vibeflow.plugin import PluginRegistry
from vibeflow.registry import NodeRegistry
from vibeflow.runtime import PipelineRuntime
from vibeflow.runtime.errors import PipelineRuntimeError


@pytest.fixture(autouse=True)
def _stub_delegate_workspace_loader(monkeypatch):
    monkeypatch.setattr("vibeflow.cli._load_workspace_for_cli", lambda path: object())


class _StartNode:
    NODE_INFO = NodeInfo("delegate.start", "Start", "test", "Starts delegate test.", "0.1.0", "terminal")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        return {}


class _AuthorizedExitNode:
    NODE_INFO = NodeInfo("delegate.authorized_exit", "Authorized exit", "test", "Exits delegated CLI.", "0.1.0", "io")
    CONTRACT = NodeContract(
        requires=(DataRequirement("cli.argv", "exactly_one"),),
        provides=(DataProvider("cli.exit_code", "cli.exit_code"),),
        input_semantics={"cli.argv": ("business argv",)},
        output_semantics={"cli.exit_code": ("business exit code",)},
        output_schema={"cli.exit_code": {"type": "integer"}},
        examples=({"inputs": {"cli.argv": {"key": "cli.argv", "type": "cli.argv", "value": [], "source_node": "example"}}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        raise SystemExit(2)


class _UnauthorizedExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.unauthorized_exit", "Unauthorized exit", "test", "Cannot exit delegated CLI.", "0.1.0", "process")


class _NoneExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.none_exit", "None exit", "test", "Exits delegated CLI with the default success code.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit(None)


class _BoolExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.bool_exit", "Bool exit", "test", "Attempts an invalid boolean CLI exit.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit(True)


class _NegativeExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.negative_exit", "Negative exit", "test", "Attempts an invalid negative CLI exit.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit(-1)


class _LargeExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.large_exit", "Large exit", "test", "Attempts an invalid oversized CLI exit.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit(256)


class _StringExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.string_exit", "String exit", "test", "Attempts an invalid string CLI exit.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit("invalid")


class _ArgparseExitNode(_AuthorizedExitNode):
    NODE_INFO = NodeInfo("delegate.argparse_exit", "Argparse exit", "test", "Exercises real argparse exits.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        import argparse

        parser = argparse.ArgumentParser(prog="delegate-business")
        parser.add_argument("--required", required=True)
        parser.parse_args(list(inputs["cli.argv"]["value"]))
        return {"cli.exit_code": 0}


class _DetachedExitNode:
    NODE_INFO = NodeInfo("delegate.detached_exit", "Detached exit", "test", "Exits from a detached task.", "0.1.0", "io")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}},))

    def run_pure(self, inputs, params):
        raise SystemExit(11)


class _SecondDetachedExitNode(_DetachedExitNode):
    NODE_INFO = NodeInfo("delegate.second_detached_exit", "Second detached exit", "test", "Exits from another detached task.", "0.1.0", "io")

    def run_pure(self, inputs, params):
        raise SystemExit(12)


class _DetachedFailureNode(_DetachedExitNode):
    NODE_INFO = NodeInfo("delegate.detached_failure", "Detached failure", "test", "Fails from a detached task.", "0.1.0", "process")

    def run_pure(self, inputs, params):
        raise RuntimeError("late detached failure")


class _SuccessfulSideNode:
    NODE_INFO = NodeInfo("delegate.successful_side", "Successful side", "test", "Completes an async side task.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=(DataProvider("async.pending", "async.pending"),),
        output_semantics={"async.pending": ("completed side result",)},
        output_schema={"async.pending": {"type": "string"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"async.pending": "done"}


class _NormalExitNode:
    NODE_INFO = NodeInfo("delegate.normal_exit", "Normal exit", "test", "Returns a normal delegated exit.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=(DataProvider("cli.exit_code", "cli.exit_code"),),
        output_semantics={"cli.exit_code": ("business exit code",)},
        output_schema={"cli.exit_code": {"type": "integer"}},
        examples=({"inputs": {}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"cli.exit_code": 0}


class _AsyncDiagnosticExitNode(_NormalExitNode):
    NODE_INFO = NodeInfo(
        "delegate.async_diagnostic_exit",
        "Async diagnostic exit",
        "test",
        "Emits a core diagnostic from an async worker.",
        "0.1.0",
        "process",
    )

    def run_pure(self, inputs, params):
        emit_core_diagnostic("ASYNC-CORE-DIAGNOSTIC")
        return {"cli.exit_code": 0}


class _ExitEndNode:
    NODE_INFO = NodeInfo("delegate.exit_end", "Exit end", "test", "Consumes a delegated exit.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=(DataRequirement("cli.exit_code", "exactly_one"),),
        input_semantics={"cli.exit_code": ("business exit code",)},
        examples=(
            {
                "inputs": {
                    "cli.exit_code": {
                        "key": "cli.exit_code",
                        "type": "cli.exit_code",
                        "value": 0,
                        "source_node": "example",
                    }
                },
                "params": {},
            },
        ),
    )

    def run_pure(self, inputs, params):
        return {}


def _runtime_registry() -> NodeRegistry:
    registry = NodeRegistry()
    registry.register("delegate.start", _StartNode, config_schema={}, config_defaults={})
    registry.register("delegate.authorized_exit", _AuthorizedExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.unauthorized_exit", _UnauthorizedExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.none_exit", _NoneExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.bool_exit", _BoolExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.negative_exit", _NegativeExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.large_exit", _LargeExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.string_exit", _StringExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.argparse_exit", _ArgparseExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.detached_exit", _DetachedExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.second_detached_exit", _SecondDetachedExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.detached_failure", _DetachedFailureNode, config_schema={}, config_defaults={})
    registry.register("delegate.successful_side", _SuccessfulSideNode, config_schema={}, config_defaults={})
    registry.register("delegate.normal_exit", _NormalExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.async_diagnostic_exit", _AsyncDiagnosticExitNode, config_schema={}, config_defaults={})
    registry.register("delegate.exit_end", _ExitEndNode, config_schema={}, config_defaults={})
    return registry


def _exit_graph(node_type: str):
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {"id": "exit", "type_used": node_type},
                ],
                "edges": [["start", "exit"]],
            }
        }
    )


def _graph(*, include_argv: bool = True, exit_cardinality: str = "exactly_one"):
    inputs = []
    if include_argv:
        inputs.append({"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"})
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": inputs,
                "outputs": [
                    {
                        "type": "cli.exit_code",
                        "cardinality": exit_cardinality,
                        "display_name": "CLI exit code",
                    }
                ],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {
                                "key": "cli.exit_code",
                                "type": "cli.exit_code",
                                "display_name": "CLI exit code",
                            }
                        ],
                    }
                ],
            }
        }
    )


def _multiple_detached_graph(second_node_type: str):
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {"id": "first", "type_used": "delegate.detached_exit", "async": "detached"},
                    {"id": "second", "type_used": second_node_type, "async": "detached"},
                    {
                        "id": "normal_exit",
                        "type_used": "delegate.normal_exit",
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                    },
                    {"id": "end", "type_used": "delegate.exit_end"},
                ],
                "edges": [["start", "first"], ["first", "second"], ["second", "normal_exit"], ["normal_exit", "end"]],
            }
        }
    )


def _parallel_result_graph(second_node_type: str):
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "first",
                        "type_used": "delegate.detached_exit",
                        "provides": [{"key": "async.first", "type": "async.first", "display_name": "First result"}],
                        "async": "result_key",
                        "result_key": "async.first",
                    },
                    {
                        "id": "second",
                        "type_used": second_node_type,
                        "provides": [{"key": "async.second", "type": "async.second", "display_name": "Second result"}],
                        "async": "result_key",
                        "result_key": "async.second",
                    },
                    {
                        "id": "join",
                        "type_used": "delegate.exit_end",
                        "requires": [
                            {"type": "async.first", "cardinality": "exactly_one", "display_name": "First result"},
                            {"type": "async.second", "cardinality": "exactly_one", "display_name": "Second result"},
                        ],
                    },
                ],
                "edges": [["start", "first"], ["start", "second"], ["first", "join"], ["second", "join"]],
            }
        }
    )


def _async_diagnostic_graph():
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "output",
                        "type_used": "delegate.async_diagnostic_exit",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}
                        ],
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                    },
                    {"id": "end", "type_used": "delegate.exit_end"},
                ],
                "edges": [["start", "output"], ["output", "end"]],
            }
        }
    )


def _unconsumed_result_graph(*node_types: str):
    async_nodes = [
        {
            "id": f"side_{index}",
            "type_used": node_type,
            "provides": [
                {
                    "key": f"async.side_{index}",
                    "type": f"async.side_{index}",
                    "display_name": f"Side result {index}",
                }
            ],
            "async": "result_key",
            "result_key": f"async.side_{index}",
        }
        for index, node_type in enumerate(node_types)
    ]
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    *async_nodes,
                    {
                        "id": "normal_exit",
                        "type_used": "delegate.normal_exit",
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                    },
                    {"id": "end", "type_used": "delegate.exit_end"},
                ],
                "edges": [
                    *[["start", node["id"]] for node in async_nodes],
                    ["start", "normal_exit"],
                    ["normal_exit", "end"],
                ],
            }
        }
    )


def _exit_with_pending_pipeline(
    *,
    pending_node_type: str,
    async_mode: str,
    exit_node_type: str = "delegate.authorized_exit",
):
    pending_node = {
        "id": "a_pending",
        "type_used": pending_node_type,
        "async": async_mode,
    }
    if async_mode == "result_key":
        pending_node.update(
            {
                "provides": [
                    {
                        "key": "async.pending",
                        "type": "async.pending",
                        "display_name": "Pending async result",
                    }
                ],
                "result_key": "async.pending",
            }
        )
    return {
        "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
        "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
        "nodes": [
            {"id": "inner_start", "type_used": "delegate.start"},
            pending_node,
            {"id": "gate", "type_used": "delegate.start"},
            {"id": "inner_exit", "type_used": exit_node_type},
        ],
        "edges": [
            ["inner_start", "a_pending"],
            ["inner_start", "gate"],
            ["gate", "inner_exit"],
        ],
    }


def _exit_with_pending_graph(
    *,
    pending_node_type: str,
    async_mode: str,
    exit_node_type: str = "delegate.authorized_exit",
):
    return parse_graph_config(
        {
            "pipeline": _exit_with_pending_pipeline(
                pending_node_type=pending_node_type,
                async_mode=async_mode,
                exit_node_type=exit_node_type,
            )
        }
    )


def _nested_exit_with_pending_graph(*, pending_node_type: str, async_mode: str):
    inner = {
        "type_key": "delegate.inner_pending",
        "display_name": "Delegate inner with pending work",
        "description": "Raises a delegated exit while child async work is pending.",
        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
        "pipeline": _exit_with_pending_pipeline(
            pending_node_type=pending_node_type,
            async_mode=async_mode,
        ),
    }
    return parse_graph_config(
        {
            "nodesets": [inner],
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "inner",
                        "type_used": "delegate.inner_pending",
                        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                    },
                ],
                "edges": [["start", "inner"]],
            },
        }
    )


def _result(run_dir: Path, exit_value: object = 0) -> CheckedRunResult:
    context = RunResult()
    context.set(
        "cli.exit_code",
        DataEnvelope(
            key="cli.exit_code",
            type="cli.exit_code",
            value=exit_value,
            source_node="cli_output",
        ).to_input(),
    )
    return CheckedRunResult("delegate-test", run_dir, HealthReport(status="PASS"), context)


def test_delegate_cli_forwards_unknown_prefix_and_raw_suffix(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir == Path(kwargs["run_root"]) / kwargs["run_id"]
        assert run_dir.is_dir()
        captured.update(kwargs)
        print("business-out")
        print("business-err", file=sys.stderr)
        emit_core_diagnostic("config trace")
        return _result(run_dir, 7)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)
    status = main(
        [
            "delegate-cli",
            "--config",
            "project/configs/main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "delegate-test",
            "--verbose",
            "前缀",
            "--",
            "--config",
            "business.json",
            "",
        ]
    )

    streams = capsys.readouterr()
    assert status == 7
    assert captured["initial"] == {"cli.argv": ["--verbose", "前缀", "--config", "business.json", ""]}
    assert streams.out == "business-out\n"
    assert streams.err == "business-err\n"
    log = (tmp_path / "delegate-test" / "vibeflow.log").read_text(encoding="utf-8")
    assert "config trace" in log
    assert "exit_code=7" in log
    assert "business-out" not in log
    assert "business.json" not in log


def test_delegate_cli_omitted_separator_preserves_argv_and_does_not_read_stdin(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    captured = {}

    class UnreadableStdin:
        def read(self, *args, **kwargs):
            raise AssertionError("delegate-cli core consumed business stdin")

        def readline(self, *args, **kwargs):
            raise AssertionError("delegate-cli core consumed business stdin")

    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir.is_dir()
        captured.update(kwargs)
        return _result(run_dir, 0)

    monkeypatch.setattr(sys, "stdin", UnreadableStdin())
    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "no-separator",
            "--input",
            "data.yaml",
            "--verbose",
            "重复",
            "重复",
            "",
        ]
    )

    assert status == 0
    assert captured["initial"] == {
        "cli.argv": ["--input", "data.yaml", "--verbose", "重复", "重复", ""]
    }
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err == ""
    log = (tmp_path / "no-separator" / "vibeflow.log").read_text(encoding="utf-8")
    assert "INFO CLI.DELEGATE.START run_id=no-separator config=main.jsonc" in log
    assert "INFO CLI.DELEGATE.ARTIFACTS" in log
    assert "health=health_report.json trace=runtime_trace.jsonl" in log
    assert "INFO CLI.DELEGATE.END status=PASS exit_code=0" in log
    assert "data.yaml" not in log
    assert "重复" not in log


@pytest.mark.parametrize("value", [0, 1, 2, 255])
def test_delegate_cli_returns_valid_graph_exit_values_unchanged(monkeypatch, tmp_path, capsys, value) -> None:
    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir.is_dir()
        return _result(run_dir, value)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            f"delegate-exit-{value}",
        ]
    )

    assert status == value
    streams = capsys.readouterr()
    assert streams.out == ""
    assert streams.err == ""
    log = (tmp_path / f"delegate-exit-{value}" / "vibeflow.log").read_text(encoding="utf-8")
    assert f"exit_code={value}" in log


@pytest.mark.parametrize("value", [True, -1, 256, "2", None])
def test_delegate_cli_rejects_invalid_graph_exit_values(monkeypatch, tmp_path, capsys, value) -> None:
    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir.is_dir()
        return _result(run_dir, value)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)
    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "delegate-test",
        ]
    )
    streams = capsys.readouterr()
    assert status == 1
    assert streams.out == ""
    assert streams.err == ""
    assert "stage=exit_code" in (tmp_path / "delegate-test" / "vibeflow.log").read_text(encoding="utf-8")


def test_delegate_cli_runtime_failure_is_logged_without_core_console(monkeypatch, tmp_path, capsys) -> None:
    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir.is_dir()
        raise RuntimeError("secret business payload")

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)
    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "delegate-test",
        ]
    )
    streams = capsys.readouterr()
    assert status == 1
    assert streams.out == ""
    assert streams.err == ""
    log = (tmp_path / "delegate-test" / "vibeflow.log").read_text(encoding="utf-8")
    assert "stage=runtime type=RuntimeError" in log
    assert "secret business payload" not in log


def test_delegate_cli_routes_async_core_diagnostics_to_run_log(monkeypatch, tmp_path, capsys) -> None:
    def run_async_graph(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir.is_dir()
        context = PipelineRuntime(
            _async_diagnostic_graph(),
            registry=_runtime_registry(),
            run_dir=run_dir,
            delegate_cli=True,
        ).run(kwargs["initial"])
        return CheckedRunResult(kwargs["run_id"], run_dir, HealthReport(status="PASS"), context)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", run_async_graph)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "async-diagnostic",
        ]
    )

    assert status == 0
    assert capsys.readouterr().err == ""
    log = (tmp_path / "async-diagnostic" / "vibeflow.log").read_text(encoding="utf-8")
    assert "ASYNC-CORE-DIAGNOSTIC" in log


def test_delegate_cli_parser_errors_remain_argparse_errors(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["delegate-cli", "--verbose"])
    assert exc_info.value.code == 2
    assert "--config" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--config", ""),
        ("--workspace", ""),
        ("--async-flush-timeout", "-1"),
        ("--async-flush-timeout", "nan"),
        ("--async-flush-timeout", "inf"),
    ],
)
def test_delegate_cli_rejects_invalid_known_core_values_before_creating_run(
    tmp_path,
    capsys,
    option,
    value,
) -> None:
    run_root = tmp_path / "runs"
    argv = [
        "delegate-cli",
        "--config",
        "main.jsonc",
        "--workspace",
        "vibeflow_config.jsonc",
        "--run-root",
        str(run_root),
    ]
    if option in {"--config", "--workspace"}:
        argv[argv.index(option) + 1] = value
    else:
        argv.extend([option, value])

    with pytest.raises(SystemExit) as exc_info:
        main(argv)

    assert exc_info.value.code == 2
    assert capsys.readouterr().err
    assert not run_root.exists()


@pytest.mark.parametrize("abbreviation", ["--conf", "--work"])
def test_delegate_cli_disables_core_option_abbreviations(abbreviation, capsys) -> None:
    argv = ["delegate-cli", "--config", "main.jsonc", "--workspace", "workspace.jsonc"]
    if abbreviation == "--conf":
        argv = ["delegate-cli", abbreviation, "main.jsonc", "--workspace", "workspace.jsonc"]
    elif abbreviation == "--work":
        argv = ["delegate-cli", "--config", "main.jsonc", abbreviation, "workspace.jsonc"]
    with pytest.raises(SystemExit) as exc_info:
        main(argv)
    assert exc_info.value.code == 2
    assert capsys.readouterr().err


def test_delegate_cli_treats_runtime_option_abbreviation_as_business_argv(
    monkeypatch,
    tmp_path,
    capsys,
) -> None:
    captured = {}

    def fake_run_workspace_checked(config_path, **kwargs):
        captured.update(kwargs)
        return _result(Path(kwargs["_prepared_run_dir"]), 0)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "workspace.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "no-abbrev",
            "--async-flush-t",
            "1",
        ]
    )

    assert status == 0
    assert captured["initial"] == {"cli.argv": ["--async-flush-t", "1"]}
    assert capsys.readouterr().err == ""


def test_delegate_cli_direct_kernel_requires_workspace_without_creating_run(tmp_path, capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "delegate-cli",
                "--config",
                "main.jsonc",
                "--run-root",
                str(tmp_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "--workspace" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "policy_args",
    [
        ["--policy", "policy.jsonc"],
        ["--policy="],
        ["--policy", ""],
    ],
)
def test_delegate_cli_policy_conflict_is_argparse_error_without_creating_run(
    tmp_path,
    capsys,
    policy_args,
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "delegate-cli",
                "--config",
                "main.jsonc",
                "--workspace",
                "vibeflow_config.jsonc",
                *policy_args,
                "--run-root",
                str(tmp_path),
            ]
        )

    assert exc_info.value.code == 2
    assert "does not accept --policy" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "run_id",
    ["", ".", "..", "../escape", "nested/id", "nested\\id", "/absolute", "nul\x00id"],
)
def test_delegate_cli_rejects_unsafe_run_id_before_creating_run(tmp_path, capsys, run_id) -> None:
    run_root = tmp_path / "runs"

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "delegate-cli",
                "--config",
                "main.jsonc",
                "--workspace",
                "vibeflow_config.jsonc",
                "--run-root",
                str(run_root),
                "--run-id",
                run_id,
            ]
        )

    assert exc_info.value.code == 2
    assert "run id must be one non-empty path component" in capsys.readouterr().err
    assert not run_root.exists()
    assert not (tmp_path / "escape").exists()


def test_delegate_cli_allows_business_policy_after_separator(monkeypatch, tmp_path, capsys) -> None:
    captured = {}

    def fake_run_workspace_checked(config_path, **kwargs):
        captured.update(kwargs)
        return _result(Path(kwargs["_prepared_run_dir"]), 0)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "business-policy",
            "--",
            "--policy=business.jsonc",
        ]
    )

    assert status == 0
    assert captured["initial"] == {"cli.argv": ["--policy=business.jsonc"]}
    assert capsys.readouterr().err == ""


def test_delegate_cli_log_escapes_run_and_config_path_line_breaks(monkeypatch, tmp_path, capsys) -> None:
    def fake_run_workspace_checked(config_path, **kwargs):
        return _result(Path(kwargs["_prepared_run_dir"]), 0)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)
    run_root = tmp_path / "runs\r\nroot"
    run_id = "run\r\nid"
    config = "project/config\r\nmain.jsonc"

    status = main(
        [
            "delegate-cli",
            "--config",
            config,
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(run_root),
            "--run-id",
            run_id,
        ]
    )

    assert status == 0
    assert capsys.readouterr().err == ""
    log = (run_root / run_id / "vibeflow.log").read_text(encoding="utf-8")
    lines = log.splitlines()
    assert len(lines) == 3
    assert "run_id=run\\r\\nid config=project/config\\r\\nmain.jsonc" in lines[0]
    assert "runs\\r\\nroot/run\\r\\nid" in lines[1]


def test_delegate_cli_run_directory_race_does_not_overwrite_foreign_log(monkeypatch, tmp_path, capsys) -> None:
    from vibeflow.runner import _prepare_run_dir as original_prepare_run_dir

    def race_for_run_directory(run_root, run_id):
        run_dir = Path(run_root) / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "vibeflow.log").write_text("OTHER-RUN\n", encoding="utf-8")
        return original_prepare_run_dir(run_root, run_id)

    monkeypatch.setattr("vibeflow.runner._prepare_run_dir", race_for_run_directory)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "vibeflow_config.jsonc",
            "--run-root",
            str(tmp_path),
            "--run-id",
            "raced",
        ]
    )

    assert status == 1
    assert capsys.readouterr().err == "vibeflow delegate-cli: run directory already exists\n"
    assert (tmp_path / "raced" / "vibeflow.log").read_text(encoding="utf-8") == "OTHER-RUN\n"


def test_delegate_cli_run_directory_ownership_survives_business_chdir(monkeypatch, tmp_path, capsys) -> None:
    origin = tmp_path / "origin"
    destination = tmp_path / "business-cwd"
    origin.mkdir()
    destination.mkdir()
    monkeypatch.chdir(origin)

    def fake_run_workspace_checked(config_path, **kwargs):
        run_dir = Path(kwargs["_prepared_run_dir"])
        assert run_dir == origin / "runs" / "cwd-safe"
        monkeypatch.chdir(destination)
        return _result(run_dir, 0)

    monkeypatch.setattr("vibeflow.workspace.run_workspace_checked", fake_run_workspace_checked)

    status = main(
        [
            "delegate-cli",
            "--config",
            "main.jsonc",
            "--workspace",
            "workspace.jsonc",
            "--run-root",
            "runs",
            "--run-id",
            "cwd-safe",
        ]
    )

    assert status == 0
    assert capsys.readouterr().err == ""
    assert (origin / "runs" / "cwd-safe" / "vibeflow.log").is_file()
    assert not (destination / "runs").exists()


def test_delegate_cli_contract_is_fail_closed() -> None:
    report = validate_delegate_cli_graph_contract(_graph(include_argv=False, exit_cardinality="optional_one"), HealthReport(status="PASS"))
    assert report.status == "FAIL"
    assert {finding.rule_id for finding in report.errors} == {
        "CLI.DELEGATE.ARGV_INPUT",
        "CLI.DELEGATE.EXIT_OUTPUT",
    }


@pytest.mark.parametrize(
    "providers",
    [
        [],
        [{"key": "wrong", "type": "cli.exit_code", "display_name": "Wrong exit"}],
        [{"key": "cli.exit_code", "type": "wrong", "display_name": "Wrong exit"}],
        [
            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"},
            {"key": "other.exit", "type": "cli.exit_code", "display_name": "Other exit code"},
        ],
    ],
)
def test_delegate_cli_contract_rejects_missing_wrong_or_duplicate_exit_providers(providers) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [{"id": "output", "type_used": "delegate.output", "provides": providers}],
            }
        }
    )

    report = validate_delegate_cli_graph_contract(graph, HealthReport(status="PASS"))

    assert report.status == "FAIL"
    assert [finding.rule_id for finding in report.errors] == ["CLI.DELEGATE.EXIT_PROVIDER"]


def test_delegate_cli_contract_rejects_reserved_exit_key_conflict_across_nodes() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}
                        ],
                    },
                    {
                        "id": "shadow",
                        "type_used": "delegate.shadow",
                        "provides": [
                            {"key": "cli.exit_code", "type": "wrong", "display_name": "Shadow exit"}
                        ],
                    },
                ],
            }
        }
    )

    report = validate_delegate_cli_graph_contract(graph, HealthReport(status="PASS"))

    assert report.status == "FAIL"
    assert [finding.rule_id for finding in report.errors] == ["CLI.DELEGATE.EXIT_PROVIDER"]


@pytest.mark.parametrize(
    "inputs",
    [
        [{"key": "cli.argv", "type": "wrong", "display_name": "Wrong argv"}],
        [{"key": "wrong", "type": "cli.argv", "display_name": "Wrong argv"}],
        [
            {"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"},
            {"key": "wrong", "type": "cli.argv", "display_name": "Shadow argv"},
        ],
    ],
)
def test_delegate_cli_contract_rejects_reserved_argv_key_or_type_conflicts(inputs) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": inputs,
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}
                        ],
                    }
                ],
            }
        }
    )

    report = validate_delegate_cli_graph_contract(graph, HealthReport(status="PASS"))

    assert report.status == "FAIL"
    assert [finding.rule_id for finding in report.errors] == ["CLI.DELEGATE.ARGV_INPUT"]


def test_delegate_cli_contract_rejects_detached_exit_provider() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}
                        ],
                        "async": "detached",
                    }
                ],
            }
        }
    )

    report = validate_delegate_cli_graph_contract(graph, HealthReport(status="PASS"))

    assert report.status == "FAIL"
    assert [finding.rule_id for finding in report.errors] == ["CLI.DELEGATE.EXIT_PROVIDER"]
    assert report.errors[0].details["providers"][0]["async"] == "detached"


def test_delegate_cli_exit_extraction_requires_reserved_envelope() -> None:
    context = RunResult()
    context.set(
        "cli.exit_code",
        {"key": "wrong", "type": "cli.exit_code", "value": 0, "source_node": "output"},
    )
    value, error = extract_delegate_cli_exit_code(context)
    assert value is None
    assert error == "delegate CLI exit provider must use key and type cli.exit_code"


def test_authorized_node_system_exit_becomes_delegate_result(tmp_path) -> None:
    runtime = PipelineRuntime(
        _exit_graph("delegate.authorized_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )
    result = runtime.run({"cli.argv": ["--help"]})
    assert result.get("cli.exit_code")["value"] == 2
    assert result.get("runtime.stop_reason") == "business_exit"


@pytest.mark.parametrize("execution", ["plan", "block", "compiled"])
def test_delegate_cli_executes_normal_business_graph_once_in_every_execution_mode(
    tmp_path,
    execution,
) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "output",
                        "type_used": "delegate.normal_exit",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}
                        ],
                    },
                    {
                        "id": "end",
                        "type_used": "delegate.exit_end",
                        "requires": [
                            {"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}
                        ],
                    },
                ],
                "edges": [["start", "output"], ["output", "end"]],
            }
        }
    )
    runtime = PipelineRuntime(
        graph,
        registry=_runtime_registry(),
        run_dir=tmp_path / execution,
        delegate_cli=True,
        runtime_options={"execution": execution},
    )

    result = runtime.run({"cli.argv": ["--business"]})

    assert result.get("cli.exit_code")["value"] == 0
    assert runtime._node_runs == {"start": 1, "output": 1, "end": 1}


def test_normal_runtime_node_system_exit_is_pipeline_failure(tmp_path) -> None:
    runtime = PipelineRuntime(
        _exit_graph("delegate.authorized_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
    )

    with pytest.raises(PipelineRuntimeError, match="attempted SystemExit outside delegate CLI mode"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "SystemExit outside delegate CLI mode" in runtime.trace.exception


def test_authorized_node_system_exit_none_becomes_zero(tmp_path) -> None:
    runtime = PipelineRuntime(
        _exit_graph("delegate.none_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    result = runtime.run({"cli.argv": []})

    assert result.get("cli.exit_code")["value"] == 0
    assert result.get("runtime.stop_reason") == "business_exit"


def test_real_argparse_help_and_error_keep_business_streams_and_exit_codes(tmp_path, capsys) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "exit",
                        "type_used": "delegate.argparse_exit",
                        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}
                        ],
                    },
                ],
                "edges": [["start", "exit"]],
            }
        }
    )
    help_result = PipelineRuntime(
        graph,
        registry=_runtime_registry(),
        run_dir=tmp_path / "help",
        delegate_cli=True,
    ).run({"cli.argv": ["--help"]})
    help_streams = capsys.readouterr()

    assert help_result.get("cli.exit_code")["value"] == 0
    assert "usage: delegate-business" in help_streams.out
    assert help_streams.err == ""

    error_result = PipelineRuntime(
        graph,
        registry=_runtime_registry(),
        run_dir=tmp_path / "error",
        delegate_cli=True,
    ).run({"cli.argv": []})
    error_streams = capsys.readouterr()

    assert error_result.get("cli.exit_code")["value"] == 2
    assert error_streams.out == ""
    assert "usage: delegate-business" in error_streams.err
    assert "--required" in error_streams.err


@pytest.mark.parametrize(
    "node_type",
    ["delegate.bool_exit", "delegate.string_exit", "delegate.negative_exit", "delegate.large_exit"],
)
def test_authorized_node_rejects_invalid_system_exit_codes(tmp_path, node_type) -> None:
    runtime = PipelineRuntime(
        _exit_graph(node_type),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(PipelineRuntimeError, match="integer code from 0 to 255"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "integer code from 0 to 255" in runtime.trace.exception


def test_unauthorized_node_system_exit_is_runtime_failure(tmp_path) -> None:
    runtime = PipelineRuntime(
        _exit_graph("delegate.unauthorized_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )
    with pytest.raises(PipelineRuntimeError, match="cannot control delegate CLI exit"):
        runtime.run({"cli.argv": []})


def test_runtime_plugin_system_exit_becomes_delegate_result(tmp_path) -> None:
    class ExitPlugin:
        def before_run(self, initial):
            raise SystemExit(9)

    plugins = PluginRegistry()
    plugins.register(ExitPlugin(), plugin_type="runtime", name="exit-plugin")
    runtime = PipelineRuntime(
        _exit_graph("delegate.authorized_exit"),
        registry=_runtime_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path,
        delegate_cli=True,
    )
    result = runtime.run({"cli.argv": []})
    assert result.get("cli.exit_code")["value"] == 9
    assert result.get("cli.exit_code")["source_node"] == "plugin:exit-plugin"


def test_normal_runtime_plugin_system_exit_is_pipeline_failure(tmp_path) -> None:
    class ExitPlugin:
        def before_run(self, initial):
            raise SystemExit(9)

    plugins = PluginRegistry()
    plugins.register(ExitPlugin(), plugin_type="runtime", name="exit-plugin")
    runtime = PipelineRuntime(
        _exit_graph("delegate.authorized_exit"),
        registry=_runtime_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path,
    )

    with pytest.raises(PipelineRuntimeError, match="runtime plugin 'exit-plugin'.*SystemExit outside delegate CLI mode"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "SystemExit outside delegate CLI mode" in runtime.trace.exception


def test_async_authorized_system_exit_stops_outer_runtime(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "exit",
                        "type_used": "delegate.authorized_exit",
                        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                    },
                    {"id": "end", "type_used": "delegate.exit_end"},
                ],
                "edges": [["start", "exit"], ["exit", "end"]],
            }
        }
    )

    result = PipelineRuntime(graph, registry=_runtime_registry(), run_dir=tmp_path, delegate_cli=True).run(
        {"cli.argv": ["--help"]}
    )

    assert result.get("cli.exit_code")["value"] == 2
    assert result.get("runtime.stop_reason") == "business_exit"


def test_normal_runtime_async_node_system_exit_is_pipeline_failure(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "exit",
                        "type_used": "delegate.authorized_exit",
                        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                    },
                    {"id": "end", "type_used": "delegate.exit_end"},
                ],
                "edges": [["start", "exit"], ["exit", "end"]],
            }
        }
    )
    runtime = PipelineRuntime(graph, registry=_runtime_registry(), run_dir=tmp_path)

    with pytest.raises(PipelineRuntimeError, match="attempted SystemExit outside delegate CLI mode"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "SystemExit outside delegate CLI mode" in runtime.trace.exception


@pytest.mark.parametrize("async_mode", ["detached", "result_key"])
def test_outer_business_exit_prioritizes_pending_framework_failure_and_records_trace(
    tmp_path,
    async_mode,
) -> None:
    failures = []

    class FailurePlugin:
        def run_failed(self, result, trace, failure):
            failures.append((trace["stop_reason"], trace["exception"], failure))

    plugins = PluginRegistry()
    plugins.register(FailurePlugin(), plugin_type="runtime", name="failure-plugin")
    runtime = PipelineRuntime(
        _exit_with_pending_graph(
            pending_node_type="delegate.detached_failure",
            async_mode=async_mode,
        ),
        registry=_runtime_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(RuntimeError, match="late detached failure"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "late detached failure" in runtime.trace.exception
    assert failures == [
        ("node_failed", runtime.trace.exception, runtime.trace.exception),
    ]


def test_existing_framework_failure_is_not_replaced_by_detached_business_exit(tmp_path) -> None:
    failures = []

    class FailurePlugin:
        def run_failed(self, result, trace, failure):
            failures.append(failure)

    plugins = PluginRegistry()
    plugins.register(FailurePlugin(), plugin_type="runtime", name="failure-plugin")
    runtime = PipelineRuntime(
        _exit_with_pending_graph(
            pending_node_type="delegate.detached_exit",
            async_mode="detached",
            exit_node_type="delegate.unauthorized_exit",
        ),
        registry=_runtime_registry(),
        plugin_registry=plugins,
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(PipelineRuntimeError, match="cannot control delegate CLI exit"):
        runtime.run({"cli.argv": []})

    assert runtime.trace.stop_reason == "node_failed"
    assert "cannot control delegate CLI exit" in runtime.trace.exception
    assert "cannot replace" not in runtime.trace.exception
    assert failures == [runtime.trace.exception]


def test_nested_authorized_system_exit_stops_outer_runtime(tmp_path) -> None:
    inner = {
        "type_key": "delegate.inner",
        "display_name": "Delegate inner",
        "description": "Runs the delegated exit inside a nodeset.",
        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
        "pipeline": {
            "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
            "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
            "nodes": [
                {"id": "inner_start", "type_used": "delegate.start"},
                {"id": "inner_exit", "type_used": "delegate.authorized_exit"},
            ],
            "edges": [["inner_start", "inner_exit"]],
        },
    }
    graph = parse_graph_config(
        {
            "nodesets": [inner],
            "pipeline": {
                "inputs": [{"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start"},
                    {
                        "id": "inner",
                        "type_used": "delegate.inner",
                        "requires": [{"type": "cli.argv", "cardinality": "exactly_one", "display_name": "CLI argv"}],
                        "provides": [{"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}],
                    },
                ],
                "edges": [["start", "inner"]],
            },
        }
    )

    result = PipelineRuntime(graph, registry=_runtime_registry(), run_dir=tmp_path, delegate_cli=True).run(
        {"cli.argv": ["--help"]}
    )

    assert result.get("cli.exit_code")["value"] == 2
    assert result.get("cli.exit_code")["source_node"] == "inner_exit"
    assert result.get("runtime.stop_reason") == "business_exit"


@pytest.mark.parametrize("async_mode", ["detached", "result_key"])
def test_nested_business_exit_prioritizes_pending_framework_failure(tmp_path, async_mode) -> None:
    runtime = PipelineRuntime(
        _nested_exit_with_pending_graph(
            pending_node_type="delegate.detached_failure",
            async_mode=async_mode,
        ),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(RuntimeError, match="late detached failure"):
        runtime.run({"cli.argv": []})

    child_trace = runtime._nodeset_runtimes["inner"].trace
    assert child_trace.stop_reason == "node_failed"
    assert "late detached failure" in child_trace.exception


def test_nested_business_exit_propagates_after_successful_pending_result(tmp_path) -> None:
    runtime = PipelineRuntime(
        _nested_exit_with_pending_graph(
            pending_node_type="delegate.successful_side",
            async_mode="result_key",
        ),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    result = runtime.run({"cli.argv": []})

    assert result.get("cli.exit_code")["value"] == 2
    assert result.get("cli.exit_code")["source_node"] == "inner_exit"
    child_trace = runtime._nodeset_runtimes["inner"].trace
    assert child_trace.stop_reason == "business_exit"
    assert child_trace.exception == ""


@pytest.mark.parametrize(
    ("second_node_type", "error_type", "message"),
    [
        ("delegate.second_detached_exit", PipelineRuntimeError, "multiple business exits"),
        ("delegate.detached_failure", RuntimeError, "late detached failure"),
    ],
)
def test_delegate_cli_drains_all_detached_results_before_deciding_exit(
    tmp_path,
    second_node_type,
    error_type,
    message,
) -> None:
    runtime = PipelineRuntime(
        _multiple_detached_graph(second_node_type),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(error_type, match=message):
        runtime.run({"cli.argv": []})


@pytest.mark.parametrize(
    ("second_node_type", "error_type", "message"),
    [
        ("delegate.second_detached_exit", PipelineRuntimeError, "multiple business exits"),
        ("delegate.detached_failure", RuntimeError, "late detached failure"),
    ],
)
def test_delegate_cli_drains_parallel_result_futures_before_deciding_exit(
    tmp_path,
    second_node_type,
    error_type,
    message,
) -> None:
    runtime = PipelineRuntime(
        _parallel_result_graph(second_node_type),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(error_type, match=message):
        runtime.run({"cli.argv": []})


def test_delegate_cli_observes_unconsumed_result_key_business_exit(tmp_path) -> None:
    runtime = PipelineRuntime(
        _unconsumed_result_graph("delegate.detached_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    result = runtime.run({"cli.argv": []})

    assert result.get("cli.exit_code")["value"] == 11
    assert result.get("runtime.stop_reason") == "business_exit"


def test_delegate_cli_observes_unconsumed_result_key_failure(tmp_path) -> None:
    runtime = PipelineRuntime(
        _unconsumed_result_graph("delegate.detached_failure"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(RuntimeError, match="late detached failure"):
        runtime.run({"cli.argv": []})


def test_delegate_cli_rejects_multiple_unconsumed_result_key_business_exits(tmp_path) -> None:
    runtime = PipelineRuntime(
        _unconsumed_result_graph("delegate.detached_exit", "delegate.second_detached_exit"),
        registry=_runtime_registry(),
        run_dir=tmp_path,
        delegate_cli=True,
    )

    with pytest.raises(PipelineRuntimeError, match="multiple business exits"):
        runtime.run({"cli.argv": []})
