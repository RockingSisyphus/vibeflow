from __future__ import annotations
from tests.fixtures.support.declarations import native_registry
from tests.fixtures.support.declarations import node_declaration, configured_declaration

import math

import pytest

from tests.fixtures.support import runtime_dispatch_helpers

from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project.compiler import _implementation_fact, _runtime_dispatch_fact
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.project.node import EFFECT_SCOPE_GLOBAL_STATE, EFFECT_SCOPE_NONE, EFFECT_SCOPE_TERMINAL
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from vibeflow.targets.python.quality.source_analysis import (
    analyze_runtime_dispatch,
)
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
from vibeflow.tooling.project.graph_config import parse_graph_config


def _value(inputs, key):
    return inputs[key]["value"]


def _invoke(value):
    return value()


def _identity(value):
    return value


STATIC_CALLBACK = _identity


class DirectDispatch:
    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        return callback()


class MethodAndAliasDispatch:
    def run_pure(self, inputs, params):
        model = _value(inputs, "model.in")
        step = model.step
        return step()


class AttributeSubscriptAndGetattrDispatch:
    def run_pure(self, inputs, params):
        bundle = _value(inputs, "bundle.in")
        bundle.callbacks["first"]()
        return getattr(bundle, params.get("method", "run"))()


class BranchAndClosureDispatch:
    def run_pure(self, inputs, params):
        model = _value(inputs, "model.in")

        def invoke():
            return model.forward()

        first = invoke()
        callback = invoke
        if params.get("direct", False):
            callback = _value(inputs, "callback.in")
        return callback() or first


class LocalHelperDispatch:
    def run_pure(self, inputs, params):
        callback = _identity(_value(inputs, "callback.in"))
        return _invoke(callback)


class ClassHelperDispatch:
    def _invoke(self, value):
        return value.step()

    def run_pure(self, inputs, params):
        return self._invoke(_value(inputs, "model.in"))


class ImportedHelperDispatch:
    def run_pure(self, inputs, params):
        callback = runtime_dispatch_helpers.identity(_value(inputs, "callback.in"))
        return runtime_dispatch_helpers.invoke(callback)


class ModuleRegistryDispatch:
    def run_pure(self, inputs, params):
        callback = CALLBACK_REGISTRY.get(params.get("name", "default"))
        return callback()


CALLBACK_REGISTRY = {}


class _OwnedRunner:
    def run(self):
        return 1


class StaticAndProtocolCalls:
    def run_pure(self, inputs, params):
        payload = _value(inputs, "payload.in")
        callback = _value(inputs, "callback.in")
        print(len(payload))
        iterator = iter(payload)
        next(iterator, None)
        for value in payload:
            math.isfinite(float(value))
        runner = _OwnedRunner()
        runner.run()
        sorted([], key=callback)
        STATIC_CALLBACK(payload)
        runtime_dispatch_helpers.accept_without_invoking(payload)
        return payload.get("result")


_CONTRACT = NodeContractDescriptor(requires=(DataRequirement('callback.in', 'exactly_one', display_name='callback.in'),), provides=(DataProvider('callback.out', 'callback.out', display_name='callback.out'),), input_semantics={'callback.in': ('runtime callback',)}, output_semantics={'callback.out': ('callback result',)}, examples=({'inputs': {'callback.in': {'key': 'callback.in', 'type': 'callback.in', 'value': 1, 'source_node': 'example'}}, 'params': {}},))


OrdinaryCallbackNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.callback.ordinary', display_name='Ordinary Callback', description='Invokes a runtime callback from an ordinary process node.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), _CONTRACT, rulesets=("vibeflow.process",))

class OrdinaryCallbackNode:

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


GlobalStateCallbackNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.callback.global', display_name='Global Callback', description='Declares a visible runtime callback boundary.', version='0.1.0', flow_kind='global_state', contract=NodeContractDescriptor()), _CONTRACT, rulesets=("vibeflow.global_state",))

class GlobalStateCallbackNode:

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


IoCallbackNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.callback.io', display_name='IO Callback', description='Invokes a runtime callback inside an existing IO boundary.', version='0.1.0', flow_kind='io', contract=NodeContractDescriptor()), _CONTRACT, rulesets=("vibeflow.io",))

class IoCallbackNode:

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


ExternalCallbackNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.callback.external', display_name='External Callback', description='Represents an unavailable external callback adapter.', version='0.1.0', flow_kind='process', external=True, contract=NodeContractDescriptor()), _CONTRACT, rulesets=("vibeflow.process",))

class ExternalCallbackNode:

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}



def _check(declaration,implementation):
    from vibeflow.tooling.application.python.project.declarations import collect_node_source_context
    from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
    registry=native_registry()
    registry.register(declaration,implementation)
    return execute_python_node_rules(registry,collect_node_source_context(registry,(declaration.type_key,))).findings

def _expressions(node_cls) -> set[str]:
    analysis = analyze_runtime_dispatch(node_cls)
    assert analysis is not None
    return {site.expression for site in analysis.sites}


def test_detects_direct_method_alias_attribute_subscript_and_getattr_dispatch() -> None:
    assert _expressions(DirectDispatch) == {"callback"}
    assert _expressions(MethodAndAliasDispatch) == {"step"}
    expressions = _expressions(AttributeSubscriptAndGetattrDispatch)
    assert "bundle.callbacks['first']" in expressions
    assert any(expression.startswith("getattr(") for expression in expressions)


def test_propagates_runtime_values_through_branches_closures_and_helpers() -> None:
    branch_expressions = _expressions(BranchAndClosureDispatch)
    assert {"model.forward", "callback"} <= branch_expressions
    assert _expressions(LocalHelperDispatch) == {"value"}
    assert _expressions(ClassHelperDispatch) == {"value.step"}
    assert _expressions(ImportedHelperDispatch) == {"value"}


def test_detects_callback_loaded_from_mutable_module_registry() -> None:
    analysis = analyze_runtime_dispatch(ModuleRegistryDispatch)
    assert analysis is not None and analysis.detected
    assert analysis.sites[0].origin == "module state CALLBACK_REGISTRY"


def test_does_not_flag_builtins_protocols_static_imports_or_mapping_reads() -> None:
    analysis = analyze_runtime_dispatch(StaticAndProtocolCalls)
    assert analysis is not None
    assert not analysis.detected


def test_ordinary_node_warns_without_blocking_but_visible_effect_boundaries_do_not() -> None:
    ordinary = _check(OrdinaryCallbackNode_DECLARATION,OrdinaryCallbackNode)
    warnings = [
        item
        for item in ordinary
        if item.rule_id == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"
    ]
    assert len(warnings) == 1
    assert warnings[0].severity == "warning"
    assert warnings[0].details["site_count"] == 1
    assert not any(item.severity == "error" for item in ordinary)

    for declaration,node_cls in ((GlobalStateCallbackNode_DECLARATION,GlobalStateCallbackNode),(IoCallbackNode_DECLARATION,IoCallbackNode)):
        findings = _check(declaration,node_cls)
        assert not any(
            item.rule_id == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"
            for item in findings
        )


def test_compiler_fact_records_tri_state_runtime_dispatch_and_effect_scope() -> None:
    from dataclasses import replace
    registry=native_registry()
    for declaration,implementation in ((OrdinaryCallbackNode_DECLARATION,OrdinaryCallbackNode),(GlobalStateCallbackNode_DECLARATION,GlobalStateCallbackNode),(IoCallbackNode_DECLARATION,IoCallbackNode)):
        registry.register(declaration,implementation)
    registry.register(ExternalCallbackNode_DECLARATION)
    static=replace(OrdinaryCallbackNode_DECLARATION,type_key="test.callback.static")
    registry.register(static,StaticAndProtocolCalls)
    def fact(key):
        return _implementation_fact(key,registry.descriptor(key),effect_scope=registry.effect_scope(key),runtime_dispatch=_runtime_dispatch_fact(registry,key))
    assert fact("test.callback.ordinary").effect_scope == EFFECT_SCOPE_NONE
    assert fact("test.callback.ordinary").runtime_dispatch is True
    assert fact("test.callback.global").effect_scope == EFFECT_SCOPE_GLOBAL_STATE
    assert fact("test.callback.global").runtime_dispatch is True
    assert fact("test.callback.io").effect_scope == EFFECT_SCOPE_TERMINAL
    assert fact("test.callback.io").runtime_dispatch is True
    assert fact("test.callback.external").runtime_dispatch is None
    assert fact("test.callback.static").runtime_dispatch is False


def test_training_sandbox_declares_runtime_model_and_optimizer_calls_as_global_state() -> None:
    from pathlib import Path
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_node_source_context
    from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
    project=Path(__file__).resolve().parents[3]/"sandbox/python/integration/project"
    registry=declared_python_registry(load_project_workspace(project), project / "configs/pass_training_nodeset_object_flow.jsonc")
    keys=("sandbox.forward_loss","sandbox.backward_grad","sandbox.optimizer_step","sandbox.training_batch_step")
    context=collect_node_source_context(registry,keys)
    from vibeflow.targets.python.quality.source_analysis.runtime_dispatch import analyze_source_runtime_dispatch
    for key in keys:
        node=next(item for item in context.nodes if item.type_key == key)
        analysis=analyze_source_runtime_dispatch(context,node)
        assert analysis is not None and analysis.detected
        assert registry.descriptor(key).flow_kind == "global_state"
    report=execute_python_node_rules(registry,context)
    assert not any(item.code == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED" for item in report.findings)


def test_source_dispatch_reuses_target_trees_and_preserves_public_ast_isolation(monkeypatch):
    import ast
    from pathlib import Path
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry, collect_node_source_context
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSymbol
    from vibeflow.targets.python.quality.source_analysis.runtime_dispatch import analyze_source_runtime_dispatch

    project = Path(__file__).resolve().parents[3] / "sandbox/python/integration/project"
    registry = declared_python_registry(load_project_workspace(project), project / "configs/pass_training_nodeset_object_flow.jsonc")
    context = collect_node_source_context(registry, ("sandbox.forward_loss",))
    node = next(item for item in context.nodes if item.type_key == "sandbox.forward_loss")
    trees = {file.path: ast.dump(file._tree) for file in context.files if file._tree is not None}
    counts = {"tree": 0, "node": 0}
    tree_getter, node_getter = PythonSourceFile.tree.fget, PythonSymbol.node.fget

    def tree_view(source):
        counts["tree"] += 1
        return tree_getter(source)

    def node_view(symbol):
        counts["node"] += 1
        return node_getter(symbol)

    monkeypatch.setattr(PythonSourceFile, "tree", property(tree_view))
    monkeypatch.setattr(PythonSymbol, "node", property(node_view))
    first = analyze_source_runtime_dispatch(context, node)
    second = analyze_source_runtime_dispatch(context, node)
    assert first is not None and first.detected and first == second
    assert counts == {"tree": 0, "node": 0}
    assert trees == {file.path: ast.dump(file._tree) for file in context.files if file._tree is not None}
    source = context.file(node.path)
    source.tree.body.clear()
    symbol = context.symbol(node.path, node.symbol)
    symbol.node.body.clear()
    assert source.tree.body
    assert symbol.node.body
    assert trees[node.path] == ast.dump(source._tree)


def _global_state_graph(*, lock_scope: str = ""):
    state_node = {
        "id": "state",
        "type_used": "sandbox.global_state_probe",
        "display_name": "Global State",
        "description": "Mutates audited process-local state.",
    }
    pipeline = {
        "nodes": [
            {
                "id": "start",
                "type_used": "test.start",
                "display_name": "Start",
                "description": "Starts the flow.",
            },
            state_node,
            {
                "id": "end",
                "type_used": "test.out_end",
                "display_name": "End",
                "description": "Ends after the state value is ready.",
            },
        ],
        "edges": [
            {"from": "start", "to": "state"},
            {"from": "state", "to": "end"},
        ],
        "outputs": [
            {
                "type": "value.out",
                "cardinality": "exactly_one",
                "display_name": "Value Output",
            }
        ],
    }
    if lock_scope == "root":
        pipeline["execution_lock"] = {"key": "test.callback.serial"}
    elif lock_scope == "node":
        state_node["execution_lock"] = {"key": "test.callback.serial"}
    return parse_graph_config({"pipeline": pipeline})


def _global_state_health(*, lock_scope: str = ""):
    from pathlib import Path
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_workflow_source_context
    from tests.fixtures.support.strict_support_runtime_nodes import OutEndNode,OutEndNode_DECLARATION,StartNode,StartNode_DECLARATION
    project=Path(__file__).resolve().parents[3]/"sandbox/python/integration/project"
    registry=declared_python_registry(load_project_workspace(project), project / "configs/pass_training_nodeset_object_flow.jsonc")
    registry.register(StartNode_DECLARATION,StartNode)
    registry.register(OutEndNode_DECLARATION,OutEndNode)
    graph=_global_state_graph(lock_scope=lock_scope)
    return validate_graph_health(graph,registry=registry,source_context=collect_workflow_source_context(registry,graph))


def test_unlocked_global_state_health_warning_is_advisory() -> None:
    health = _global_state_health()

    assert not health.errors
    warnings = [
        finding
        for finding in health.warnings
        if finding.rule_id
        == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
    ]
    assert len(warnings) == 1
    assert warnings[0].details["execution_lock"] is None


@pytest.mark.parametrize("lock_scope", ["root", "node"])
def test_effective_named_lock_suppresses_global_state_coordination_warning(
    lock_scope: str,
) -> None:
    health = _global_state_health(lock_scope=lock_scope)

    assert not health.errors
    assert not any(
        finding.rule_id
        == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
        for finding in health.warnings
    )
