"""Read-only public rule and in-memory language proof for the parity fixture."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--package-root', type=Path, required=True)
parser.add_argument('--source-file', type=Path, required=True)
parser.add_argument('--report', type=Path, required=True)
options = parser.parse_args()
package = options.package_root.resolve(strict=True)
source_path = options.source_file.resolve(strict=True)
sys.path.insert(0, str(package))

import vibeflow
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
from vibeflow.targets.python.quality.source_analysis import input_tracking

code = source_path.read_text()
code_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
source = PythonSourceFile.parse(str(source_path), 'conditional_alias', code)
before = ast.dump(source._tree)
descriptor = NodeDescriptor(type_key='parity.node', display_name='Parity', description='Conditional ownership.',
    version='1', flow_kind='process', contract=NodeContractDescriptor())
node = PythonSourceNode(descriptor, source.path, 'DemoNode')
sources = build_python_source_context((node,), (source,))
result = no_side_effects(RuleContext(subject={'kind':'node', 'type_key':'parity.node'}, target='python',
    facts={'source_context':sources, 'node_catalog':(), 'source_owners':()}), {}, {'effect_scope':'none'})

# The inspected eight-line fixture has no imports or I/O. Execute only that
# exact source to demonstrate Python's list identity and the actual mutation.
assert code == ('class DemoNode:\n    def run_pure(self, inputs, params):\n'
    '        if params.get("choose"):\n            value=inputs["demo.in"]\n'
    '        else:\n            value=[]\n        value.append(1)\n'
    '        return {"demo.out":1}\n')
namespace = {}
exec(compile(code, str(source_path), 'exec'), namespace)
runtime = []
for choose in (False, True):
    borrowed = [0]
    inputs = {'demo.in':borrowed}
    previous = list(borrowed)
    output = namespace['DemoNode']().run_pure(inputs, {'choose':choose})
    runtime.append({'choose':choose, 'before':previous, 'after':list(borrowed),
        'same_input_object':inputs['demo.in'] is borrowed, 'mutates_input':borrowed != previous, 'output':output})
assert [row['mutates_input'] for row in runtime] == [False, True]
loaded = {name:str(getattr(module,'__file__','')) for name,module in sys.modules.items()
    if name == 'vibeflow' or name.startswith('vibeflow.')}
foreign = {name:path for name,path in loaded.items() if not path or not Path(path).resolve().is_relative_to(package)}
assert not foreign, foreign
report = {'package_root':str(package), 'product_origin':vibeflow.__file__,
    'input_tracking_sha256':hashlib.sha256(Path(input_tracking.__file__).read_bytes()).hexdigest(),
    'source_file':str(source_path), 'source_sha256':code_hash,
    'source_unchanged':hashlib.sha256(source_path.read_bytes()).hexdigest() == code_hash,
    'ast_unchanged':ast.dump(source._tree) == before, 'rule_state':result.state,
    'actual_input_mutation_diagnostic':any(item.code == 'NODE.PURITY.INPUT_MUTATION' for item in result.findings),
    'findings':[item.to_dict() for item in result.findings], 'runtime_proof':runtime,
    'loaded_product_modules':loaded, 'foreign_product_modules':foreign}
options.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({key:report[key] for key in ('product_origin','rule_state','actual_input_mutation_diagnostic',
    'source_unchanged','ast_unchanged','foreign_product_modules','runtime_proof')}, ensure_ascii=False))
