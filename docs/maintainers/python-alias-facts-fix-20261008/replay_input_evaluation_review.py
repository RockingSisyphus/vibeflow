"""Replay preserved independent ownership snippets through one selected product.

Use python -I -B, --source/--kernel, or a noneditable installed wheel.
The original inline cases and expectations are extracted unchanged. Inspected
business implementations are syntax-compiled and analyzed, never executed.
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
import zipfile


def product_hashes(product, kind):
    if kind == 'kernel_zip':
        with zipfile.ZipFile(product) as archive:
            return {name: hashlib.sha256(archive.read(name)).hexdigest()
                    for name in archive.namelist()
                    if name.startswith('vibeflow/') and not name.endswith('/')}
    directory = product / 'vibeflow'
    return {'vibeflow/' + path.relative_to(directory).as_posix():
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob('*')
            if path.is_file() and '__pycache__' not in path.parts
            and path.suffix not in ('.pyc', '.pyo')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--source', type=Path)
    selection.add_argument('--kernel', type=Path)
    parser.add_argument('--review', choices=('evaluation12', 'nested_clear3', 'writeback_exits3', 'writeback_exits5'), required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--expect', choices=('before', 'fixed'), default='fixed')
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    names = {'evaluation12': 'original_review_input_evaluation_order.py',
             'nested_clear3': 'original_review_nested_clear.py',
             'writeback_exits3': 'original_review_writeback_exits.py',
             'writeback_exits5': 'original_review_writeback_exits5.py'}
    original = directory / names[args.review]
    manifest = json.loads((directory / 'additional-independent-probes.json').read_text())
    protected = next(row for row in manifest if Path(row['preserved']).name == original.name)
    original_bytes = original.read_bytes()
    assert hashlib.sha256(original_bytes).hexdigest() == protected['sha256']
    tree = ast.parse(original_bytes, str(original))
    case_name = 'CASES' if args.review == 'evaluation12' else 'cases'
    literal = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == case_name
                           for target in node.targets))
    cases = ast.literal_eval(literal)
    if args.source:
        product, kind = args.source.resolve(strict=True), 'source_snapshot'
    elif args.kernel:
        product, kind = args.kernel.resolve(strict=True), 'kernel_zip'
    else:
        distribution = importlib.metadata.distribution('vibeflow')
        assert distribution.read_text('WHEEL')
        assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info', {}).get('editable')
        product, kind = Path(distribution.locate_file('')).resolve(strict=True), 'installed_wheel'
    sys.path.insert(0, str(product))
    before = product_hashes(product, kind)
    report = {'product': {'kind': kind, 'path': str(product)}, 'review': args.review,
              'original_script_sha256': protected['sha256'],
              'original_cases_and_expectations_modified': False,
              'expected_state': args.expect, 'product_files_sha256': before,
              'rows': [], 'probe_error': None}
    try:
        import vibeflow
        from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
        from vibeflow.core.rules import RuleContext
        from vibeflow.targets.python.quality.rules.effects import no_side_effects
        from vibeflow.targets.python.quality.source_context import (
            PythonSourceFile, PythonSourceNode, build_python_source_context)
        from vibeflow.targets.python.quality.source_analysis.input_tracking import source_input_parameters
        report['product']['origin'] = vibeflow.__file__
        baseline = json.loads((directory / 'nested-call-clear-before-5b9f976-01.json').read_text())
        baseline_actual = {row['case']: row['actual'] for row in baseline['rows']}
        for label, body, expected in cases:
            if args.review == 'evaluation12':
                text = "def sink(payload,other=None):\n    payload.pop('seed',None)\nclass Task:\n    def run_pure(self,inputs,params):\n" + indent(body + '\nreturn {}\n', '        ')
                path, module = '/virtual/evaluation_order.py', 'evaluation_order'
            else:
                text = 'class Task:\n    def run_pure(self,inputs,params):\n' + indent(body + '\nreturn {}\n', '        ')
                path, module = '/virtual/writeback_summary.py', 'writeback_summary'
            compile(text, path, 'exec')
            parsed = PythonSourceFile.parse(path, module, text)
            descriptor = NodeDescriptor(type_key='example.task', display_name='Task',
                                        description='Independent ownership replay.', version='1',
                                        flow_kind='process', contract=NodeContractDescriptor())
            node = PythonSourceNode(descriptor, parsed.path, 'Task')
            sources = build_python_source_context((node,), (parsed,))
            result = no_side_effects(RuleContext(subject={'kind': 'node', 'type_key': 'example.task'},
                                     target='python', facts={'source_context': sources,
                                                            'node_catalog': (), 'source_owners': ()}),
                                     {}, {'effect_scope': 'global_state'})
            actual = any('mutate inputs' in finding.message for finding in result.findings)
            completed = result.state == 'completed'
            # General nested clear summaries are an existing conservative boundary.
            # Preserve the original desired expectation and compare this one control
            # with the immutable HEAD observation; only the new transient-owned
            # regression and uncalled control are required to match original intent.
            existing_boundary = args.review == 'nested_clear3' and label == 'called_nested_clear'
            accepted = completed and actual == (baseline_actual[label] if existing_boundary else expected)
            report['rows'].append({'case': label, 'source': text, 'expected': expected,
                                   'actual': actual, 'matched': completed and actual == expected,
                                   'existing_conservative_boundary': existing_boundary,
                                   'regression_check_matched': accepted,
                                   'result_state': result.state,
                                   'parameter_seeds': {key: sorted(value) for key, value in source_input_parameters(sources, node).items()},
                                   'findings': [finding.to_dict() for finding in result.findings],
                                   'calls': [{'source': ref.source, 'target': ref.target, 'line': ref.line, 'column': ref.column}
                                             for ref in sources.references if ref.kind == 'call']})
    except BaseException:
        report['probe_error'] = traceback.format_exc()
    after = product_hashes(product, kind)
    report['product_files_sha256_after'] = after
    report['changed_product_files'] = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
    loaded = {name: str(getattr(module, '__file__', '')) for name, module in sys.modules.items()
              if name == 'vibeflow' or name.startswith('vibeflow.')}
    prefix = str(product / 'vibeflow') + '/'
    report['loaded_product_modules'] = loaded
    report['foreign_product_modules'] = {name: path for name, path in loaded.items() if not path or not path.startswith(prefix)}
    report['original_script_unchanged'] = original.read_bytes() == original_bytes
    report['count'] = len(report['rows'])
    report['mismatches'] = sum(not row['matched'] for row in report['rows'])
    report['regression_check_mismatches'] = sum(not row['regression_check_matched'] for row in report['rows'])
    report['input_tracking_sha256'] = before.get('vibeflow/targets/python/quality/source_analysis/input_tracking.py')
    good = report['probe_error'] is None and report['count'] == len(cases) and not report['changed_product_files'] and not report['foreign_product_modules'] and report['original_script_unchanged']
    report['pass'] = good and (args.expect == 'before' or report['regression_check_mismatches'] == 0)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('review', 'count', 'mismatches', 'regression_check_mismatches', 'pass', 'input_tracking_sha256', 'foreign_product_modules', 'probe_error')}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
