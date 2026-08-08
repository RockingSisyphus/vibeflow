from __future__ import annotations

import math

import pytest

from tests.fixtures.support import runtime_dispatch_helpers

from vibeflow.core import DataProvider, DataRequirement
from vibeflow.targets.python.project.compiler import _implementation_fact
from vibeflow.targets.python.project.registry import NodeRegistry
from vibeflow.targets.python.project.node import (
    EFFECT_SCOPE_GLOBAL_STATE,
    EFFECT_SCOPE_NONE,
    EFFECT_SCOPE_TERMINAL,
    NodeContract,
    NodeInfo,
)
from vibeflow.targets.python.quality.source_analysis import (
    analyze_runtime_dispatch,
    validate_node_class,
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


_CONTRACT = NodeContract(
    requires=(DataRequirement("callback.in", "exactly_one", display_name="callback.in"),),
    provides=(DataProvider("callback.out", "callback.out", display_name="callback.out"),),
    input_semantics={"callback.in": ("runtime callback",)},
    output_semantics={"callback.out": ("callback result",)},

    examples=(
        {
            "inputs": {
                "callback.in": {
                    "key": "callback.in",
                    "type": "callback.in",
                    "value": 1,
                    "source_node": "example",
                }
            },
            "params": {},
        },
    ),
)


class OrdinaryCallbackNode:
    NODE_INFO = NodeInfo(
        "test.callback.ordinary",
        "Ordinary Callback",
        "test",
        "Invokes a runtime callback from an ordinary process node.",
        "0.1.0",
        "process",
    )
    CONTRACT = _CONTRACT

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


class GlobalStateCallbackNode:
    NODE_INFO = NodeInfo(
        "test.callback.global",
        "Global Callback",
        "test",
        "Declares a visible runtime callback boundary.",
        "0.1.0",
        "global_state",
    )
    CONTRACT = _CONTRACT

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


class IoCallbackNode:
    NODE_INFO = NodeInfo(
        "test.callback.io",
        "IO Callback",
        "test",
        "Invokes a runtime callback inside an existing IO boundary.",
        "0.1.0",
        "io",
    )
    CONTRACT = _CONTRACT

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


class ExternalCallbackNode:
    NODE_INFO = NodeInfo(
        "test.callback.external",
        "External Callback",
        "test",
        "Represents an unavailable external callback adapter.",
        "0.1.0",
        "process",
        external=True,
    )
    CONTRACT = _CONTRACT

    def run_pure(self, inputs, params):
        callback = _value(inputs, "callback.in")
        value = callback() if callable(callback) else callback
        return {"callback.out": value}


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
    ordinary = validate_node_class(OrdinaryCallbackNode)
    warnings = [
        item
        for item in ordinary
        if item.rule_id == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"
    ]
    assert len(warnings) == 1
    assert warnings[0].severity == "warning"
    assert warnings[0].details["site_count"] == 1
    assert not any(item.severity == "error" for item in ordinary)

    for node_cls in (GlobalStateCallbackNode, IoCallbackNode):
        findings = validate_node_class(node_cls)
        assert not any(
            item.rule_id == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"
            for item in findings
        )


def test_compiler_fact_records_tri_state_runtime_dispatch_and_effect_scope() -> None:
    ordinary = _implementation_fact("test.callback.ordinary", OrdinaryCallbackNode)
    global_state = _implementation_fact("test.callback.global", GlobalStateCallbackNode)
    io = _implementation_fact("test.callback.io", IoCallbackNode)
    external = _implementation_fact("test.callback.external", ExternalCallbackNode)
    static = _implementation_fact("test.callback.static", StaticAndProtocolCalls)

    assert ordinary.effect_scope == EFFECT_SCOPE_NONE
    assert ordinary.runtime_dispatch is True
    assert global_state.effect_scope == EFFECT_SCOPE_GLOBAL_STATE
    assert global_state.runtime_dispatch is True
    assert io.effect_scope == EFFECT_SCOPE_TERMINAL
    assert io.runtime_dispatch is True
    assert external.runtime_dispatch is None
    assert static.runtime_dispatch is False


def test_training_sandbox_declares_runtime_model_and_optimizer_calls_as_global_state() -> None:
    from sandbox.python.integration.project.nodes.legal_training_nodes import (
        BackwardGradNode,
        ForwardLossNode,
        OptimizerStepNode,
        TrainingBatchStepNode,
    )

    for node_cls in (
        ForwardLossNode,
        BackwardGradNode,
        OptimizerStepNode,
        TrainingBatchStepNode,
    ):
        analysis = analyze_runtime_dispatch(node_cls)
        assert analysis is not None and analysis.detected
        assert node_cls.NODE_INFO.flow_kind == "global_state"
        assert not any(
            finding.rule_id == "NODE.EFFECT.RUNTIME_DISPATCH.UNDECLARED"
            for finding in validate_node_class(node_cls)
        )


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
    from sandbox.python.integration.project.nodes.legal_global_state_nodes import (
        GlobalStateProbeNode,
    )
    from tests.fixtures.support.strict_support_runtime_nodes import (
        OutEndNode,
        StartNode,
    )

    registry = NodeRegistry()
    registry.register(
        "sandbox.global_state_probe",
        GlobalStateProbeNode,
        config_schema={},
        config_defaults={},
    )
    registry.register(
        "test.start",
        StartNode,
        config_schema={},
        config_defaults={},
    )
    registry.register(
        "test.out_end",
        OutEndNode,
        config_schema={},
        config_defaults={},
    )
    return validate_graph_health(
        _global_state_graph(lock_scope=lock_scope),
        registry=registry,
    )


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
