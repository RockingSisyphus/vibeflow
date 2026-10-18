"""Scheduling values belong to a call, not its business or global contract."""

import pytest

from vibeflow.core.config.concurrency import business_config, dispatch_limit, merge_call_config
from vibeflow.core.config.node import NodeConfigError, merge_node_config, normalize_node_config_spec
from vibeflow.core.config.scope import node_invocation_scope, normalize_node_config_overrides, ConfigBindingError
from vibeflow.core.flow import GraphConfigError, NodeSpec
from vibeflow.tooling.project.graph_config import parse_graph_config


@pytest.mark.parametrize("value", [0, -1, True, False, 2.5, "4", None, [], {}])
def test_call_config_rejects_invalid_capacity(value):
    with pytest.raises(GraphConfigError, match="max_concurrency"):
        parse_graph_config({"pipeline": {"nodes": [{"id": "dispatch", "type_used": "test.dispatch",
            "display_name": "Dispatch", "description": "Queue calls", "config": {"max_concurrency": value}}]}})
    with pytest.raises(NodeConfigError, match="max_concurrency"):
        NodeSpec("dispatch", "test.dispatch", params={"max_concurrency": value})


def test_call_config_extracts_scheduler_value_without_relaxing_business_contract():
    spec = normalize_node_config_spec({"label": {"type": "string"}}, {"label": "default"})
    merged = merge_call_config(spec, {"label": "local", "max_concurrency": 4})
    assert dispatch_limit(merged) == 4
    assert business_config(merged) == {"label": "local"}
    assert dispatch_limit({}) == 8
    with pytest.raises(NodeConfigError, match="undeclared"):
        merge_call_config(spec, {"unknown": 1, "max_concurrency": 4})
    with pytest.raises(NodeConfigError, match="max_concurrency"):
        merge_call_config(spec, {"max_concurrency": 0})
    # Rule parameters use the original checker, which has no scheduling keys.
    with pytest.raises(NodeConfigError, match="undeclared"):
        merge_node_config(spec, {"max_concurrency": 4})


def test_dispatch_capacity_does_not_become_a_child_global_setting():
    scope = node_invocation_scope({"max_concurrency": 2, "label": "parent"}, allow_config_override=False)
    assert scope.values == {"label": "parent"}


def test_business_contract_cannot_claim_the_scheduler_key():
    spec = normalize_node_config_spec({"max_concurrency": {"type": "integer"}}, {"max_concurrency": 4})
    with pytest.raises(NodeConfigError, match="reserved"):
        merge_call_config(spec, {})


def test_call_override_validation_covers_nested_dispatchers():
    assert normalize_node_config_overrides({"body.dispatch": {"max_concurrency": 4}}) == {
        "body.dispatch": {"max_concurrency": 4}}
    with pytest.raises(ConfigBindingError, match="max_concurrency"):
        normalize_node_config_overrides({"body.dispatch": {"max_concurrency": False}})
    with pytest.raises(GraphConfigError, match="max_concurrency"):
        parse_graph_config({"pipeline": {"nodes": [{"id": "outer", "type_used": "test.body",
            "display_name": "Outer", "description": "Nested work",
            "node_configs": {"dispatch": {"max_concurrency": 0}}}]}})
