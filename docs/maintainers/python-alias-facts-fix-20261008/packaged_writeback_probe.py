"""Isolated SDK -> RulePlan replay of input writeback and binding controls.

Use python -I -B with --source/--kernel, or an installed wheel interpreter.
No inspected implementation is executed; it is syntax-compiled and analyzed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from textwrap import indent
import traceback

# CASES is an inline literal, filled when this independent artifact is made.
CASES = (('nonlocal_assign', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias.pop('seed', None)", True), ('nonlocal_walrus', "alias = {}\ndef bind():\n    nonlocal alias\n    (alias := inputs)\nbind()\nalias.pop('seed', None)", True), ('nonlocal_get', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs.get('nested')\nbind()\nalias.pop('seed', None)", True), ('nonlocal_multilevel', "alias = {}\ndef middle():\n    def bind():\n        nonlocal alias\n        alias = inputs\n    bind()\nmiddle()\nalias.pop('seed', None)", True), ('nonlocal_nearest_local', "alias = {}\ndef middle():\n    alias = {}\n    def bind():\n        nonlocal alias\n        alias = inputs\n    bind()\nmiddle()\nalias.pop('seed', None)", False), ('global_assign', "def bind():\n    global alias\n    alias = inputs\nbind()\nalias.pop('seed', None)", True), ('global_walrus', "def bind():\n    global alias\n    (alias := inputs)\nbind()\nalias.pop('seed', None)", True), ('global_caller_local', "alias = {}\ndef bind():\n    global alias\n    alias = inputs\nbind()\nalias.pop('seed', None)", False), ('global_outer_closure', "global alias\nalias = inputs\ndef mutate():\n    alias.pop('seed', None)\nmutate()", True), ('global_middle_closure', "alias = {}\ndef middle():\n    global alias\n    alias = inputs\n    def mutate():\n        alias.pop('seed', None)\n    mutate()\nmiddle()", True), ('ordinary_child_local', "alias = {}\ndef bind():\n    alias = inputs\nbind()\nalias.pop('seed', None)", False), ('lambda_body_local', "alias = {}\nfn = lambda: (alias := inputs)\nfn()\nalias.pop('seed', None)", False), ('lambda_parameter', "(lambda inputs: inputs.pop('seed', None))({})", False), ('lambda_closure', "(lambda: inputs.pop('seed', None))()", True), ('function_default_walrus', "def bind(value=(alias := inputs)):\n    return value\nalias.pop('seed', None)", True), ('lambda_default_walrus', "fn = lambda value=(alias := inputs): value\nalias.pop('seed', None)", True), ('comp_default_walrus', "values = [lambda value=(alias := inputs): value for item in (0,)]\nalias.pop('seed', None)", True), ('comp_local_input_control', "alias = {}\nvalues = [lambda value=(alias := inputs): value for inputs in ({},)]\nalias.pop('seed', None)", False), ('nonlocal_comp', "alias = {}\ndef bind():\n    nonlocal alias\n    list(alias := inputs for item in (0,))\nbind()\nalias.pop('seed', None)", True), ('global_comp', "def bind():\n    global alias\n    values = [alias := inputs for item in (0,)]\nbind()\nalias.pop('seed', None)", True), ('nested_parameter_direct', "def mutate(payload):\n    payload.pop('seed', None)\nmutate(inputs)", True), ('nested_parameter_local_control', "def mutate(payload):\n    payload.pop('seed', None)\nmutate({})", False), ('nested_parameter_nonlocal_write', "alias = {}\ndef bind(payload):\n    nonlocal alias\n    alias = payload\nbind(inputs)\nalias.pop('seed', None)", True), ('nested_parameter_keyword_write', "alias = {}\ndef bind(*, payload):\n    nonlocal alias\n    alias = payload\nbind(payload=inputs)\nalias.pop('seed', None)", True), ('nested_parameter_global_write', "def bind(payload):\n    global alias\n    alias = payload\nbind(inputs)\nalias.pop('seed', None)", True), ('nested_parameter_fake_write', "alias = {}\ndef bind(payload):\n    nonlocal alias\n    alias = payload\nbind({})\nalias.pop('seed', None)", False), ('straight_overwrite', "alias = inputs\nalias = {}\nalias.pop('seed', None)", False), ('annotated_overwrite', "alias = inputs\nalias: dict = {}\nalias.pop('seed', None)", False), ('walrus_overwrite', "alias = inputs\n(alias := {})\nalias.pop('seed', None)", False), ('nonlocal_caller_overwrite', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias = {}\nalias.pop('seed', None)", False), ('global_caller_overwrite', "global alias\ndef bind():\n    global alias\n    alias = inputs\nbind()\nalias = {}\nalias.pop('seed', None)", False), ('constant_false', "alias = {}\nif False:\n    alias = inputs\nalias.pop('seed', None)", False), ('constant_false_else_owned', "alias = {}\nif False:\n    alias = {}\nelse:\n    alias = inputs\nalias.pop('seed', None)", True), ('constant_true_else_dead', "alias = {}\nif True:\n    alias = {}\nelse:\n    alias = inputs\nalias.pop('seed', None)", False), ('branch_owned_first', "if params['flag']:\n    alias = inputs\nelse:\n    alias = {}\nalias.pop('seed', None)", True), ('branch_owned_else', "if params['flag']:\n    alias = {}\nelse:\n    alias = inputs\nalias.pop('seed', None)", True), ('branch_both_clear', "alias = inputs\nif params['flag']:\n    alias = {}\nelse:\n    alias = {}\nalias.pop('seed', None)", False), ('loop_possible_write', "alias = {}\nfor item in ():\n    alias = inputs\nalias.pop('seed', None)", True), ('loop_clear_keeps_zero_iterations', "alias = inputs\nfor item in ():\n    alias = {}\nalias.pop('seed', None)", True), ('while_false', "alias = {}\nwhile False:\n    alias = inputs\nalias.pop('seed', None)", False), ('loop_next_iteration', "alias = {}\nfor item in params['items']:\n    alias.pop('seed', None)\n    alias = inputs", True), ('comp_clear_keeps_zero_iterations', "alias = inputs\nvalues = [(alias := {}) for item in ()]\nalias.pop('seed', None)", True), ('comp_next_iteration', "alias = {}\nvalues = [(alias.pop('seed', None), (alias := inputs)) for item in params['items']]", True), ('late_closure', "alias = {}\ndef mutate():\n    alias.pop('seed', None)\nalias = inputs\nmutate()", True), ('closure_after_clear', "alias = inputs\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nmutate()", False), ('global_closure_after_clear', "global alias\nalias = inputs\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nmutate()", False), ('late_bind_call', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nbind()\nmutate()", True), ('noncalled_binding_does_not_write', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nalias.pop('seed', None)", False), ('dead_binding_call_does_not_write', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nif False:\n    bind()\nalias.pop('seed', None)", False), ('noncalled_global_binding_does_not_write', "def bind():\n    global alias\n    alias = inputs\nalias.pop('seed', None)", False), ('late_bind_wrapper', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\ndef middle():\n    bind()\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nmiddle()\nmutate()", True), ('late_bind_mutual_definition', "alias = {}\ndef first():\n    second()\ndef second():\n    nonlocal alias\n    alias = inputs\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nfirst()\nmutate()", True), ('possible_bind_branch', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nif params['flag']:\n    bind()\nalias.pop('seed', None)", True), ('possible_bind_reverse_branch', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nif params['flag']:\n    pass\nelse:\n    bind()\nalias.pop('seed', None)", True), ('bind_branch_both_clear', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nif params['flag']:\n    alias = {}\nelse:\n    alias = {}\nalias.pop('seed', None)", False), ('late_global_bind', "def bind():\n    global alias\n    alias = inputs\nglobal alias\nalias = {}\ndef mutate():\n    alias.pop('seed', None)\nbind()\nmutate()", True), ('ifexp_owned_first', "alias = {}\n(alias := inputs) if params['flag'] else (alias := {})\nalias.pop('seed', None)", True), ('ifexp_owned_else', "alias = {}\n(alias := {}) if params['flag'] else (alias := inputs)\nalias.pop('seed', None)", True), ('ifexp_both_clear', "alias = inputs\n(alias := {}) if params['flag'] else (alias := {})\nalias.pop('seed', None)", False), ('and_optional_clear', "alias = inputs\nparams['flag'] and (alias := {})\nalias.pop('seed', None)", True), ('or_optional_clear', "alias = inputs\nparams['flag'] or (alias := {})\nalias.pop('seed', None)", True), ('boolean_first_clear_executes', "alias = inputs\n(alias := {}) and params['flag']\nalias.pop('seed', None)", False), ('try_handler_clear', "alias = inputs\ntry:\n    params['flag']\nexcept KeyError:\n    alias = {}\nalias.pop('seed', None)", True), ('try_normal_clear_handler_preserves', "alias = inputs\ntry:\n    params['flag']\n    alias = {}\nexcept KeyError:\n    pass\nalias.pop('seed', None)", True), ('try_both_clear', "alias = inputs\ntry:\n    params['flag']\n    alias = {}\nexcept KeyError:\n    alias = {}\nalias.pop('seed', None)", False), ('try_late_handler_owned', "alias = {}\ntry:\n    params['flag']\nexcept KeyError:\n    alias = inputs\nexcept ValueError:\n    alias = {}\nalias.pop('seed', None)", True), ('try_finally_clear', "alias = inputs\ntry:\n    params['flag']\nfinally:\n    alias = {}\nalias.pop('seed', None)", False), ('try_body_intermediate_owned', "alias = {}\ntry:\n    alias = inputs\n    params['flag']\n    alias = {}\nexcept KeyError:\n    alias.pop('seed', None)", True), ('match_optional_clear', "alias = inputs\nmatch params['flag']:\n    case True:\n        alias = {}\nalias.pop('seed', None)", True), ('match_owned_first', "alias = {}\nmatch params['flag']:\n    case True:\n        alias = inputs\n    case False:\n        alias = {}\nalias.pop('seed', None)", True), ('match_owned_last', "alias = {}\nmatch params['flag']:\n    case True:\n        alias = {}\n    case False:\n        alias = inputs\nalias.pop('seed', None)", True), ('match_unconditional_clear', "alias = inputs\nmatch params['flag']:\n    case _:\n        alias = {}\nalias.pop('seed', None)", False), ('match_guard_write_reaches_later_case', "alias = {}\nmatch params['flag']:\n    case True if (alias := inputs) and False:\n        pass\n    case _:\n        alias.pop('seed', None)", True), ('captured_get_owned_receiver', "alias = inputs\nborrowed = alias.get((alias := 'seed'), {})\nborrowed.pop('seed', None)", True), ('captured_get_local_receiver', "alias = {}\nborrowed = alias.get((alias := inputs) and 'seed', {})\nborrowed.pop('seed', None)", False), ('captured_get_actual_argument', "def mutate(payload):\n    payload.pop('seed', None)\nalias = inputs\nmutate(alias.get((alias := 'seed'), {}))", True), ('noncalled_clear_does_not_erase', "alias = inputs\ndef clear():\n    nonlocal alias\n    alias = {}\nalias.pop('seed', None)", True), ('mutation_form_0', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias['seed'] = 1", True), ('mutation_form_1', 'alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias.seed = 1', True), ('mutation_form_2', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\ndel alias['seed']", True), ('mutation_form_3', 'alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\ndel alias.seed', True), ('mutation_form_4', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias['seed'] += 1", True), ('mutation_form_5', 'alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias.seed += 1', True), ('mutation_form_6', 'alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias.update({})', True), ('mutation_form_7', 'alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nalias.clear()', True), ('mutation_form_8', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\n[item for alias['seed'] in (0,)]", True), ('mutation_form_9', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\n{item for alias['seed'] in (0,)}", True), ('mutation_form_10', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\n{item: item for alias['seed'] in (0,)}", True), ('mutation_form_11', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\nlist(item for alias['seed'] in (0,))", True), ('mutation_form_12', "alias = {}\ndef bind():\n    nonlocal alias\n    alias = inputs\nbind()\n(alias := inputs).pop('seed', None)", True), ('try_prefix_helper', 'alias = {}\ntry:\n    alias = inputs\n    fallible()\n    alias = {}\nexcept Exception:\n    sink(alias)', True))


def replay():
    parser = argparse.ArgumentParser(description=__doc__)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument('--source', type=Path)
    selected.add_argument('--kernel', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    options = parser.parse_args()
    report = {'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'observations':[], 'probe_error':None}
    try:
        if options.source:
            product = options.source.resolve(strict=True)
            kind = 'source_snapshot'
            sys.path.insert(0, str(product))
        elif options.kernel:
            product = options.kernel.resolve(strict=True)
            kind = 'kernel_zip'
            sys.path.insert(0, str(product))
        else:
            distribution = importlib.metadata.distribution('vibeflow')
            assert distribution.read_text('WHEEL')
            assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info', {}).get('editable')
            product = Path(distribution.locate_file('')).resolve(strict=True)
            kind = 'installed_wheel'
        report['product'] = {'kind':kind, 'path':str(product)}
        from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
        from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
        from vibeflow.targets.python.sdk import RuleCall, ruleset
        from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
        from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
        from vibeflow.targets.python.quality.source_analysis import input_tracking
        from vibeflow.targets.shared.bindings import native_binding
        from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
        catalog = load_builtin_plugins('python').catalogs
        definitions = {item.id:item for item in catalog.rules}
        handlers = {item.id:native_binding(catalog, 'rule', item.id) for item in catalog.rules}
        selection = ruleset(id='probe.input_writeback', calls=[RuleCall(id='effects',
            rule_id='vibeflow.no_side_effects', params={'effect_scope':'global_state'})]).descriptor
        plan = complete_source_policy_plan(compile_ruleset(selection, rules=definitions,
            rulesets={selection.id:selection}), handlers=handlers)
        for label, body, expected in CASES:
            text = ('alias = None\ndef sink(payload):\n    return payload.pop("seed", None)\n'
                    'class Task:\n    def run_pure(self, inputs, params):\n'
                    + indent(body + '\nreturn {}\n', '        '))
            compile(text, '/virtual/input_writeback.py', 'exec')
            source = PythonSourceFile.parse('/virtual/input_writeback.py', 'input_writeback', text)
            before = ast.dump(source._tree)
            descriptor = NodeDescriptor(type_key='example.task', display_name='Task', description='Input writeback.',
                version='1', flow_kind='process', contract=NodeContractDescriptor())
            node = PythonSourceNode(descriptor, source.path, 'Task')
            sources = build_python_source_context((node,), (source,))
            context = RuleContext(subject={'kind':'node', 'type_key':'example.task'}, target='python',
                facts={'source_context':sources, 'node_catalog':(), 'source_owners':()})
            execution = execute_rule_plan(plan, context, handlers=handlers)
            result = execution.results['effects']
            findings = [item.to_dict() for item in result.findings]
            mutation = any('mutate inputs' in item['message'] for item in findings)
            effect = result.to_dict()['records']['effect_policy']['value']
            unchanged = before == ast.dump(source._tree)
            module_globals = sorted(item.name for item in sources.symbols if item.kind == 'global')
            matched = mutation == expected and result.state == 'completed' and unchanged and 'alias' in module_globals
            matched = matched and effect['effect_scope'] == 'global_state'
            report['observations'].append({'case':label, 'source':text, 'expected_mutation':expected,
                'actual_mutation':mutation, 'matched':matched, 'result_state':result.state, 'effect_policy':effect,
                'ast_unchanged':unchanged, 'module_globals':module_globals, 'findings':findings,
                'formal_input_parameters':{key:sorted(names) for key,names in input_tracking.source_input_parameters(sources,node).items()}})
        origin = Path(input_tracking.__file__)
        report['input_tracking'] = str(origin)
        if kind == 'kernel_zip':
            import zipfile
            with zipfile.ZipFile(product) as archive:
                source_bytes = archive.read('vibeflow/targets/python/quality/source_analysis/input_tracking.py')
        else:
            source_bytes = origin.read_bytes()
        report['input_tracking_sha256'] = hashlib.sha256(source_bytes).hexdigest()
        loaded = {name:str(getattr(module, '__file__', '')) for name,module in sys.modules.items()
                  if name == 'vibeflow' or name.startswith('vibeflow.')}
        prefix = str(product / 'vibeflow') + '/'
        foreign = {name:path for name,path in loaded.items() if not path or not path.startswith(prefix)}
        report['loaded_product_modules'] = loaded
        report['loaded_module_count'] = len(loaded)
        report['foreign_product_modules'] = foreign
        assert not foreign, foreign
    except BaseException:
        report['probe_error'] = traceback.format_exc()
    report['case_count'] = len(report['observations'])
    report['matching_count'] = sum(item['matched'] for item in report['observations'])
    report['pass'] = report['probe_error'] is None and report['case_count'] == len(CASES) and report['matching_count'] == len(CASES)
    options.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key:report.get(key) for key in ('product', 'case_count', 'matching_count', 'pass',
        'input_tracking_sha256', 'loaded_module_count', 'foreign_product_modules', 'probe_error')}, ensure_ascii=False))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(replay())
