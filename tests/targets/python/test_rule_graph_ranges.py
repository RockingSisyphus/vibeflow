"""Real Target execution uses disjoint ranges and ordinary Records dependencies."""
from dataclasses import replace
import pytest
from tests.targets.python.test_rule_sessions import _registry
from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleRelation, RuleRecord, RuleResult, RulesetDescriptor
from vibeflow.targets.python.quality.workflow.validation import _HealthValidationState
from vibeflow.targets.python.quality.workflow.rule_phase import execute_workflow_rules


def definition(key, graph):
    return NodesetSpec(key,key,key,(),(),graph)


@pytest.mark.parametrize("scope", ["current_graph", "effective_subtree"])
def test_nested_ranges_have_no_overlapping_responsibility_and_keep_global_background(tmp_path, scope):
    analysis = RuleDescriptor("test.analysis", outputs={"graphs":"test.graphs"})
    check = RuleDescriptor("test.check", inputs={"graphs":"test.graphs"})
    selected = RulesetDescriptor("test.range", workflow_default=True, graph_scope=scope,
        calls=(RuleCall("analysis",rule_id=analysis.id),RuleCall("check",rule_id=check.id)),
        relations=(RuleRelation("check","analysis","requires",bindings={"graphs":"graphs"}),),
        entrypoints={"import":("check",)})
    registry = _registry(tmp_path, (analysis,check), selected)
    child = definition("child",GraphConfig((NodeSpec("leaf","test.leaf"),)))
    middle = definition("middle",GraphConfig((NodeSpec("inner","child"),),nodesets={"child":child}))
    boundary = definition("boundary",replace(middle.graph,rulesets=()))
    graph = GraphConfig((NodeSpec("first","middle"),NodeSpec("second","middle"),NodeSpec("boundary","boundary")),
        nodesets={"child":child,"middle":middle,"boundary":boundary})
    observed, analyzed = [], []
    def analyze(context, inputs, params):
        assert len(context.require("global_graph").nodesets["child"].graph.nodes) == 1
        assert all(not item.graph.nodes for item in context.require("graph").nodesets.values())
        paths = tuple(item["call_path"] for item in context.require("graphs"))
        analyzed.append(paths)
        return RuleResult({"graphs":RuleRecord("test.graphs",paths)})
    def consume(context, inputs, params):
        observed.extend(tuple(value) for value in inputs["graphs"].value)
        return RuleResult()
    registry.rule_handler_loader = lambda _: {analysis.id:analyze, check.id:consume}
    state = _HealthValidationState()
    execute_workflow_rules(graph,state,registry=registry,phase="import")
    assert not state.errors
    assert observed == [(),("first",),("first","inner"),("second",),("second","inner")]
    assert len(set(observed)) == len(observed)
    assert len(analyzed) == (5 if scope == "current_graph" else 1)
    assert state.rule_executions[0].scope["boundaries"] == (("boundary",),)


def test_shared_nodeset_width_analysis_reports_all_affected_call_paths(tmp_path):
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    registry = _registry(tmp_path,(),RulesetDescriptor("test.empty"))
    wide = definition("wide",GraphConfig(tuple(NodeSpec(f"leaf_{i}","test.leaf",rulesets=()) for i in range(11))))
    graph = GraphConfig((NodeSpec("first","wide"),NodeSpec("second","wide")),nodesets={"wide":wide})
    report = validate_graph_health(graph,registry=registry)
    finding = next(item for item in report.warnings if item.rule_id == "NODESET.SMELL.TOO_WIDE")
    assert finding.details["call_paths"] == (("first",),("second",))
