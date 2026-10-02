"""Delegate exit authorization comes from actual Rules, not Node identity."""

from types import SimpleNamespace

import pytest

from tests.fixtures.support.declarations import node_declaration
from vibeflow.core.contracts import DataProvider, DataRequirement, PipelineInputSpec, PipelineOutputSpec
from vibeflow.core.flow import EdgeSpec, GraphConfig, NodeSpec
from vibeflow.core.rules import RuleCall, RuleRelation, RulesetDescriptor
from vibeflow.targets.python.project import NodeContract, NodeInfo, NodeRegistry
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
from vibeflow.targets.python.runtime import PipelineRuntime
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def _runtime(tmp_path, *, selection, async_mode, flow_kind="process", delegate_cli=True):
    source = (
        "class StartNode:\n"
        "    def run_pure(self, inputs, params):\n"
        "        return {}\n\n"
        "class ExitNode:\n"
        "    def run_pure(self, inputs, params):\n"
        "        raise SystemExit(7)\n\n"
        "class EndNode:\n"
        "    def run_pure(self, inputs, params):\n"
        "        return {}\n"
    )
    path = tmp_path / "nodes.py"
    path.write_text(source)
    namespace = {}
    exec(compile(source, str(path), "exec"), namespace)
    custom = RulesetDescriptor(
        "test.delegate", calls=(RuleCall("base", ruleset_id="vibeflow.process"),),
        relations=(RuleRelation("$self", "base/effects", "overrides", params={"effect_scope":"terminal"}),),
        entrypoints={"static":("base",), "run":("base",)},
    )
    selected = {"terminal":(custom.id,), "none":("vibeflow.process",), "unconstrained":()}[selection]
    contract = NodeContract(
        requires=(DataRequirement("cli.argv", "exactly_one", display_name="CLI argv"),),
        provides=(DataProvider("cli.exit_code", "cli.exit_code", display_name="CLI exit code"),),
        input_semantics={"cli.argv":("business arguments",)},
        output_semantics={"cli.exit_code":("business status",)},
    )
    descriptor = node_declaration(NodeInfo("test.exit", "Exit", "test", "Ends the delegated application.", "1", flow_kind),
                                  contract, rulesets=selected)
    end = node_declaration(NodeInfo("test.end", "End", "test", "Consumes application status.", "1", "terminal"),
                          NodeContract(requires=(DataRequirement("cli.exit_code", "exactly_one", display_name="CLI exit code"),)), rulesets=())
    registry = NodeRegistry()
    start = node_declaration(NodeInfo("test.start", "Start", "test", "Starts the application.", "1", "terminal"),
                            NodeContract(), rulesets=())
    registry.register(start, namespace["StartNode"])
    registry.register(descriptor, namespace["ExitNode"])
    registry.register(end, namespace["EndNode"])
    registry.source_locations = {"test.start":(path,"StartNode","project",tmp_path), "test.exit":(path,"ExitNode","project",tmp_path), "test.end":(path,"EndNode","project",tmp_path)}
    registry.source_roots = (tmp_path,)
    registry.source_root_ids = {tmp_path:"project"}
    registry.rule_catalogs = (SimpleNamespace(rules=(),rulesets=(custom,)),)
    graph = GraphConfig(
        nodes=(NodeSpec("start","test.start"), NodeSpec("exit","test.exit",async_mode=async_mode,result_key="cli.exit_code" if async_mode else ""),
               NodeSpec("end","test.end")), edges=(EdgeSpec("start","exit"), EdgeSpec("exit","end")),
        inputs=(PipelineInputSpec("cli.argv","cli.argv",display_name="CLI argv"),),
        outputs=(PipelineOutputSpec("cli.exit_code","exactly_one",display_name="CLI exit code"),), rulesets=(),
    )
    rules = execute_python_node_rules(registry,collect_workflow_source_context(registry,graph),phase="run")
    runtime = PipelineRuntime(graph,registry=registry,run_dir=tmp_path / "run",delegate_cli=delegate_cli)
    return runtime, rules


@pytest.mark.parametrize("async_mode",[None,"result_key"])
@pytest.mark.parametrize("selection",["terminal","unconstrained"])
def test_process_can_exit_when_rule_allows_or_check_is_unselected(tmp_path,async_mode,selection):
    runtime, rules = _runtime(tmp_path,selection=selection,async_mode=async_mode)
    assert runtime._plan.frame("exit").flow_kind == "process"
    assert runtime._plan.frame("exit").effect_scope == selection
    assert not any(item.severity == "error" for item in rules.findings)
    if selection == "terminal":
        records = rules.call_effect_policies[("pipeline","exit")]
        assert records[0]["value"]["effect_scope"] == "terminal"
        assert records[0]["definition_id"] == "vibeflow.no_side_effects"
    else:
        assert rules.executions == ()
    result = runtime.run({"cli.argv":[]})
    assert result.get("cli.exit_code")["value"] == 7
    assert runtime.trace.stop_reason == "business_exit"
    assert runtime.trace.exception == ""


@pytest.mark.parametrize("async_mode",[None,"result_key"])
@pytest.mark.parametrize("flow_kind",["process","io"])
def test_selected_none_rejects_exit_independently_of_flow_kind(tmp_path,async_mode,flow_kind):
    runtime, rules = _runtime(tmp_path,selection="none",async_mode=async_mode,flow_kind=flow_kind)
    assert runtime._plan.frame("exit").effect_scope == "none"
    assert any(item.severity == "error" and item.definition_id == "vibeflow.no_side_effects" for item in rules.findings)
    with pytest.raises(PipelineRuntimeError,match="effect_scope 'none'.*cannot control delegate CLI exit"):
        runtime.run({"cli.argv":[]})
    assert runtime.trace.stop_reason == "node_failed"


def test_rule_permission_does_not_change_non_delegate_execution_protocol(tmp_path):
    runtime, _ = _runtime(tmp_path,selection="terminal",async_mode=None,delegate_cli=False)
    with pytest.raises(PipelineRuntimeError,match="outside delegate CLI mode"):
        runtime.run({"cli.argv":[]})
