"""Static independent exception-edge probes; inspected functions never executed."""
import argparse
import json
from pathlib import Path
import sys
from textwrap import indent

CASES = (
    ('tuple_lookup', "((alias := inputs), params['missing'], (alias := {}))", True),
    ('list_lookup', "[(alias := inputs), params['missing'], (alias := {})]", True),
    ('dict_lookup', "{'a': (alias := inputs), 'b': params['missing'], 'c': (alias := {})}", True),
    ('assign_tuple_lookup', "unused = ((alias := inputs), params['missing'], (alias := {}))", True),
    ('tuple_call', "((alias := inputs), noop(), (alias := {}))", True),
    ('tuple_attribute', "((alias := inputs), params.missing, (alias := {}))", True),
    ('clear_before_lookup_control', "((alias := inputs), (alias := {}), params['missing'])", False),
    ('separate_statements_control', "alias = inputs\nparams['missing']\nalias = {}", True),
)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--product', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    import vibeflow
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality.rules.effects import no_side_effects
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
    rows = []
    for label, expression, expected in CASES:
        for via_helper in (False, True):
            statement = 'sink(alias)' if via_helper else 'alias.pop("seed", None)'
            body = 'alias = {}\ntry:\n' + indent(expression, '    ') + '\nexcept Exception:\n    ' + statement + '\nreturn {}\n'
            text = ('def sink(payload):\n    payload.pop("seed", None)\n'
                    'def noop():\n    raise ValueError("probe")\nclass Task:\n    def run_pure(self, inputs, params):\n' + indent(body, '        '))
            compile(text, '/virtual/exception_alias.py', 'exec')
            file = PythonSourceFile.parse('/virtual/exception_alias.py', 'exception_alias', text)
            descriptor = NodeDescriptor('probe.task', 'Task', 'Exception path ownership probe.', '1', 'process', contract=NodeContractDescriptor())
            node = PythonSourceNode(descriptor, file.path, 'Task')
            sources = build_python_source_context((node,), (file,))
            context = RuleContext(subject={'kind':'node', 'type_key':'probe.task'}, target='python',
                facts={'source_context':sources, 'node_catalog':(), 'source_owners':()})
            result = no_side_effects(context, {}, {'effect_scope':'global_state'})
            actual = any('mutate inputs' in f.message for f in result.findings)
            rows.append({'case':label, 'via_helper':via_helper, 'source':text, 'expected':expected, 'actual':actual,
                'matched':result.state == 'completed' and actual == expected, 'state':result.state,
                'findings':[f.to_dict() for f in result.findings]})
    report = {'origin':vibeflow.__file__, 'count':len(rows), 'mismatches':sum(not r['matched'] for r in rows), 'rows':rows}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:report[k] for k in ('origin','count','mismatches')}))


if __name__ == '__main__':
    main()
