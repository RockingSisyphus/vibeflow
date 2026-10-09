"""Independent F03/F04 replay through official CLI and public ordinary RulePlan.

Use python -I -B. Select --source (root containing vibeflow), --kernel (ZIP),
or an installed non-editable wheel interpreter with neither option. Inspected
business bodies are validated, never executed. Fixed expectations stay the same
in before mode: it records the observed mismatch, rather than relaxing policy.
"""
from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from textwrap import indent
import traceback
import zipfile

POLICY = {'imports': {key: [] for key in ('allowed_roots', 'banned_roots', 'allowed_modules', 'banned_modules')}}
KINDS = ('python_source', 'node', 'base_lib', 'plugin')
FORMS = {
    'list': '[(alias := {value}) for {target} in objects]',
    'set': '{{(alias := {value}) for {target} in objects}}',
    'dict': '{{0: (alias := {value}) for {target} in objects}}',
    'generator': 'list((alias := {value}) for {target} in objects)',
    'lambda_default': '[(lambda value=(alias := {value}): value) for {target} in objects]',
    'nested_comp': '[[(alias := {value}) for {target} in objects] for row in objects]',
}


@dataclass(frozen=True)
class Case:
    name: str
    kind: str
    family: str
    body: str
    scope: str
    expected_host: bool
    expected_input: bool
    expected_denied: bool
    placement: str = 'method'


def cases():
    rows = []
    for kind in KINDS:
        for shape, form in FORMS.items():
            for variant, target, value, host in (('local_sys', 'sys', 'sys', False), ('local_item', 'item', 'item', False), ('host_sys', 'item', 'sys', True)):
                body = form.format(value=value, target=target) + '\nalias.argv\n'
                rows.append(Case('.'.join((kind, 'F03', shape, variant)), kind, 'F03', body, 'none', host, False, host))
        for variant, target, value, host in (('local_sys', 'sys', 'sys', False), ('local_item', 'item', 'item', False), ('host_sys', 'item', 'sys', True)):
            body = FORMS['list'].format(value=value + '.stdout', target=target) + '\nalias.closed\n'
            rows.append(Case('.'.join((kind, 'F03', 'attribute', variant)), kind, 'F03', body, 'none', host, False, host))
        rows.append(Case(kind + '.F03.direct_local_control', kind, 'F03', '[sys.argv for sys in objects]\n', 'none', False, False, False))
        rows.append(Case(kind + '.F03.direct_host_control', kind, 'F03', 'sys.argv\n', 'none', True, False, True))
        # Unknown .write remains an ordinary I/O leaf. Identity repair must not
        # invent a sys origin, nor grant an unknown receiver extra permissions.
        for target in ('sys', 'item'):
            for scope in ('none', 'python_io'):
                body = FORMS['list'].format(value=target + '.stdout', target=target) + '\nalias.write("probe")\n'
                rows.append(Case('.'.join((kind, 'unknown_io', target, scope)), kind, 'unknown_io', body, scope, False, False, scope == 'none'))
    for placement in ('method', 'module_helper'):
        for declaration in ('nonlocal', 'global'):
            for endpoint in ('direct', 'helper'):
                for value, owned in (('inputs', True), ('{}', False)):
                    body = 'alias = {}\n' if declaration == 'nonlocal' else ''
                    body += 'def inner():\n    ' + declaration + ' alias\n    alias = ' + value + '\ninner()\n'
                    body += 'alias.pop("seed", None)\n' if endpoint == 'direct' else 'sink(alias)\n'
                    name = '.'.join(('node', 'F04', placement, declaration, endpoint, 'owned' if owned else 'local'))
                    rows.append(Case(name, 'node', 'F04', body, 'global_state', False, owned, owned, placement))
    for endpoint in ('direct', 'helper'):
        body = 'alias = {}\ndef inner():\n    global alias\n    alias = inputs\ninner()\n'
        body += 'alias.pop("seed", None)\n' if endpoint == 'direct' else 'sink(alias)\n'
        rows.append(Case('node.F04.same_named_caller_local.' + endpoint, 'node', 'F04', body, 'global_state', False, False, False))
    rows.append(Case('node.F04.lambda_parameter_local', 'node', 'F04', '(lambda inputs: inputs.pop("seed", None))({})\n', 'global_state', False, False, False))
    rows.append(Case('node.F04.comprehension_local_inputs', 'node', 'F04', '[(alias := inputs) for inputs in ({},)]\nalias.pop("seed", None)\n', 'global_state', False, False, False))
    assert len(rows) == 128 and len({r.name for r in rows}) == 128
    return rows


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def host_source(case, function='inspect_values', decorator=''):
    return 'import sys\n' + decorator + 'def ' + function + '(objects=()):\n' + indent(case.body + 'return None\n', '    ')


def project(path, case):
    path.mkdir(parents=True)
    write(path / 'vibeflow_config.jsonc', {'roots': [{'id': 'alias-facts', 'path': '.'}]})
    write(path / 'vibeflow_project.jsonc', {'project_target': 'python'})
    write(path / 'workflow.jsonc', {'plugins': [{'source': {'kind': 'file', 'ref': 'plugin.py'}}], 'pipeline': {
        'inputs': [], 'outputs': [], 'nodes': [
            {'id': 'start', 'type_used': 'probe.start', 'display_name': 'Start', 'description': 'Starts.'},
            {'id': 'task', 'type_used': 'probe.task', 'display_name': 'Task', 'description': 'Checks the selected resource.'},
            {'id': 'end', 'type_used': 'probe.start', 'display_name': 'End', 'description': 'Ends.'}],
        'edges': [['start', 'task'], ['task', 'end']]}})
    selected = 'selected = ruleset(id="probe.effects", calls=' + repr([{'id': 'effects', 'rule_id': 'vibeflow.no_side_effects', 'params': {'effect_scope': case.scope, 'policy': POLICY}}]) + ')\n'
    node_source = 'from vibeflow.targets.python.sdk import node\n'
    task_body = ''
    imports = 'from vibeflow.targets.python.sdk import Plugin, ruleset\nfrom node_resource import Start, Task\n'
    resources, options = '[Start, Task, selected]', ''
    if case.kind == 'node':
        if case.family == 'F04':
            node_source += 'alias = None\ndef sink(payload):\n    payload.pop("seed", None)\n'
            if case.placement == 'module_helper':
                node_source += 'def mutate_inputs(inputs):\n' + indent(case.body + 'return None\n', '    ')
                task_body = 'mutate_inputs(inputs)\n'
            else:
                task_body = case.body
        else:
            node_source += host_source(case)
            task_body = 'inspect_values(params.get("objects", ()))\n'
        offender = path / 'node_resource.py'
    elif case.kind == 'base_lib':
        node_source += 'from library import calculate\n'
        library = 'from vibeflow.targets.python.sdk import base_lib\n' + host_source(case, 'calculate', '@base_lib(id="probe.library", rulesets=["probe.effects"])\n')
        offender = path / 'library.py'
        offender.write_text(library)
        imports += 'from library import calculate\n'
        resources = '[Start, Task, calculate, selected]'
        task_body = 'calculate()\n'
    else:
        offender = path / 'runtime_resource.py'
        offender.write_text(host_source(case) + '\ndef create_runtime(context):\n    inspect_values()\n    return Runtime()\n\nclass Runtime:\n    pass\n')
        imports += 'from runtime_resource import create_runtime\n'
        options = ', runtime=create_runtime, rulesets=["probe.effects"]'
    node_source += '\n@node(type_key="probe.task", rulesets=' + repr(['probe.effects'] if case.kind == 'node' else []) + (', base_libs=["probe.library"]' if case.kind == 'base_lib' else '') + ', contract={})\nclass Task:\n    def run_pure(self, inputs, params):\n' + indent(task_body + 'return {}\n', '        ')
    node_source += '\n@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})\nclass Start:\n    def run_pure(self, inputs, params):\n        return {}\n'
    (path / 'node_resource.py').write_text(node_source)
    (path / 'plugin.py').write_text(imports + selected + 'plugin = Plugin(id="probe", resources=' + resources + options + ', declaration_rulesets=[])\n')
    return offender


def selected_findings(payload):
    result = []
    def visit(value):
        if isinstance(value, dict):
            if value.get('definition_id') == 'vibeflow.no_side_effects' and 'source_location' in value and value not in result:
                result.append(value)
            for key, item in value.items():
                if key not in ('source_code', 'resources', 'definitions'):
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)
    visit(payload)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument('--source', type=Path)
    selection.add_argument('--kernel', type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--expect', choices=('before', 'fixed'), required=True)
    args = parser.parse_args()
    report = {'expected_state': args.expect, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observations': [], 'probe_error': None}
    try:
        if args.source:
            product, kind = args.source.resolve(strict=True), 'source_snapshot'
        elif args.kernel:
            product, kind = args.kernel.resolve(strict=True), 'kernel_zip'
        else:
            distribution = importlib.metadata.distribution('vibeflow')
            assert distribution.read_text('WHEEL'), 'Wheel metadata is required'
            assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info', {}).get('editable'), 'Editable install cannot provide wheel evidence'
            product, kind = Path(distribution.locate_file('')).resolve(strict=True), 'installed_wheel'
        expected_root = str(product / 'vibeflow') + '/'
        sys.path.insert(0, str(product))
        import vibeflow
        from vibeflow.core.rules import RuleCall, RuleContext, RulesetDescriptor, compile_ruleset, execute_rule_plan
        from vibeflow.targets.python.quality import PythonSource
        from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
        from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context
        from vibeflow.targets.shared.bindings import native_binding
        from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
        assert str(vibeflow.__file__).startswith(expected_root)
        report['product'] = {'kind': kind, 'path': str(product), 'origin': str(vibeflow.__file__)}
        if args.kernel:
            report['product']['sha256'] = hashlib.sha256(product.read_bytes()).hexdigest()
        def product_hashes():
            if args.kernel:
                with zipfile.ZipFile(product) as archive:
                    return {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist() if name.startswith('vibeflow/') and not name.endswith('/')}
            directory = product / 'vibeflow'
            return {'vibeflow/' + path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.rglob('*') if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc', '.pyo')}
        report['product_files_sha256'] = product_hashes()
        catalog = load_builtin_plugins('python').catalogs
        rules = {item.id: item for item in catalog.rules}
        handlers = {item.id: native_binding(catalog, 'rule', item.id) for item in catalog.rules}
        bootstrap = "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from vibeflow.tooling.application.python.cli import main;code=main(json.loads(sys.argv[2]));modules={n:str(getattr(m,'__file__','')) for n,m in sys.modules.items() if n=='vibeflow' or n.startswith('vibeflow.')};expected=str(Path(sys.argv[1])/'vibeflow')+'/';Path(sys.argv[3]).write_text(json.dumps({'origin':modules['vibeflow'],'loaded_module_count':len(modules),'foreign_product_modules':{n:p for n,p in modules.items() if not p or not p.startswith(expected)}}));raise SystemExit(code)"
        for case in cases():
            work = args.work.resolve() / case.name
            if case.kind == 'python_source':
                work.mkdir(parents=True)
                offender = work / 'ordinary.py'
                offender.write_text(host_source(case))
                text = offender.read_text()
                source = PythonSource('ordinary', 'ordinary.py', str(offender), text)
                source_file = PythonSourceFile.parse(str(offender), 'ordinary', text)
                context = RuleContext(subject={'kind': 'python_source', 'id': 'ordinary.py'}, target='python', facts={'python_source': source, 'source_file': source_file, 'python_sources': ((source, source_file),), 'source_context': build_python_source_context((), (source_file,))})
                descriptor = RulesetDescriptor('probe.alias_facts', calls=(RuleCall('effects', rule_id='vibeflow.no_side_effects', params={'effect_scope': case.scope, 'policy': POLICY}),))
                plan = complete_source_policy_plan(compile_ruleset(descriptor, rules=rules, rulesets={descriptor.id: descriptor}), handlers=handlers)
                result = execute_rule_plan(plan, context, handlers=handlers)
                payload = result.to_dict(); write(work / 'quality.json', payload)
                findings, status, code, origin = payload['findings'], result.status, None, None
                route = 'public Core compile_ruleset/execute_rule_plan native PythonSource binding'
            else:
                offender = project(work, case)
                argv = ['validate', '--workspace', str(work / 'vibeflow_config.jsonc'), '--config', str(work / 'workflow.jsonc'), '--json']
                process = subprocess.run([sys.executable, '-I', '-B', '-c', bootstrap, str(product), json.dumps(argv), str(work / 'origin.json')], cwd=work, capture_output=True, text=True, timeout=60)
                (work / 'stdout.txt').write_text(process.stdout); (work / 'stderr.txt').write_text(process.stderr)
                payload = json.loads(process.stdout); write(work / 'cli.json', payload)
                findings, status, code = selected_findings(payload), payload.get('status'), process.returncode
                origin = json.loads((work / 'origin.json').read_text()); assert not origin['foreign_product_modules']
                route = 'vibeflow.tooling.application.python.cli.main(validate)'
            tree = ast.parse(offender.read_text()); compile(tree, str(offender), 'exec')
            relevant = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr in ('argv', 'stdout', 'closed', 'write', 'pop')]
            locations = [{'path': str(offender), 'line': node.lineno, 'column': node.col_offset + 1} for node in relevant]
            located = [finding for finding in findings if finding.get('source_location') in locations]
            host = [finding for finding in located if 'banned process argument access:' in finding['message'] or 'banned terminal stream access:' in finding['message'] or 'banned call: sys.' in finding['message']]
            owned = [finding for finding in located if 'mutate inputs' in finding['message']]
            ordinary_io = [finding for finding in located if 'banned call:' in finding['message'] and finding not in host]
            expected_status = ('CONCERNS' if case.kind == 'python_source' else 'FAIL') if case.expected_denied else 'PASS'
            public_match = status == expected_status and (code is None or code == (1 if case.expected_denied else 0))
            semantic_match = bool(host) == case.expected_host and bool(owned) == case.expected_input and bool(located) == case.expected_denied and public_match
            report['observations'].append({'case': case.name, 'kind': case.kind, 'family': case.family, 'scope': case.scope, 'placement': case.placement, 'source_path': str(offender), 'source': offender.read_text(), 'entrypoint': route, 'expected_host_diagnostic': case.expected_host, 'actual_host_diagnostic': bool(host), 'expected_input_diagnostic': case.expected_input, 'actual_input_diagnostic': bool(owned), 'expected_denied': case.expected_denied, 'actual_denied': bool(located), 'expected_status': expected_status, 'status': status, 'exit_code': code, 'matched': semantic_match, 'findings': findings, 'matching_host_findings': host, 'matching_input_findings': owned, 'ordinary_io_findings': ordinary_io, 'expression_locations': locations, 'cli_product': origin})
        loaded = {name: str(getattr(module, '__file__', '')) for name, module in sys.modules.items() if name == 'vibeflow' or name.startswith('vibeflow.')}
        report['loaded_product_modules'] = loaded
        report['foreign_product_modules'] = {name: path for name, path in loaded.items() if not path or not path.startswith(expected_root)}
        assert not report['foreign_product_modules']
        report['product_files_sha256_after'] = product_hashes()
        assert report['product_files_sha256'] == report['product_files_sha256_after'], 'Selected product changed during replay'
        rows = report['observations']
        report['summary'] = {'cases': len(rows), 'matched': sum(row['matched'] for row in rows), 'mismatches': sum(not row['matched'] for row in rows), 'ordinary_public_cases': sum(row['kind'] == 'python_source' for row in rows), 'official_cli_cases': sum(row['kind'] != 'python_source' for row in rows), 'by_family': {family: {'cases': sum(row['family'] == family for row in rows), 'mismatches': sum(row['family'] == family and not row['matched'] for row in rows)} for family in ('F03', 'F04', 'unknown_io')}}
        report['expected_state_observed'] = report['summary']['mismatches'] == 0 if args.expect == 'fixed' else report['summary']['mismatches'] > 0
    except Exception:
        report['probe_error'] = traceback.format_exc(); report['expected_state_observed'] = False
    write(args.report.resolve(), report)
    print(json.dumps({key: report.get(key) for key in ('summary', 'expected_state_observed', 'probe_error')}, ensure_ascii=False))
    return 0 if report['expected_state_observed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
