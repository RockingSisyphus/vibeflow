"""Review findings: correct lexical subjects without business-path proofs."""
from textwrap import indent
import pytest
from tests.targets.python.test_product_boundary import context
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.rules.node.input_writes import input_writes
from vibeflow.targets.python.rules.node.node_interface import node_interface
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
from vibeflow.targets.python.quality import PythonSource


@pytest.mark.parametrize('body', (
    'def values():\n    yield 1\nvalues = list(values())\nreturn {}',
    'async def values():\n    yield 1\nreturn {}',
    'class Helper:\n    def values(self):\n        yield 1\nreturn {}',
    'if params:\n    def values():\n        yield from [1]\nreturn {}',
))
def test_nested_generator_does_not_change_entry_abi(body):
    assert not node_interface(context(body), {}, {}).findings


@pytest.mark.parametrize('body', (
    'yield {}', 'yield from [{}]',
    'def values(value=(yield 1)):\n    return value\nreturn {}',
))
def test_yield_in_entry_or_its_definition_expression_remains_rejected(body):
    result = node_interface(context(body), {}, {})
    assert {f.code for f in result.findings} == {'NODE.CONTRACT.GENERATOR_RUN_PURE'}


@pytest.mark.parametrize(('body', 'rejected'), (
    ("inputs['x']: int", False),
    ("inputs['x']: int = 1", True),
    ("inputs['x'] = 1", True),
    ("del inputs['x']", True),
    ("inputs['items'].append(1)", True),
    ("inputs[inputs.pop('x')]: int", True),
    ("if (inputs := {'local': True}):\n    inputs['x'] = 1", False),
    ("while (inputs := {'local': True}):\n    inputs['x'] = 1\n    break", False),
    ("inputs['x'].append(1) if (inputs := {}) else None", False),
    ("for item in (inputs := []):\n    inputs.append(item)", False),
    ("if params:\n    inputs['x'] = 1", True),
    ("if params:\n    pass\nelse:\n    inputs['x'] = 1", True),
    ("for inputs in inputs['items'].pop():\n    pass", True),
    ("alias = inputs\nif (alias := {}):\n    alias['x'] = 1", False),
))
def test_finite_input_writes_use_actual_assignment_and_seen_rebinding(body, rejected):
    result = input_writes(context(body + '\nreturn {}'), {}, {})
    assert bool(result.findings) == rejected
    assert {f.code for f in result.findings} <= {'NODE.PURITY.INPUT_MUTATION'}


def effect_context(kind, body, prefix='VERSION = 1\n'):
    text = prefix + ('class Task:\n    def run_pure(self, inputs, params):\n' + indent(body, '        ')
                     if kind == 'node' else 'def helper():\n' + indent(body, '    ')) + '\n'
    parsed = PythonSourceFile.parse('/virtual/review.py', 'review', text)
    descriptor = NodeDescriptor(rulesets=(), id='example.task', display_name='Task', description='Review scope.',
                                version='1', flow_kind='process', contract=NodeContractDescriptor(), node_type="vibeflow.node")
    nodes = (PythonSourceNode(descriptor, parsed.path, 'Task'),) if kind == 'node' else ()
    facts = {'source_context': build_python_source_context(nodes, (parsed,)), 'node_definitions': (),
             'source_owners': ({'kind': kind, 'id': 'example.task', 'role': 'entry',
                               'path': parsed.path, 'symbol': 'Task' if kind == 'node' else ''},)}
    if kind == 'python_source':
        facts.update(python_source=PythonSource(parsed.module, 'review.py', parsed.path, text), source_file=parsed)
    elif kind == 'base_lib':
        facts.update(base_lib_file=parsed, resource_symbol='')
    elif kind == 'plugin':
        facts.update(resource_source_file=parsed, resource_symbol='')
    return RuleContext(subject={'kind': kind, 'id': 'example.task', "definition_id": 'example.task'},
                       target='python', facts=facts)


@pytest.mark.parametrize('kind', ('node', 'base_lib', 'plugin', 'python_source'))
@pytest.mark.parametrize('body', (
    'global VERSION\nvalue = VERSION\nreturn {}',
    'global NEW_VALUE\nreturn {}',
    'global VERSION\nVERSION: int\nreturn {}',
    'global VERSION\nclass Box:\n    VERSION = 2\nreturn {}',
    'value = 1\ndef helper():\n    nonlocal value\n    return value\nhelper()\nreturn {}',
    'value = 1\ndef helper():\n    nonlocal value\n    value += 1\nhelper()\nreturn {}',
    'VERSION = 1\ndef helper():\n    nonlocal VERSION\n    VERSION += 1\nhelper()\nreturn {}',
))
def test_declarations_and_local_closures_do_not_claim_shared_mutation(kind, body):
    assert not no_side_effects(effect_context(kind, body), {}, {'effect_scope': 'none'}).findings


@pytest.mark.parametrize('kind', ('node', 'base_lib', 'plugin', 'python_source'))
@pytest.mark.parametrize('body', (
    'global VERSION\nVERSION = 2\nreturn {}',
    'global VERSION\nVERSION: int = 2\nreturn {}',
    'global VERSION\nVERSION += 1\nreturn {}',
    'global VERSION\ndel VERSION\nreturn {}',
    'global VERSION\nVERSION, local = 2, 3\nreturn {}',
    'def helper():\n    global VERSION\n    VERSION = 2\nhelper()\nreturn {}',
    'class Box:\n    global VERSION\n    VERSION = 2\nreturn {}',
))
def test_real_module_global_writes_keep_effect_policy(kind, body):
    source = effect_context(kind, body)
    rejected = no_side_effects(source, {}, {'effect_scope': 'none'})
    assert rejected.findings
    assert {f.code for f in rejected.findings} <= {'NODE.PURITY.GLOBAL_STATE', 'BASE_LIB.GLOBAL_STATE', 'QUALITY.SIDE_EFFECT.CALL'}
    assert not no_side_effects(source, {}, {'effect_scope': 'global_state'}).findings


def test_nonlocal_alias_to_known_module_still_reports_actual_mutation():
    body = 'shared = sys\ndef helper():\n    nonlocal shared\n    shared.path = []\nhelper()\nreturn {}'
    result = no_side_effects(effect_context('node', body, 'import sys\n'), {}, {'effect_scope': 'none'})
    assert any(f.code == 'NODE.EFFECT.CALL_FORBIDDEN' for f in result.findings)
