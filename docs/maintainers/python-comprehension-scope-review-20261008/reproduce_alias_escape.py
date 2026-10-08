"""Independent static probes for comprehension alias identity; no business execution."""
import argparse
import json
from pathlib import Path
import sys
from textwrap import indent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--kernel', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.kernel:
        sys.path.insert(0, str(args.kernel.resolve()))
    import vibeflow
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality import PythonSource
    from vibeflow.targets.python.quality.rules.effects import no_side_effects
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
    cases = [
        ('local_sys_escape', '[(alias := sys) for sys in objects]\nreturn alias.argv', False),
        ('local_sys_renamed', '[(alias := item) for item in objects]\nreturn alias.argv', False),
        ('local_sys_attribute', '[(alias := sys.stdout) for sys in objects]\nreturn alias.write("a")', False),
        ('real_sys_escape', '[(alias := sys) for item in objects]\nreturn alias.argv', True),
        ('local_sys_nested_lambda', '[(lambda value=(alias := sys): value) for sys in objects]\nreturn alias.argv', False),
        ('local_sys_nested_comp', '[[(alias := sys) for sys in objects] for item in objects]\nreturn alias.argv', False),
        ('local_sys_import_as', '[(alias := process) for process in objects]\nreturn alias.argv', False),
        ('local_sys_direct_control', 'return [sys.argv for sys in objects]', False),
        ('local_inputs_escape', '[(alias := inputs) for inputs in objects]\nalias.pop("seed", None)\nreturn {}', False),
        ('real_inputs_escape', '[(alias := inputs) for item in objects]\nalias.pop("seed", None)\nreturn {}', True),
        ('nonlocal_inputs_direct', 'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs\ninner()\nalias.pop("seed", None)\nreturn {}', True),
        ('global_inputs_direct', 'def inner():\n    global alias\n    alias = inputs\ninner()\nalias.pop("seed", None)\nreturn {}', True),
    ]
    rows = []
    for label, body, expected in cases:
        for kind in ('python_source', 'node', 'base_lib', 'plugin'):
            if 'inputs' in label and kind != 'node':
                continue
            text = 'import sys\nimport sys as process\n'
            kind_body = body
            if kind == 'node':
                if not body.endswith('return {}'):
                    kind_body = body.replace('return ', '') + '\nreturn {}'
                text += 'class Task:\n    def run_pure(self, inputs, params):\n        objects = params["objects"]\n' + indent(kind_body + '\n', '        ')
            else:
                text += 'def task(objects):\n' + indent(body + '\n', '    ')
            compile(text, '/virtual/alias_escape.py', 'exec')
            entry = PythonSourceFile.parse('/virtual/alias_escape.py', 'alias_escape', text)
            descriptor = NodeDescriptor('probe.task', 'Task', 'Independent alias identity probe.', '1', 'process', contract=NodeContractDescriptor())
            nodes = (PythonSourceNode(descriptor, entry.path, 'Task'),) if kind == 'node' else ()
            sources = build_python_source_context(nodes, (entry,))
            facts = {'source_context': sources, 'node_catalog': (), 'resource_symbol': '',
                'source_owners': ({'kind': kind, 'id': 'probe.task', 'role': 'entry', 'path': entry.path, 'symbol': 'Task' if kind == 'node' else ''},),
                'base_lib_file': entry, 'resource_source_file': entry, 'source_file': entry,
                'python_source': PythonSource(entry.module, 'alias_escape.py', entry.path, text)}
            result = no_side_effects(RuleContext(subject={'kind':kind, 'id':'probe.task', 'type_key':'probe.task'}, target='python', facts=facts), {}, {'effect_scope':'global_state' if 'inputs' in label else 'none'})
            actual = any('mutate inputs' in f.message for f in result.findings) if 'inputs' in label else bool(result.findings)
            rows.append({'case':label, 'kind':kind, 'source':text, 'expected_findings':expected,
                'state':result.state, 'matched':result.state == 'completed' and actual == expected,
                'findings':[f.to_dict() for f in result.findings]})
    report = {'origin':vibeflow.__file__, 'count':len(rows), 'mismatches':sum(not r['matched'] for r in rows), 'rows':rows}
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:report[k] for k in ('origin','count','mismatches')}))


if __name__ == '__main__':
    main()
