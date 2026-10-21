from dataclasses import replace

import pytest

from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor, NodeTypeDescriptor
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.node_types import resolve_node_type
from vibeflow.core.rules.selection import resolve_node_selection
from vibeflow.core.flow import NodeCallSpec
from vibeflow.core.style import NODE_SHAPES


@pytest.mark.parametrize("shape", sorted(NODE_SHAPES))
def test_node_shell_and_business_node_resolve_before_call_overrides(shape):
    shell = NodeTypeDescriptor("shell", rulesets=("type.rules",),
        presentation={"shape": shape, "fill": "#f4e4c0", "stroke": "#121212"})
    node = NodeDescriptor(id="business", node_type="shell", display_name="Step", description="Business step",
        version="1", flow_kind="process", contract=NodeContractDescriptor(), presentation={"fill": "#fff0d0"})
    effective = resolve_node_type(node, {"shell": shell})
    assert effective.presentation == {"shape": shape, "fill": "#fff0d0", "stroke": "#121212"}
    assert effective.rulesets == ("type.rules",)
    assert resolve_node_selection(effective, NodeCallSpec("one", "business")).references == ("type.rules",)
    assert resolve_node_selection(effective, NodeCallSpec("two", "business", rulesets=())).references == ()
    assert resolve_node_type(replace(node, rulesets=()), {"shell": shell}).rulesets == ()
    assert node.rulesets is None


def test_node_type_cannot_contain_business_contract_or_implementation():
    for field, value in (("contract", {}), ("implementations", [])):
        with pytest.raises(ValueError, match="unknown"):
            decode_resource({"kind": "node_type", "id": "shell", field: value})


def test_business_node_format_does_not_accept_old_type_key_identifier():
    with pytest.raises(ValueError, match="type_key"):
        decode_resource({"kind": "node", "type_key": "old", "contract": {}})
