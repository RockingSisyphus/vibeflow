"""Command-local reuse preserves facts, call rules and import refusal."""
from dataclasses import replace

import pytest

from tests.targets.python.test_rule_sessions import _registry, _repeated_graph
from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor
from vibeflow.targets.python.project.check_session import begin_python_check, current_python_check, end_python_check
from vibeflow.targets.python.project.source_closure import collect_python_source_facts
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
from vibeflow.targets.python.rules.node.policy import PurityPolicy
from vibeflow.tooling.application.python.project.declarations import _bind_node, collect_workflow_source_context, PythonSourceRuleError


def _case(tmp_path, *, scope="source", handler=None, policy_parameters=False):
    rule = RuleDescriptor("test.review",scope=scope,
        **({"handler":"vibeflow.maintainability", "params_schema":{"policy":{"type":"object"}},
            "params_defaults":{"policy":{}}} if policy_parameters else {}))
    selection = RulesetDescriptor("test.review",calls=(RuleCall("check",rule_id=rule.id),),
                                  entrypoints={"import":("check",),"static":("check",),"run":("check",)})
    registry = _registry(tmp_path,(rule,),selection)
    handlers = {rule.id:handler or (lambda *_: RuleResult())}
    registry.rule_handler_loader = lambda _: handlers
    begin_python_check(registry)
    sources = collect_workflow_source_context(registry,_repeated_graph())
    return registry,sources,handlers


def test_source_reuse_is_private_to_session_and_call_checks_are_live(tmp_path):
    registry,sources,handlers = _case(tmp_path)
    seen = []
    handlers["test.review"] = lambda context,*_: seen.append(context.phase) or RuleResult()
    execute_python_node_rules(registry,sources,phase="import")
    again = execute_python_node_rules(registry,sources,phase="import")
    assert seen == ["import"] and all(not item.executed for item in again.executions)
    execute_python_node_rules(registry,sources,phase="run")
    assert seen == ["import","run"]
    session = current_python_check(registry)
    end_python_check(registry)
    assert current_python_check(registry) is None and session.views == {}
    begin_python_check(registry)
    execute_python_node_rules(registry,sources,phase="import")
    assert seen == ["import","run","import"]
    end_python_check(registry)
    registry,sources,handlers = _case(tmp_path,scope="call")
    calls = []
    handlers["test.review"] = lambda context,*_: calls.append(context.subject["call_id"]) or RuleResult()
    for _ in range(2):
        execute_python_node_rules(registry,sources,phase="import")
    assert calls == ["first/leaf","second/leaf","first/leaf","second/leaf"]
    end_python_check(registry)


def test_local_source_cache_uses_effective_params_and_handler_without_global_facts(tmp_path):
    registry,sources,handlers = _case(tmp_path,policy_parameters=True)
    seen = []
    from functools import wraps
    @wraps(registry.direct_bindings[("rule","vibeflow.maintainability")])
    def check(context,inputs,params):
        assert not {"plugins", "node_catalog", "source_load_states", "extra"} & context.facts.keys()
        seen.append(params["policy"]["node_source"]["max_lines"])
        return RuleResult()
    handlers["test.review"] = check
    config = {"plugins":{"demo":{"value":1}},"extra":{"value":1}}
    def run(policy=500):
        return execute_python_node_rules(registry,sources,phase="import",purity_policy=PurityPolicy(max_source_lines=policy),extra_facts=config)
    run(); run()
    config["plugins"]["demo"]["value"] = 9
    config["extra"]["value"] = 2
    run()
    run(100)
    assert seen == [500,100]
    replacements = []
    handlers["test.review"] = lambda *_: replacements.append(1) or RuleResult()
    run(100)
    assert replacements == [1]
    end_python_check(registry)


@pytest.mark.parametrize("state,severity",[("completed","error"),("failed","warning"),("unavailable","warning")])
def test_cached_or_incomplete_import_result_still_blocks_binding_marker(tmp_path,state,severity):
    calls = []
    def check(*_):
        calls.append(1)
        return RuleResult(state=state,findings=(HealthFinding(rule_id="TEST.IMPORT",severity=severity,message="refused"),))
    registry,sources,_ = _case(tmp_path,handler=check)
    marker = tmp_path / "node-imported"
    path = tmp_path / "nodes.py"
    path.write_text(f'from pathlib import Path\nPath({str(marker)!r}).write_text("loaded")\nclass Leaf:\n    def run_pure(self,inputs,params):\n        return {{}}\n')
    sources = collect_workflow_source_context(registry,_repeated_graph())
    before = execute_python_node_rules(registry,sources,phase="import")
    assert before.findings
    registry.register(registry.descriptor("test.leaf"),loader=lambda:_bind_node(registry,"test.leaf",(tmp_path,)),overwrite=True)
    with pytest.raises(PythonSourceRuleError):
        registry.get("test.leaf")
    assert not marker.exists()
    assert len(calls) == (1 if state == "completed" else 4)
    end_python_check(registry)


def test_changed_source_and_selected_params_are_new_views(tmp_path):
    registry,sources,handlers = _case(tmp_path)
    seen = []
    handlers["test.review"] = lambda context,*_: seen.append(context.facts["source_context"].files[0].text) or RuleResult()
    execute_python_node_rules(registry,sources,phase="import")
    path = tmp_path / "nodes.py"
    path.write_text(path.read_text().replace("return {}", "return {1: 2}"))
    changed = collect_workflow_source_context(registry,_repeated_graph())
    execute_python_node_rules(registry,changed,phase="import")
    assert len(seen) == 2 and seen[0] != seen[1]
    original = registry.rule_catalogs[-1].rulesets[0]
    registry.rule_catalogs[-1].rulesets = (replace(original,calls=(RuleCall("check",rule_id="test.review",params={"tag":1}),)),)
    # An undeclared parameter is diagnosed rather than served from an earlier plan.
    rejected = execute_python_node_rules(registry,changed,phase="import")
    assert rejected.findings and len(seen) == 2
    end_python_check(registry)


def test_fact_view_freezes_once_across_phases_and_keeps_explicit_quality_fact(tmp_path):
    registry,sources,_ = _case(tmp_path)
    registry.source_load_states = {sources.files[0].path:"not_loaded"}
    extra = {"quality_policy":{"custom":True}}
    session = current_python_check(registry)
    view = session.view(registry,sources,extra_facts=extra)
    first = view.context("import")
    registry.source_load_states[sources.files[0].path] = "loaded"
    extra["quality_policy"]["custom"] = False
    later = view.context("static")
    assert later.facts is first.facts
    assert later.facts["source_load_states"][sources.files[0].path] == "not_loaded"
    assert later.facts["quality_policy"]["custom"] is True
    changed = session.view(registry,sources,extra_facts=extra)
    assert changed.token != view.token and changed.context("static").facts["quality_policy"]["custom"] is False
    end_python_check(registry)


def test_opaque_mutable_extra_fact_is_not_reused_by_object_identity(tmp_path):
    from types import SimpleNamespace
    registry,sources,handlers = _case(tmp_path)
    external = SimpleNamespace(value=1)
    seen = []
    handlers["test.review"] = lambda context,*_: seen.append("opaque" in context.facts) or RuleResult()
    execute_python_node_rules(registry,sources,phase="import",extra_facts={"opaque":external})
    external.value = 2
    execute_python_node_rules(registry,sources,phase="import",extra_facts={"opaque":external})
    assert seen == [False]
    end_python_check(registry)


@pytest.mark.parametrize("scope,expected",[("source",2),("call",4)])
def test_equal_diagnostic_text_does_not_merge_distinct_effective_checks(tmp_path,scope,expected):
    registry,sources,handlers = _case(tmp_path,scope=scope)
    rule = replace(registry.rule_catalogs[-1].rules[0],params_schema={"limit":{"type":"integer"}},params_defaults={"limit":0})
    selection = replace(registry.rule_catalogs[-1].rulesets[0],calls=(
        RuleCall("first",rule_id=rule.id,params={"limit":1}),
        RuleCall("second",rule_id=rule.id,params={"limit":2})),entrypoints={"import":("first","second")})
    registry.rule_catalogs[-1].rules = (rule,)
    registry.rule_catalogs[-1].rulesets = (selection,)
    handlers["test.review"] = lambda *_: RuleResult(findings=(HealthFinding(rule_id="TEST.EQUAL",severity="warning",message="same text"),))
    report = execute_python_node_rules(registry,sources,phase="import")
    assert len(report.findings) == expected
    end_python_check(registry)


def test_call_diagnostics_keep_local_invocation_identity_across_rulesets(tmp_path):
    registry,sources,handlers = _case(tmp_path,scope="call")
    selected = registry.rule_catalogs[-1].rulesets[0]
    registry.rule_catalogs[-1].rulesets = (replace(selected,id="test.left"),replace(selected,id="test.right"))
    descriptor = replace(registry.descriptor("test.leaf"),rulesets=("test.left","test.right"))
    registry.register(descriptor,loader=lambda:None,overwrite=True)
    sources = collect_workflow_source_context(registry,_repeated_graph())
    seen = []
    handlers["test.review"] = lambda *_: seen.append(1) or RuleResult(findings=(
        HealthFinding(rule_id="TEST.EQUAL",severity="warning",message="same text"),))
    report = execute_python_node_rules(registry,sources,phase="import")
    assert len(seen) == 4 and len(report.findings) == 4
    end_python_check(registry)


def test_prepared_implementation_facts_compile_child_without_registry_queries(tmp_path,monkeypatch):
    from vibeflow.targets.python.project.compiler import GraphCompiler
    registry,_,_ = _case(tmp_path)
    graph = _repeated_graph()
    compiler = GraphCompiler()
    facts = compiler.prepare_implementation_facts(graph,registry=registry)
    monkeypatch.setattr(registry,"descriptor",lambda *_: (_ for _ in ()).throw(AssertionError("facts were adapted twice")))
    root = compiler.compile_with_findings(graph,registry=registry,implementation_facts=facts)
    child = compiler.compile(graph.nodesets["test.inner"].graph,registry=registry,implementation_facts=facts)
    assert root.workflow.implementation_facts is facts
    assert child.order == ("leaf",)
    end_python_check(registry)


def test_shared_parse_cache_keeps_each_import_closure_and_refreshes_changed_file(tmp_path,monkeypatch):
    import ast
    counts = []
    original = ast.parse
    monkeypatch.setattr(ast,"parse",lambda *args,**kwargs: counts.append(args[0]) or original(*args,**kwargs))
    for name in ("first","second"):
        (tmp_path/f"{name}.py").write_text(f"import {name}_helper\n")
        (tmp_path/f"{name}_helper.py").write_text("VALUE = 1\n")
    parsed = {}
    first = collect_python_source_facts(tmp_path/"first.py",project_root=tmp_path,_parsed=parsed)
    second = collect_python_source_facts(tmp_path/"second.py",project_root=tmp_path,_parsed=parsed)
    repeated = collect_python_source_facts(tmp_path/"first.py",project_root=tmp_path,_parsed=parsed)
    assert {item.module_name for item in first} == {"first","first_helper"}
    assert {item.module_name for item in second} == {"second","second_helper"}
    assert len(counts) == 4 and repeated[0]._tree is first[0]._tree
    (tmp_path/"first_helper.py").write_text("VALUE = 2000\n")
    changed = collect_python_source_facts(tmp_path/"first.py",project_root=tmp_path,_parsed=parsed)
    assert len(counts) == 5 and any("2000" in item.source for item in changed)


def test_fact_view_preserves_mapping_key_types_and_iteration_order(tmp_path):
    registry,sources,_ = _case(tmp_path)
    session = current_python_check(registry)
    mappings = ({1:"value"},{"1":"value"},{"a":1,"b":2},{"b":2,"a":1})
    views = [session.view(registry,sources,extra_facts={"nested":item}) for item in mappings]
    assert len({view.token for view in views}) == len(mappings)
    assert [list(view.facts["nested"].items()) for view in views] == [list(item.items()) for item in mappings]
    end_python_check(registry)


def test_fact_view_preserves_distinct_same_named_dataclass_types(tmp_path):
    from dataclasses import make_dataclass
    registry,sources,_ = _case(tmp_path)
    session = current_python_check(registry)
    first = make_dataclass("Facts",[("value",int)],frozen=True)
    second = make_dataclass("Facts",[("value",int)],frozen=True)
    one = session.view(registry,sources,extra_facts={"data":first(1)})
    two = session.view(registry,sources,extra_facts={"data":second(1)})
    assert one.token != two.token
    assert type(one.facts["data"]) is first and type(two.facts["data"]) is second
    end_python_check(registry)


def test_unknown_primitive_subclass_is_not_stable_by_its_base_value(tmp_path):
    class MutableString(str):
        pass
    registry,sources,handlers = _case(tmp_path)
    value = MutableString("same base string")
    value.observed = 1
    seen = []
    handlers["test.review"] = lambda context,*_: seen.append("extra" in context.facts) or RuleResult()
    execute_python_node_rules(registry,sources,phase="import",extra_facts={"extra":value})
    value.observed = 2
    execute_python_node_rules(registry,sources,phase="import",extra_facts={"extra":value})
    assert seen == [False]
    end_python_check(registry)


def test_changed_provider_records_invalidate_source_consumer_only(tmp_path):
    from vibeflow.core.flow import GraphConfig,NodeSpec
    registry,_,handlers = _case(tmp_path)
    provider = RuleDescriptor("test.provide",scope="call",outputs={"data":"test.data.v1"})
    consumer = replace(registry.rule_catalogs[-1].rules[0],inputs={"data":"test.data.v1"})
    selection = RulesetDescriptor("test.review",calls=(RuleCall("provide",rule_id=provider.id),RuleCall("consume",rule_id=consumer.id)),
        relations=(RuleRelation("consume","provide","requires",bindings={"data":"data"}),),entrypoints={"import":("consume",)})
    registry.rule_catalogs[-1].rules = (provider,consumer)
    registry.rule_catalogs[-1].rulesets = (selection,)
    graph = GraphConfig(nodes=tuple(NodeSpec(name,"test.leaf",params={"marker":value})
        for name,value in (("first",1),("second",2),("third",2))),rulesets=())
    sources = collect_workflow_source_context(registry,graph)
    produced, consumed = [], []
    def provide(context,*_):
        value = context.require("call").params["marker"]
        produced.append(value)
        return RuleResult(records={"data":RuleRecord("test.data.v1",{"value":value})})
    def consume(context,inputs,params):
        value = inputs["data"].value["value"]
        consumed.append(value)
        return RuleResult(findings=(HealthFinding(rule_id="TEST.CONSUMED",severity="warning",message=str(value)),))
    handlers.update({provider.id:provide,consumer.id:consume})
    report = execute_python_node_rules(registry,sources,phase="import")
    assert produced == [1,2,2] and consumed == [1,2]
    assert len(report.findings) == 2
    assert [{item["node"] for item in finding.details["calls"]} for finding in report.findings] == [{"first"}, {"second","third"}]
    again = execute_python_node_rules(registry,sources,phase="import")
    assert produced == [1,2,2,1,2,2] and consumed == [1,2]
    assert all(item.executed == ("provide",) for item in again.executions)
    end_python_check(registry)


def test_native_identity_captures_loading_after_handler_preparation_and_only_selected_rules(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from vibeflow.targets.python.quality import rule_adapter as adapter
    registry,sources,handlers = _case(tmp_path)
    path = sources.files[0].path
    seen=[]; identities=[]
    def check(context,*_):
        assert 'call' not in context.facts and 'call_id' not in context.subject
        seen.append(context.facts['source_load_states'][path])
        return RuleResult()
    handlers['test.review']=check
    bindings={**handlers,**{f'unselected.{i}':lambda *_:RuleResult() for i in range(26)}}
    monkeypatch.setattr(adapter,'native_rule_bindings',lambda *_:bindings)
    monkeypatch.setattr(adapter,'native_rule_origins',lambda *_:{('rules',key):SimpleNamespace(plugin_id='vibeflow.core') for key in bindings})
    state={'value':'first'}
    registry.source_load_states={path:'before_loading'}
    def load(_):
        registry.source_load_states[path]=state['value']
        return handlers
    registry.rule_handler_loader=load
    original=adapter.execute_rule_plan
    def execute(plan,context,**kwargs):
        identities.append(set(context.subject['source_cache_identities']))
        return original(plan,context,**kwargs)
    monkeypatch.setattr(adapter,'execute_rule_plan',execute)
    for value in ('first','first','second'):
        state['value']=value
        adapter.execute_python_node_rules(registry,sources,phase='import')
    assert seen==['first','second']
    assert all(keys=={'test.review'} for keys in identities)
    end_python_check(registry)


def test_native_alias_uses_the_implementation_background_without_exposing_it_to_custom_rules(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from vibeflow.targets.python.quality import rule_adapter as adapter
    registry,sources,handlers = _case(tmp_path)
    seen=[]
    def check(context,*_):
        seen.append('node_catalog' in context.facts)
        return RuleResult()
    handlers['test.review']=check
    monkeypatch.setattr(adapter,'native_rule_bindings',lambda *_: {'core.original':check,'test.review':check})
    monkeypatch.setattr(adapter,'native_rule_origins',lambda *_:{('rules','core.original'):SimpleNamespace(plugin_id='vibeflow.core'),
        ('rules','test.review'):SimpleNamespace(plugin_id='custom')})
    adapter.execute_python_node_rules(registry,sources,phase='import')
    assert seen==[True]
    end_python_check(registry)
