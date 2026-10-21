"""Replacement reaches source checks, first binding and actual call policies."""
from dataclasses import replace

from tests.targets.python.test_rule_sessions import _registry
from vibeflow.core.flow import GraphConfig, NodeCallSpec
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleResult, RulesetDescriptor
from vibeflow.targets.python.project.check_session import begin_python_check, end_python_check
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules, review_python_node_binding
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def test_dynamic_defaults_empty_and_binding_do_not_resurrect_default(tmp_path):
    rule = RuleDescriptor("test.default")
    default = RulesetDescriptor("test.default", calls=(RuleCall("check", rule_id=rule.id),), entrypoints={"import": ("check",), "static": ("check",)})
    registry = _registry(tmp_path, (rule,), default)
    begin_python_check(registry)
    graph = GraphConfig((NodeCallSpec("default", "test.leaf"), NodeCallSpec("dynamic", "test.leaf", rulesets=({"rule_id": "test.dynamic"},)),
        NodeCallSpec("disabled", "test.leaf", rulesets=())), rulesets=())
    registry.rule_catalogs[-1].rules = (rule, RuleDescriptor("test.dynamic"))
    seen = []
    registry.rule_handler_loader = lambda _: {key: (lambda context, inputs, params, key=key: seen.append((key, context.subject["call_id"])) or RuleResult())
        for key in ("test.default", "test.dynamic")}
    sources = collect_workflow_source_context(registry, graph)
    report = execute_python_node_rules(registry, sources, phase="import")
    assert not report.findings
    assert seen == [("test.default", "default"), ("test.dynamic", "dynamic")]
    review_python_node_binding(registry, sources, "test.leaf")
    assert len(seen) == 2
    end_python_check(registry)


def test_same_file_other_node_is_hidden_and_real_helper_is_visible(tmp_path):
    rule = RuleDescriptor("test.inspect")
    selection = RulesetDescriptor("test.inspect", calls=(RuleCall("inspect", rule_id=rule.id),))
    registry = _registry(tmp_path, (rule,), selection)
    path = tmp_path / "nodes.py"
    path.write_text('def helper(value):\n    return value + 1\nclass Leaf:\n    def run_pure(self, inputs, params):\n        return helper(1)\nclass Secret:\n    def run_pure(self, inputs, params):\n        return "OTHER_NODE_SECRET"\n')
    registry.register(replace(registry.descriptor("test.leaf"), id="test.secret", rulesets=()))
    registry.source_locations["test.secret"] = (path, "Secret", "project", tmp_path)
    sources = collect_workflow_source_context(registry, GraphConfig((NodeCallSpec("leaf", "test.leaf"), NodeCallSpec("secret", "test.secret")), rulesets=()))
    seen = []
    def inspect(context, inputs, params):
        local = context.require("source_context")
        assert "node_definitions" not in context.facts and "graph" not in context.facts
        assert [node.definition_id for node in local.nodes] == ["test.leaf"]
        assert local.calls == ()
        assert "OTHER_NODE_SECRET" not in local.files[0].text
        assert local.symbol(str(path), "Secret") is None
        assert local.symbol(str(path), "helper") is not None
        assert local.symbol(str(path), "Leaf").line == 3
        seen.append(context.subject["call_id"])
        return RuleResult()
    report = execute_python_node_rules(registry, sources, extra_handlers={rule.id: inspect})
    assert not report.findings and seen == ["leaf"]


def test_actual_runtime_first_import_uses_workflow_call_choices(tmp_path):
    from vibeflow.targets.python.runtime.engine import PipelineRuntime
    from vibeflow.tooling.application.python.project.declarations import _bind_node
    rule = RuleDescriptor("test.block")
    default = RulesetDescriptor("test.block", calls=(RuleCall("block", rule_id=rule.id),), entrypoints={"import":("block",)})
    registry = _registry(tmp_path, (rule,), default)
    seen = []
    registry.rule_handler_loader = lambda _: {rule.id:lambda *_: seen.append("default") or RuleResult(state="failed")}
    registry.register(registry.descriptor("test.leaf"), loader=lambda:_bind_node(registry,"test.leaf",(tmp_path,)), overwrite=True)
    runtime = PipelineRuntime(GraphConfig((NodeCallSpec("allowed", "test.leaf", rulesets=()),), rulesets=()), registry=registry, run_dir=tmp_path / "run")
    assert runtime.run().get("runtime.exception") == ""
    assert seen == []


def test_same_line_source_and_inherited_implementation_share_one_boundary(tmp_path):
    import ast
    rule = RuleDescriptor("test.inspect")
    selected = RulesetDescriptor("test.inspect", calls=(RuleCall("inspect", rule_id=rule.id),))
    registry = _registry(tmp_path, (rule,), selected)
    path = tmp_path / "nodes.py"
    path.write_text('PUBLIC = 1; SECRET = "HIDDEN_SAME_LINE"\n@node(node_type="vibeflow.node",id="PRIVATE_PARENT_DECLARATION")\nclass Parent:\n    def unrelated(self):\n        return "HIDDEN_PARENT_METHOD"\n    def run_pure(self, inputs, params):\n        return PUBLIC\nclass Leaf(Parent):\n    def unrelated(self):\n        return 0\n')
    registry.register(replace(registry.descriptor("test.leaf"), id="test.parent", rulesets=()))
    registry.source_locations["test.parent"] = (path, "Parent", "project", tmp_path)
    sources = collect_workflow_source_context(registry, GraphConfig((NodeCallSpec("leaf", "test.leaf"), NodeCallSpec("parent", "test.parent", rulesets=())), rulesets=()))
    def inspect(context, inputs, params):
        local = context.require("source_context")
        text = local.files[0].text
        assert "HIDDEN_SAME_LINE" not in text and "HIDDEN_PARENT_METHOD" not in text
        parent = local.symbol(str(path), "Parent")
        assert "HIDDEN_PARENT_METHOD" not in ast.dump(parent.node)
        assert "PRIVATE_PARENT_DECLARATION" not in ast.dump(parent.node)
        assert "PRIVATE_PARENT_DECLARATION" not in text
        assert local.class_members(local.symbol(str(path), "Leaf"))["run_pure"].name == "Parent.run_pure"
        assert local.symbol(str(path), "PUBLIC") is not None
        return RuleResult()
    report = execute_python_node_rules(registry, sources, extra_handlers={rule.id:inspect})
    assert not report.findings


def test_nested_compilation_uses_full_call_policy_path(tmp_path):
    from vibeflow.targets.python.project.compiler import GraphCompiler
    selected = RulesetDescriptor("test.none")
    registry = _registry(tmp_path, (), selected)
    registry.call_effect_scopes = {("leaf",):"terminal", ("outer", "leaf"):"none"}
    graph = GraphConfig((NodeCallSpec("leaf", "test.leaf"),))
    assert GraphCompiler().compile(graph, registry=registry).effect_scopes["leaf"] == "terminal"
    assert GraphCompiler().compile(graph, registry=registry, call_path=("outer",)).effect_scopes["leaf"] == "none"


def test_empty_local_and_graph_selections_do_not_skip_native_syntax(tmp_path):
    rule = RuleDescriptor("test.inspect")
    selected = RulesetDescriptor("test.inspect", calls=(RuleCall("inspect", rule_id=rule.id),))
    registry = _registry(tmp_path,(rule,),selected)
    (tmp_path / "nodes.py").write_text('class Leaf:\n    def run_pure(:\n        pass\n')
    sources = collect_workflow_source_context(registry,GraphConfig((NodeCallSpec("leaf","test.leaf",rulesets=()),),rulesets=()))
    report = execute_python_node_rules(registry,sources)
    assert report.findings[0].code == "QUALITY.SYNTAX.PYTHON"
    assert report.findings[0].source_location["line"] == 2
    assert report.executions == ()


def test_native_compilation_failure_keeps_completed_rule_findings_and_selection(tmp_path):
    from vibeflow.core.findings import Finding
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    rule = RuleDescriptor("test.inspect")
    selected = RulesetDescriptor("test.inspect", calls=(RuleCall("inspect", rule_id=rule.id),))
    registry = _registry(tmp_path,(rule,),selected)
    registry.rule_handler_loader = lambda _: {rule.id:lambda *_:RuleResult(findings=(Finding(
        "test.LOCAL", "warning", "node", "test.leaf", "Already checked the implementation."),))}
    graph = GraphConfig((NodeCallSpec("leaf","test.leaf"),NodeCallSpec("unknown","test.unknown")),rulesets=())
    report = validate_graph_health(graph,registry=registry,source_context=collect_workflow_source_context(registry,graph))
    assert report.errors and any(item.rule_id == "test.LOCAL" for item in report.warnings)
    assert report.info["rule_executions"] and report.info["rule_selections"]


def test_local_metrics_count_visible_utf8_and_helpers_without_masked_other_code(tmp_path):
    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality.node_context import local_sources
    registry = _registry(tmp_path,(),RulesetDescriptor("test.empty"))
    own = 'class Leaf:\n    def run_pure(self, inputs, params):\n        return helper("界")\n'
    (tmp_path / "nodes.py").write_text('from support import helper\n' + own)
    helper = 'def helper(value):\n    return value\n'
    (tmp_path / "support.py").write_text('def unrelated():\n' + '    # Other implementation\n' * 501 + '    return 0\n' + helper)
    sources = collect_workflow_source_context(registry,GraphConfig((NodeCallSpec("leaf","test.leaf"),),rulesets=()))
    local = local_sources(sources,sources.nodes[0])
    measured = local._analysis.measurements(RuleContext(facts={"source_context":local},subject={'node_type': 'vibeflow.node', "kind":"node","definition_id":"test.leaf"}))
    assert measured.metrics.source_bytes == len(('from support import helper\n' + own).encode())
    assert measured.helpers[0][1].source_lines == 2
    assert measured.helpers[0][1].source_bytes == len(helper.encode())


def test_empty_uncalled_nodeset_selection_preserves_native_compilation_errors(tmp_path):
    from vibeflow.core.flow import NodesetTypeSpec
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
    registry = _registry(tmp_path,(),RulesetDescriptor("test.empty"))
    definition = NodesetTypeSpec("unused","Unused","Uncalled",(),(),
        GraphConfig((NodeCallSpec("unknown","unknown.type",rulesets=()),),rulesets=()))
    graph = GraphConfig((NodeCallSpec("leaf","test.leaf",rulesets=()),),nodeset_types={"unused":definition},rulesets=())
    report = validate_graph_health(graph,registry=registry,source_context=collect_workflow_source_context(registry,graph))
    assert report.status == "FAIL" and any(item.object_type == "nodeset" for item in report.errors)


def test_direct_references_with_distinct_parameters_are_both_executed(tmp_path):
    rule = RuleDescriptor("test.limit",scope="source",params_schema={"limit":{"type":"integer"}},params_defaults={"limit":0})
    registry = _registry(tmp_path,(rule,),RulesetDescriptor("test.empty"))
    graph = GraphConfig((NodeCallSpec("leaf","test.leaf",rulesets=(
        {"rule_id":rule.id,"params":{"limit":1}}, {"rule_id":rule.id,"params":{"limit":2}})),),rulesets=())
    seen = []
    report = execute_python_node_rules(registry,collect_workflow_source_context(registry,graph),
        extra_handlers={rule.id:lambda context,inputs,params:seen.append(params["limit"]) or RuleResult()})
    assert not report.findings and seen == [1,2]
