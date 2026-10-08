"""A checked compiler artifact survives review without another hook invocation."""

from types import SimpleNamespace

from tests.targets.python.test_rule_sessions import _registry
from vibeflow.core.flow import GraphConfig, NodeSpec
from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleCall, RuleDescriptor, RuleRecord, RuleResult, RulesetDescriptor
from vibeflow.targets.python.project.check_session import current_python_check
from vibeflow.targets.python.project.compiler import GraphCompiler
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
from vibeflow.tooling.application.python.presentation.prepared import python_check_scope
from vibeflow.tooling.application.python.project.declarations import collect_workflow_source_context


def test_review_refreshes_rule_owned_metadata_without_replacing_stage_artifact(tmp_path, monkeypatch):
    rule = RuleDescriptor("test.effect", scope="source", outputs={"policy":EFFECT_POLICY_TYPE})
    selection = RulesetDescriptor("test.effect", calls=(RuleCall("effect",rule_id=rule.id),),
                                   entrypoints={"static":("effect",)})
    registry = _registry(tmp_path, (rule,), selection)
    registry.rule_handler_loader = lambda _plan: {rule.id:lambda *_:RuleResult(records={
        "policy":RuleRecord(EFFECT_POLICY_TYPE,{"effect_scope":"python_io"})})}
    events = []
    class Compiler:
        def before_compile(self, graph):
            events.append("before")
        def after_compile(self, graph, compiled):
            events.append("after")
            compiled.providers["compiler.marker"] = "preserved"
    plugins = SimpleNamespace(compiler_plugins=lambda:(Compiler(),), review_findings=(), to_dict=lambda:{"plugins":[]})
    from vibeflow.targets.python.project import compiler
    original, calls = compiler.compile_core, []
    def native(request):
        calls.append(request)
        return original(request)
    monkeypatch.setattr(compiler,"compile_core",native)
    graph = GraphConfig(nodes=(NodeSpec("leaf","test.leaf"),), rulesets=())
    with python_check_scope(registry):
        stage = GraphCompiler().compile_with_findings(graph, registry=registry, plugin_registry=plugins)
        graph = stage.workflow.graph
        report = validate_graph_health(graph, registry=registry, plugin_registry=plugins,
            source_context=collect_workflow_source_context(registry,graph))
        final = current_python_check(registry).checked_compilation(graph)
        assert report.status == "PASS"
        assert final.compiled_graph.providers == {"compiler.marker":"preserved"}
        assert final.compiled_graph.effect_scopes == {"leaf":"python_io"}
        assert final.workflow.implementation_facts.get("test.leaf").effect_scope == "python_io"
        assert final.compiled_graph.order == stage.compiled_graph.order
        assert final.workflow.graph is graph
    assert events == ["before","after"]
    assert len(calls) == 1
    assert current_python_check(registry) is None


def test_compiler_stages_are_private_to_the_current_check(tmp_path):
    selection = RulesetDescriptor("test.none", calls=())
    registry = _registry(tmp_path, (), selection)
    plugins = SimpleNamespace(compiler_plugins=lambda:())
    graph = GraphConfig(nodes=(NodeSpec("leaf","test.leaf"),), rulesets=())
    with python_check_scope(registry):
        stage = GraphCompiler().compile_with_findings(graph, registry=registry, plugin_registry=plugins)
        session = current_python_check(registry)
        assert session.compiler_stage(graph) is stage
        assert session.compiler_stage(stage.workflow.graph) is stage
        assert session.compiler_stage(GraphConfig(nodes=graph.nodes,rulesets=())) is None
    with python_check_scope(registry):
        assert current_python_check(registry).compiler_stage(graph) is None
