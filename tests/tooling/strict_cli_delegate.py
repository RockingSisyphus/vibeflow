from __future__ import annotations
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from tests.fixtures.support.declarations import node_declaration, configured_declaration, native_registry

import sys
from pathlib import Path

import pytest

from vibeflow.tooling.application.python.cli import main
from vibeflow.tooling.application.python.cli.delegate_cli import extract_delegate_cli_exit_code, validate_delegate_cli_graph_contract
from vibeflow.core.contracts import DataEnvelope, DataProvider, DataRequirement, RunResult
from vibeflow.core import HealthReport
from vibeflow.tooling.application.python.diagnostics import emit_core_diagnostic
from vibeflow.tooling.application.python.runner import CheckedRunResult
from vibeflow.tooling.project.graph_config import parse_graph_config

from vibeflow.targets.python.project.plugins import PluginRegistry
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError


@pytest.fixture(autouse=True)
def _stub_delegate_workspace_loader(monkeypatch):
    monkeypatch.setattr(
        "vibeflow.tooling.application.python.cli._load_workspace_for_cli",
        lambda path: object(),
    )


_StartNode_DECLARATION = node_declaration(NodeDescriptor('delegate.start', 'Start', 'Starts delegate test.', '0.1.0', 'terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class _StartNode:

    def run_pure(self, inputs, params):
        return {}


_AuthorizedExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.authorized_exit', 'Authorized exit', 'Exits delegated CLI.', '0.1.0', 'io', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('cli.argv', 'exactly_one', display_name='cli.argv'),), provides=(DataProvider('cli.exit_code', 'cli.exit_code', display_name='cli.exit_code'),), input_semantics={'cli.argv': ('business argv',)}, output_semantics={'cli.exit_code': ('business exit code',)}, examples=({'inputs': {'cli.argv': {'key': 'cli.argv', 'type': 'cli.argv', 'value': [], 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.io",))

class _AuthorizedExitNode:

    def run_pure(self, inputs, params):
        raise SystemExit(2)


_UnauthorizedExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.unauthorized_exit', 'Unauthorized exit', 'Cannot exit delegated CLI.', '0.1.0', 'process', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.process",))

class _UnauthorizedExitNode(_AuthorizedExitNode):
    pass


_NoneExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.none_exit', 'None exit', 'Exits delegated CLI with the default success code.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _NoneExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit(None)


_BoolExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.bool_exit', 'Bool exit', 'Attempts an invalid boolean CLI exit.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _BoolExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit(True)


_NegativeExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.negative_exit', 'Negative exit', 'Attempts an invalid negative CLI exit.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _NegativeExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit(-1)


_LargeExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.large_exit', 'Large exit', 'Attempts an invalid oversized CLI exit.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _LargeExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit(256)


_StringExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.string_exit', 'String exit', 'Attempts an invalid string CLI exit.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _StringExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit("invalid")


_ArgparseExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.argparse_exit', 'Argparse exit', 'Exercises real argparse exits.', '0.1.0', 'io', contract=NodeContractDescriptor()), _AuthorizedExitNode_DECLARATION.contract, rulesets=("vibeflow.io",))

class _ArgparseExitNode(_AuthorizedExitNode):

    def run_pure(self, inputs, params):
        import argparse

        parser = argparse.ArgumentParser(prog="delegate-business")
        parser.add_argument("--required", required=True)
        parser.parse_args(list(inputs["cli.argv"]["value"]))
        return {"cli.exit_code": 0}


_DetachedExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.detached_exit', 'Detached exit', 'Exits from a detached task.', '0.1.0', 'io', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('async.first', 'async.first', display_name='First async result'),), output_semantics={'async.first': ('first delegated async result',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.io",))

class _DetachedExitNode:

    def run_pure(self, inputs, params):
        raise SystemExit(11)


_SecondDetachedExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.second_detached_exit', 'Second detached exit', 'Exits from another detached task.', '0.1.0', 'io', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('async.second', 'async.second', display_name='Second async result'),), output_semantics={'async.second': ('second delegated async result',)}), rulesets=("vibeflow.io",))

class _SecondDetachedExitNode(_DetachedExitNode):

    def run_pure(self, inputs, params):
        raise SystemExit(12)


_DetachedFailureNode_DECLARATION = node_declaration(NodeDescriptor('delegate.detached_failure', 'Detached failure', 'Fails from a detached task.', '0.1.0', 'process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('async.pending', 'async.pending', display_name='Pending async result'),), output_semantics={'async.pending': ('pending task result used by the async failure fixture',)}), rulesets=("vibeflow.process",))

class _DetachedFailureNode(_DetachedExitNode):

    def run_pure(self, inputs, params):
        raise RuntimeError("late detached failure")


_SuccessfulSideNode_DECLARATION = node_declaration(NodeDescriptor('delegate.successful_side', 'Successful side', 'Completes an async side task.', '0.1.0', 'process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('async.pending', 'async.pending', display_name='async.pending'),), output_semantics={'async.pending': ('completed side result',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class _SuccessfulSideNode:

    def run_pure(self, inputs, params):
        return {"async.pending": "done"}


_ArgvGateNode_DECLARATION = node_declaration(NodeDescriptor('delegate.argv_gate', 'Argv gate', 'Forwards CLI arguments after pending work starts.', '0.1.0', 'process', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('cli.argv', 'exactly_one', display_name='CLI argv'),), provides=(DataProvider('cli.argv.gated', 'cli.argv', display_name='Forwarded CLI argv'),), input_semantics={'cli.argv': ('business argv',)}, output_semantics={'cli.argv.gated': ('forwarded business argv',)}), rulesets=("vibeflow.process",))

class _ArgvGateNode:

    def run_pure(self, inputs, params):
        return {"cli.argv.gated": inputs["cli.argv"]["value"]}


_ParallelJoinExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.parallel_join_exit', 'Parallel exit join', 'Joins two delegated exit results.', '0.1.0', 'terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('async.first', 'exactly_one', display_name='First async result'), DataRequirement('async.second', 'exactly_one', display_name='Second async result')), input_semantics={'async.first': ('first delegated async result',), 'async.second': ('second delegated async result',)}), rulesets=("vibeflow.process",))

class _ParallelJoinExitNode:

    def run_pure(self, inputs, params):
        return {}


_ParallelJoinFailureNode_DECLARATION = node_declaration(NodeDescriptor('delegate.parallel_join_failure', 'Parallel failure join', 'Joins an exit result with a failing result.', '0.1.0', 'terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('async.first', 'exactly_one', display_name='First async result'), DataRequirement('async.pending', 'exactly_one', display_name='Pending async result')), input_semantics={'async.first': ('first delegated async result',), 'async.pending': ('pending async result',)}), rulesets=("vibeflow.process",))

class _ParallelJoinFailureNode:

    def run_pure(self, inputs, params):
        return {}


_NormalExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.normal_exit', 'Normal exit', 'Returns a normal delegated exit.', '0.1.0', 'process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider('cli.exit_code', 'cli.exit_code', display_name='cli.exit_code'),), output_semantics={'cli.exit_code': ('business exit code',)}, examples=({'inputs': {}, 'params': {}},)), rulesets=("vibeflow.process",))

class _NormalExitNode:

    def run_pure(self, inputs, params):
        return {"cli.exit_code": 0}


_AsyncDiagnosticExitNode_DECLARATION = node_declaration(NodeDescriptor('delegate.async_diagnostic_exit', 'Async diagnostic exit', 'Emits a core diagnostic from an async worker.', '0.1.0', 'process', contract=NodeContractDescriptor()), _NormalExitNode_DECLARATION.contract, rulesets=("vibeflow.process",))

class _AsyncDiagnosticExitNode(_NormalExitNode):

    def run_pure(self, inputs, params):
        emit_core_diagnostic("ASYNC-CORE-DIAGNOSTIC")
        return {"cli.exit_code": 0}


_ExitEndNode_DECLARATION = node_declaration(NodeDescriptor('delegate.exit_end', 'Exit end', 'Consumes a delegated exit.', '0.1.0', 'terminal', contract=NodeContractDescriptor()), NodeContractDescriptor(requires=(DataRequirement('cli.exit_code', 'exactly_one', display_name='cli.exit_code'),), input_semantics={'cli.exit_code': ('business exit code',)}, examples=({'inputs': {'cli.exit_code': {'key': 'cli.exit_code', 'type': 'cli.exit_code', 'value': 0, 'source_node': 'example'}}, 'params': {}},)), rulesets=("vibeflow.process",))

class _ExitEndNode:

    def run_pure(self, inputs, params):
        return {}


def _runtime_registry() -> NodeRegistry:
    registry = native_registry()
    registry.register(configured_declaration(_StartNode_DECLARATION, {}, {}), _StartNode)
    registry.register(configured_declaration(_AuthorizedExitNode_DECLARATION, {}, {}), _AuthorizedExitNode)
    registry.register(_UnauthorizedExitNode_DECLARATION, _UnauthorizedExitNode)
    registry.register(_NoneExitNode_DECLARATION, _NoneExitNode)
    registry.register(_BoolExitNode_DECLARATION, _BoolExitNode)
    registry.register(_NegativeExitNode_DECLARATION, _NegativeExitNode)
    registry.register(_LargeExitNode_DECLARATION, _LargeExitNode)
    registry.register(_StringExitNode_DECLARATION, _StringExitNode)
    registry.register(_ArgparseExitNode_DECLARATION, _ArgparseExitNode)
    registry.register(configured_declaration(_DetachedExitNode_DECLARATION, {}, {}), _DetachedExitNode)
    registry.register(configured_declaration(_SecondDetachedExitNode_DECLARATION, {}, {}), _SecondDetachedExitNode)
    registry.register(configured_declaration(_DetachedFailureNode_DECLARATION, {}, {}), _DetachedFailureNode)
    registry.register(configured_declaration(_SuccessfulSideNode_DECLARATION, {}, {}), _SuccessfulSideNode)
    registry.register(configured_declaration(_ArgvGateNode_DECLARATION, {}, {}), _ArgvGateNode)
    registry.register(configured_declaration(_ParallelJoinExitNode_DECLARATION, {}, {}), _ParallelJoinExitNode)
    registry.register(configured_declaration(_ParallelJoinFailureNode_DECLARATION, {}, {}), _ParallelJoinFailureNode)
    registry.register(configured_declaration(_NormalExitNode_DECLARATION, {}, {}), _NormalExitNode)
    registry.register(_AsyncDiagnosticExitNode_DECLARATION, _AsyncDiagnosticExitNode)
    registry.register(configured_declaration(_ExitEndNode_DECLARATION, {}, {}), _ExitEndNode)
    return registry


def _exit_graph(node_type: str):
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {"id": "exit", "type_used": node_type, "display_name": "Exit", "description": "Exercises exit in the delegated CLI test workflow."},
                ],
                "edges": [["start", "exit"]],
            }
        }
    )


def _graph(*, include_argv: bool = True, exit_cardinality: str = "exactly_one"):
    inputs = []
    if include_argv:
        inputs.append({"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv", "required": False})
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
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                        "status": "planned",
                        "flow_kind": "process",
                        "requires": [],
                    }
                ],
            }
        }
    )


def _multiple_detached_graph(second_node_type: str):
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {"id": "first", "type_used": "delegate.detached_exit", "async": "detached", "display_name": "First", "description": "Exercises first in the delegated CLI test workflow."},
                    {"id": "second", "type_used": second_node_type, "async": "detached", "display_name": "Second", "description": "Exercises second in the delegated CLI test workflow."},
                    {
                        "id": "normal_exit",
                        "type_used": "delegate.normal_exit",
                        "display_name": "Normal Exit",
                        "description": "Exercises normal_exit in the delegated CLI test workflow.",
                    },
                    {"id": "end", "type_used": "delegate.exit_end", "display_name": "End", "description": "Exercises end in the delegated CLI test workflow."},
                ],
                "edges": [["start", "first"], ["first", "second"], ["second", "normal_exit"], ["normal_exit", "end"]],
            }
        }
    )


def _parallel_result_graph(second_node_type: str):
    second_result_key = "async.pending" if second_node_type == "delegate.detached_failure" else "async.second"
    join_type = "delegate.parallel_join_failure" if second_node_type == "delegate.detached_failure" else "delegate.parallel_join_exit"
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "first",
                        "type_used": "delegate.detached_exit",
                        "async": "result_key",
                        "result_key": "async.first",
                        "display_name": "First",
                        "description": "Exercises first in the delegated CLI test workflow.",
                    },
                    {
                        "id": "second",
                        "type_used": second_node_type,
                        "async": "result_key",
                        "result_key": second_result_key,
                        "display_name": "Second",
                        "description": "Exercises second in the delegated CLI test workflow.",
                    },
                    {
                        "id": "join",
                        "type_used": join_type,
                        "display_name": "Join",
                        "description": "Exercises join in the delegated CLI test workflow.",
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "output",
                        "type_used": "delegate.async_diagnostic_exit",
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                    },
                    {"id": "end", "type_used": "delegate.exit_end", "display_name": "End", "description": "Exercises end in the delegated CLI test workflow."},
                ],
                "edges": [["start", "output"], ["output", "end"]],
            }
        }
    )


def _unconsumed_result_graph(*node_types: str):
    result_keys = {
        "delegate.detached_exit": "async.first",
        "delegate.second_detached_exit": "async.second",
        "delegate.detached_failure": "async.pending",
    }
    async_nodes = [
        {
            "id": f"side_{index}",
            "type_used": node_type,
            "async": "result_key",
            "result_key": result_keys[node_type],
            "display_name": f"Side {index}",
            "description": f"Exercises side_{index} in the delegated CLI test workflow.",
        }
        for index, node_type in enumerate(node_types)
    ]
    return parse_graph_config(
        {
            "pipeline": {
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    *async_nodes,
                    {
                        "id": "normal_exit",
                        "type_used": "delegate.normal_exit",
                        "display_name": "Normal Exit",
                        "description": "Exercises normal_exit in the delegated CLI test workflow.",
                    },
                    {"id": "end", "type_used": "delegate.exit_end", "display_name": "End", "description": "Exercises end in the delegated CLI test workflow."},
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
        "display_name": "A Pending",
        "description": "Exercises a_pending in the delegated CLI test workflow.",
    }
    if async_mode == "result_key":
        pending_node.update(
            {
                "result_key": "async.pending",
            }
        )
    return {
        "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
        "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
        "nodes": [
            {"id": "inner_start", "type_used": "delegate.start", "display_name": "Inner Start", "description": "Exercises inner_start in the delegated CLI test workflow."},
            pending_node,
            {"id": "gate", "type_used": "delegate.argv_gate", "display_name": "Gate", "description": "Exercises gate in the delegated CLI test workflow."},
            {"id": "inner_exit", "type_used": exit_node_type, "display_name": "Inner Exit", "description": "Exercises inner_exit in the delegated CLI test workflow."},
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "inner",
                        "type_used": "delegate.inner_pending",
                        "display_name": "Inner",
                        "description": "Exercises inner in the delegated CLI test workflow.",
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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)
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
    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)
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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)
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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", run_async_graph)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)
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
    lines = [line for line in log.splitlines() if not line.startswith("STATE ")]
    assert len(lines) == 3
    assert "run_id=run\\r\\nid config=project/config\\r\\nmain.jsonc" in lines[0]
    assert "runs\\r\\nroot/run\\r\\nid" in lines[1]


def test_delegate_cli_run_directory_race_does_not_overwrite_foreign_log(monkeypatch, tmp_path, capsys) -> None:
    from vibeflow.tooling.application.python.runner import _prepare_run_dir as original_prepare_run_dir

    def race_for_run_directory(run_root, run_id):
        run_dir = Path(run_root) / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "vibeflow.log").write_text("OTHER-RUN\n", encoding="utf-8")
        return original_prepare_run_dir(run_root, run_id)

    monkeypatch.setattr("vibeflow.tooling.application.python.runner._prepare_run_dir", race_for_run_directory)

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

    monkeypatch.setattr("vibeflow.tooling.application.python.workspace_service.run_workspace_checked", fake_run_workspace_checked)

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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [{"id": "output", "type_used": "delegate.output", "provides": providers, "display_name": "Output", "description": "Exercises output in the delegated CLI test workflow.", "status": "planned", "flow_kind": "process", "requires": []}],
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit"}
                        ],
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                        "status": "planned",
                        "flow_kind": "process",
                        "requires": [],
                    },
                    {
                        "id": "shadow",
                        "type_used": "delegate.shadow",
                        "provides": [
                            {"key": "cli.exit_code", "type": "wrong", "display_name": "Shadow exit"}
                        ],
                        "display_name": "Shadow",
                        "description": "Exercises shadow in the delegated CLI test workflow.",
                        "status": "planned",
                        "flow_kind": "process",
                        "requires": [],
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
        [{"key": "cli.argv", "type": "wrong", "display_name": "Wrong argv", "required": False}],
        [{"key": "wrong", "type": "cli.argv", "display_name": "Wrong argv", "required": False}],
        [
            {"key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv", "required": False},
            {"key": "wrong", "type": "cli.argv", "display_name": "Shadow argv", "required": False},
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
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                        "status": "planned",
                        "flow_kind": "process",
                        "requires": [],
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {
                        "id": "output",
                        "type_used": "delegate.output",
                        "provides": [
                            {"key": "cli.exit_code", "type": "cli.exit_code", "display_name": "CLI exit code"}
                        ],
                        "async": "detached",
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                        "status": "planned",
                        "flow_kind": "process",
                        "requires": [],
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "output",
                        "type_used": "delegate.normal_exit",
                        "display_name": "Output",
                        "description": "Exercises output in the delegated CLI test workflow.",
                    },
                    {
                        "id": "end",
                        "type_used": "delegate.exit_end",
                        "display_name": "End",
                        "description": "Exercises end in the delegated CLI test workflow.",
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "exit",
                        "type_used": "delegate.argparse_exit",
                        "display_name": "Exit",
                        "description": "Exercises exit in the delegated CLI test workflow.",
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "exit",
                        "type_used": "delegate.authorized_exit",
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                        "display_name": "Exit",
                        "description": "Exercises exit in the delegated CLI test workflow.",
                    },
                    {"id": "end", "type_used": "delegate.exit_end", "display_name": "End", "description": "Exercises end in the delegated CLI test workflow."},
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
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "exit",
                        "type_used": "delegate.authorized_exit",
                        "async": "result_key",
                        "result_key": "cli.exit_code",
                        "display_name": "Exit",
                        "description": "Exercises exit in the delegated CLI test workflow.",
                    },
                    {"id": "end", "type_used": "delegate.exit_end", "display_name": "End", "description": "Exercises end in the delegated CLI test workflow."},
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
            "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
            "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
            "nodes": [
                {"id": "inner_start", "type_used": "delegate.start", "display_name": "Inner Start", "description": "Exercises inner_start in the delegated CLI test workflow."},
                {"id": "inner_exit", "type_used": "delegate.authorized_exit", "display_name": "Inner Exit", "description": "Exercises inner_exit in the delegated CLI test workflow."},
            ],
            "edges": [["inner_start", "inner_exit"]],
        },
    }
    graph = parse_graph_config(
        {
            "nodesets": [inner],
            "pipeline": {
                "inputs": [{"required": True, "key": "cli.argv", "type": "cli.argv", "display_name": "CLI argv"}],
                "outputs": [{"type": "cli.exit_code", "cardinality": "exactly_one", "display_name": "CLI exit code"}],
                "nodes": [
                    {"id": "start", "type_used": "delegate.start", "display_name": "Start", "description": "Exercises start in the delegated CLI test workflow."},
                    {
                        "id": "inner",
                        "type_used": "delegate.inner",
                        "display_name": "Inner",
                        "description": "Exercises inner in the delegated CLI test workflow.",
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
