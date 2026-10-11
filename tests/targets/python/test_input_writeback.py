"""Finite entry writes through the public Rule; retired semantic suites are archived."""
import pytest
from tests.targets.python.test_product_boundary import context
from vibeflow.targets.python.rules.node.input_writes import input_writes
from vibeflow.targets.python.rules.node.effects import no_side_effects


@pytest.mark.parametrize("body", (
    "inputs['x'] = 1",
    "del inputs['x']",
    "inputs['x'] += [1]",
    "inputs['items'].append(1)",
    "items = inputs['items']\nitems.append(1)",
    "items = inputs['items']\nother = items\nother[0] = 1",
    "items: object = inputs['items']\nitems.clear()",
    "(items := inputs['items']).append(1)",
    "try:\n    inputs['x'] = 1\nexcept Exception:\n    pass",
    "[inputs['items'].append(x) for x in [1]]",
    "[x for x in inputs['items'].pop()]",
    "with manager() as item:\n    inputs['x'] = 1",
    "def helper(value=inputs['items'].pop()):\n    pass",
    "[inputs for inputs in []]\ninputs['x'] = 1",
))
def test_direct_and_linear_alias_writes_are_reported(body):
    result = input_writes(context(body+'\nreturn {}'), {}, {})
    assert result.state == 'completed'
    assert result.findings
    assert {item.code for item in result.findings} == {'NODE.PURITY.INPUT_MUTATION'}


@pytest.mark.parametrize("body", (
    "items = inputs['items']\nitems = []\nitems.append(1)",
    "items = inputs['items']\nitems = items.copy()\nitems.append(1)",
    "def helper(inputs):\n    inputs['x'] = 1\nhelper({})",
    "def helper(value):\n    value.append(1)\nhelper(inputs['items'])",
    "items = inputs['items']\ndef helper():\n    items.append(1)\nhelper()",
    "[inputs.append(1) for inputs in [[]]]",
    "(inputs['items'].append(x) for x in [1])",
    "if flag:\n    items = inputs['items']\nelse:\n    items = []\nitems.append(1)",
    "with manager() as inputs:\n    inputs['x'] = 1",
    "match value:\n    case {'items': inputs}:\n        inputs.append(1)",
    "items = inputs['items']\nimport package as items\nitems.append(1)",
))
def test_rebinding_lexical_scope_and_unanalyzed_propagation_are_not_claimed(body):
    assert not input_writes(context(body+'\nreturn {}'), {}, {}).findings


def test_input_rule_selection_is_independent_of_effect_policy():
    source = context("inputs['x'] = 1\nreturn {}")
    assert not no_side_effects(source, {}, {'effect_scope':'none'}).findings
    assert input_writes(source, {}, {}).findings
    assert not input_writes(context("inputs['x'].append(1)\nreturn {}"), {}, {'mutating_methods':[]}).findings
