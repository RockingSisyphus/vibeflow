"""Retained rules: implicit global binding and independent sibling branches."""
from textwrap import indent

import pytest

from tests.targets.python.test_boundary_review_regressions import effect_context
from tests.targets.python.test_product_boundary import context
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.rules.node.input_writes import input_writes


GLOBAL_BINDINGS = (
    'for VERSION in [2]:\n    pass',
    'for VERSION, local in [(2, 3)]:\n    pass',
    'for *VERSION, local in [(2, 3)]:\n    pass',
    'with manager as VERSION:\n    pass',
    'import math as VERSION',
    'from math import pi as VERSION',
    'def VERSION():\n    return 2',
    'async def VERSION():\n    return 2',
    'class VERSION:\n    pass',
    'try:\n    raise ValueError()\nexcept ValueError as VERSION:\n    pass',
    'match 2:\n    case VERSION:\n        pass',
    'match [2]:\n    case [*VERSION]:\n        pass',
    "match {'x': 2}:\n    case {'x': local, **VERSION}:\n        pass",
    '[(VERSION := item) for item in [2]]',
)


@pytest.mark.parametrize('kind', ('node', 'base_lib', 'plugin', 'python_source'))
@pytest.mark.parametrize('binding', GLOBAL_BINDINGS)
def test_all_explicit_global_bindings_obey_selected_scope(kind, binding):
    body = 'global VERSION\n' + binding + '\nreturn {}'
    # Unlike invalid global annotations, these are executable Python syntax.
    compile('VERSION = 1\ndef helper():\n' + indent(body, '    '), '<global-binding>', 'exec')
    source = effect_context(kind, body)
    denied = no_side_effects(source, {}, {'effect_scope': 'none'})
    assert {f.code for f in denied.findings} == {
        'BASE_LIB.GLOBAL_STATE' if kind == 'base_lib'
        else 'QUALITY.SIDE_EFFECT.CALL' if kind == 'python_source'
        else 'NODE.PURITY.GLOBAL_STATE'
    }
    assert not no_side_effects(source, {}, {'effect_scope': 'global_state'}).findings


@pytest.mark.parametrize('binding', ('async for VERSION in values:\n    pass',
                                    'async with manager as VERSION:\n    pass'))
def test_async_binding_uses_function_global_scope(binding):
    body = 'global VERSION\n' + binding + '\nreturn {}'
    compile('VERSION = 1\nasync def helper():\n' + indent(body, '    '), '<async-binding>', 'exec')
    source = effect_context('node', body)
    assert {f.code for f in no_side_effects(source, {}, {'effect_scope': 'none'}).findings} == {'NODE.PURITY.GLOBAL_STATE'}
    assert not no_side_effects(source, {}, {'effect_scope': 'global_state'}).findings


@pytest.mark.parametrize('kind', ('node', 'base_lib', 'plugin', 'python_source'))
@pytest.mark.parametrize('body', (
    'global VERSION\nvalue = [VERSION for VERSION in [2]]',
    'global VERSION\nvalue = {VERSION for VERSION in [2]}',
    'global VERSION\nvalue = {VERSION: VERSION for VERSION in [2]}',
    'global VERSION\nvalue = (VERSION for VERSION in [2])',
    'global VERSION\ndef local():\n    for VERSION in [2]:\n        pass',
    'global VERSION\nclass Local:\n    VERSION = 2',
    'for VERSION in [2]:\n    pass',
    'import math as VERSION',
    'def VERSION():\n    return 2',
    'class VERSION:\n    pass',
))
def test_implicit_local_scopes_do_not_write_same_spelled_global(kind, body):
    compile('VERSION = 1\ndef helper():\n' + indent(body, '    '), '<local-binding>', 'exec')
    assert not no_side_effects(effect_context(kind, body + '\nreturn {}'), {}, {'effect_scope': 'none'}).findings


@pytest.mark.parametrize(('body', 'rejected'), (
    ("if params:\n    inputs = {}\nelse:\n    inputs['x'] = 1", True),
    ("if params:\n    inputs['x'] = 1\nelse:\n    inputs = {}", True),
    ("alias = inputs\nif params:\n    alias = {}\nelse:\n    alias['x'] = 1", True),
    ("(inputs := {}) if params else inputs.update(x=1)", True),
    ("inputs.update(x=1) if params else (inputs := {})", True),
    ("match params:\n    case 1:\n        inputs = {}\n    case _:\n        inputs['x'] = 1", True),
    ("match params:\n    case {'value': inputs}:\n        pass\n    case _:\n        inputs['x'] = 1", False),
    ("try:\n    value = params['x']\nexcept ValueError:\n    inputs = {}\nexcept KeyError:\n    inputs['x'] = 1", True),
    ("try:\n    value = params['x']\nexcept ValueError as inputs:\n    pass\nexcept KeyError:\n    inputs['x'] = 1", True),
    ("match params:\n    case 1 if (inputs := {}):\n        pass\n    case _:\n        inputs['x'] = 1", False),
    ("try:\n    raise KeyError()\nexcept ((inputs := {}) or ValueError):\n    pass\nexcept KeyError:\n    inputs['x'] = 1", False),
    ("if (inputs := {}):\n    inputs['x'] = 1\nelse:\n    inputs['x'] = 1", False),
    ("inputs.update(x=1) if (inputs := {}) else inputs.update(x=2)", False),
    ("match (inputs := {}):\n    case 1:\n        inputs['x'] = 1\n    case _:\n        inputs['x'] = 1", False),
    ("if params:\n    inputs = {}\nelse:\n    inputs = {}\ninputs['x'] = 1", False),
    ("if params:\n    inputs = {}\nelse:\n    pass\ninputs['x'] = 1", False),
    ("if params:\n    if params['nested']:\n        inputs = {}\n    else:\n        inputs['x'] = 1\nelse:\n    inputs['x'] = 1", True),
))
def test_sibling_branches_share_entry_identity_but_not_local_rebinding(body, rejected):
    compile('def helper(inputs, params):\n' + indent(body, '    '), '<branch-binding>', 'exec')
    result = input_writes(context(body + '\nreturn {}'), {}, {})
    assert bool(result.findings) is rejected
    assert {f.code for f in result.findings} <= {'NODE.PURITY.INPUT_MUTATION'}
