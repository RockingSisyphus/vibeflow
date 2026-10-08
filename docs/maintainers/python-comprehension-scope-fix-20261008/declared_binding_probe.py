"""Short isolated SDK -> native RulePlan input binding regression replay.

Use python -I -B. Choose --source or --kernel, or use an installed wheel's
interpreter. Inspected Node/helper source is parsed and syntax-compiled only.
"""
from __future__ import annotations
import argparse
import ast
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from textwrap import indent
import traceback
import zipfile

CASES = (
    ('nonlocal_assign', 'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs\ninner()\nsink(alias)', True),
    ('nonlocal_walrus', 'alias = {}\ndef inner():\n    nonlocal alias\n    (alias := inputs)\ninner()\nsink(alias)', True),
    ('nonlocal_get', 'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs.get("nested")\ninner()\nsink(alias)', True),
    ('nonlocal_multilevel', 'alias = {}\ndef middle():\n    def inner():\n        nonlocal alias\n        alias = inputs\n    inner()\nmiddle()\nsink(alias)', True),
    ('nonlocal_multilevel_declarations', 'alias = {}\ndef middle():\n    nonlocal alias\n    def inner():\n        nonlocal alias\n        alias = inputs\n    inner()\nmiddle()\nsink(alias)', True),
    ('nonlocal_nearest_binding_keeps_caller_local', 'alias = {}\ndef middle():\n    alias = {}\n    def inner():\n        nonlocal alias\n        alias = inputs\n    inner()\nmiddle()\nsink(alias)', False),
    ('nonlocal_keyword', 'alias = {}\ndef inner():\n    nonlocal alias\n    alias = inputs\ninner()\nsink(payload=alias)', True),
    ('nonlocal_comp_walrus', 'alias = {}\ndef inner():\n    nonlocal alias\n    list(alias := inputs for item in (0,))\ninner()\nsink(alias)', True),
    ('nonlocal_comp_local_inputs', 'alias = {}\ndef inner():\n    nonlocal alias\n    list(alias := inputs for inputs in ({},))\ninner()\nsink(alias)', False),
    ('nonlocal_lambda_default_comp', 'alias = {}\ndef inner():\n    nonlocal alias\n    values = [lambda value=(alias := inputs): value for item in (0,)]\ninner()\nsink(alias)', True),
    ('nonlocal_function_default', 'alias = {}\ndef inner():\n    nonlocal alias\n    def nested(value=(alias := inputs)):\n        return value\ninner()\nsink(alias)', True),
    ('nonlocal_lambda_body_stays_local', 'alias = {}\ndef inner():\n    nonlocal alias\n    fn = lambda: (alias := inputs)\n    fn()\ninner()\nsink(alias)', False),
    ('global_assign', 'def inner():\n    global alias\n    alias = inputs\ninner()\nsink(alias)', True),
    ('local_annotated_alias', 'alias: dict = inputs\nsink(alias)', True),
    ('annotated_child_local_stays_local', 'alias = {}\ndef inner():\n    alias: dict = inputs\ninner()\nsink(alias)', False),
    ('global_outer_decl_free_closure', 'global alias\nalias = inputs\ndef inner():\n    sink(alias)\ninner()', True),
    ('middle_global_decl_free_closure', 'alias = {}\ndef middle():\n    global alias\n    alias = inputs\n    def inner():\n        sink(alias)\n    inner()\nmiddle()', True),
    ('global_direct', 'global alias\nalias = inputs\nsink(alias)', True),
    ('global_walrus', 'def inner():\n    global alias\n    (alias := inputs)\ninner()\nsink(alias)', True),
    ('global_same_named_caller_local', 'alias = {}\ndef inner():\n    global alias\n    alias = inputs\ninner()\nsink(alias)', False),
    ('global_multilevel_with_middle_local', 'def middle():\n    alias = {}\n    def inner():\n        global alias\n        alias = inputs\n    inner()\nmiddle()\nsink(alias)', True),
    ('global_inner_same_named_local_stays_local', 'def middle():\n    alias = {}\n    def inner():\n        global alias\n        alias = inputs\n    inner()\n    sink(alias)\nmiddle()', False),
    ('global_comp_lambda_default', 'def inner():\n    global alias\n    values = [lambda value=(alias := inputs): value for item in (0,)]\ninner()\nsink(alias)', True),
    ('global_comp_lambda_default_local_control', 'alias = {}\ndef inner():\n    global alias\n    values = [lambda value=(alias := inputs): value for item in (0,)]\ninner()\nsink(alias)', False),
    ('global_lambda_body_stays_local', 'def inner():\n    global alias\n    fn = lambda: (alias := inputs)\n    fn()\ninner()\nsink(alias)', False),
    ('global_read_does_not_capture_same_named_outer_inputs', 'def inner():\n    global inputs\n    sink(inputs)\ninner()', False),
    ('ordinary_child_local_does_not_escape', 'alias = {}\ndef inner():\n    alias = inputs\ninner()\nsink(alias)', False),
    ('lambda_default_binds_parent', 'fn = lambda value=(alias := inputs): value\nsink(alias)', True),
    ('function_default_binds_parent', 'def inner(value=(alias := inputs)):\n    return value\nsink(alias)', True),
    ('lambda_parameter_shadows_inputs', '(lambda inputs: sink(inputs))({})', False),
    ('lambda_captures_inputs', '(lambda: sink(inputs))()', True),
    ('branch_possible_alias_preserved', 'if params["flag"]:\n    alias = inputs\nsink(alias)', True),
    ('loop_possible_alias_preserved', 'for item in ():\n    alias = inputs\nsink(alias)', True),
    ('late_closure_preserved', 'def inner():\n    return sink(alias)\nalias = inputs\ninner()', True),
)


def replay():
    parser=argparse.ArgumentParser(description=__doc__)
    selection=parser.add_mutually_exclusive_group()
    selection.add_argument('--source',type=Path)
    selection.add_argument('--kernel',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--expect',choices=('before','fixed'),default='fixed')
    args=parser.parse_args()
    report={'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'observations':[], 'probe_error':None}
    try:
        if args.source:
            product=args.source.resolve(strict=True);kind='source_snapshot'
            sys.path.insert(0,str(product))
        elif args.kernel:
            product=args.kernel.resolve(strict=True);kind='kernel_zip'
            sys.path.insert(0,str(product))
        else:
            distribution=importlib.metadata.distribution('vibeflow')
            assert distribution.read_text('WHEEL')
            assert not json.loads(distribution.read_text('direct_url.json') or '{}').get('dir_info',{}).get('editable')
            product=Path(distribution.locate_file('')).resolve(strict=True);kind='installed_wheel'
        report['product']={'kind':kind,'path':str(product)}
        import vibeflow
        from vibeflow.core.descriptors import NodeContractDescriptor,NodeDescriptor
        from vibeflow.core.rules import RuleContext,compile_ruleset,execute_rule_plan
        from vibeflow.targets.python.sdk import RuleCall,ruleset
        from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan
        from vibeflow.targets.python.quality.source_analysis.input_tracking import _input_call_facts,_trace_helper_input_parameters,source_input_parameters
        from vibeflow.targets.python.quality.source_context import PythonSourceFile,PythonSourceNode,build_python_source_context
        from vibeflow.targets.shared.bindings import native_binding
        from vibeflow.tooling.project.descriptor_loader import load_builtin_plugins
        catalog=load_builtin_plugins('python').catalogs
        rules={item.id:item for item in catalog.rules}
        handlers={item.id:native_binding(catalog,'rule',item.id) for item in catalog.rules}
        selected=ruleset(id='probe.declared_binding',calls=[RuleCall(id='effects',rule_id='vibeflow.no_side_effects',params={'effect_scope':'global_state'})]).descriptor
        plan=complete_source_policy_plan(compile_ruleset(selected,rules=rules,rulesets={selected.id:selected}),handlers=handlers)
        for label,body,expected in CASES:
            text="alias = None\ninputs = {}\ndef sink(payload):\n    return payload.pop('seed', None)\nclass Task:\n    def run_pure(self, inputs, params):\n"+indent(body+'\nreturn {}\n','        ')
            compile(text,'/virtual/input_binding.py','exec')
            source=PythonSourceFile.parse('/virtual/input_binding.py','input_binding',text)
            descriptor=NodeDescriptor(type_key='example.task',display_name='Task',description='Declared binding ownership.',version='1',flow_kind='process',contract=NodeContractDescriptor())
            node=PythonSourceNode(descriptor,source.path,'Task')
            context=build_python_source_context((node,),(source,))
            formal=source_input_parameters(context,node)
            fallback=_trace_helper_input_parameters(source._tree,'Task')
            execution=execute_rule_plan(plan,RuleContext(subject={'kind':'node','type_key':'example.task'},facts={'source_context':context,'node_catalog':(),'source_owners':()},target='python'),handlers=handlers)
            result=execution.results['effects']
            findings=tuple(item.to_dict() for item in result.findings)
            mutations=tuple(item for item in findings if 'mutate inputs' in item['message'])
            formal_owned='payload' in formal.get(source.path+':sink',set())
            fallback_owned='payload' in fallback.get('sink',set())
            global_names={item.name for item in context.symbols if item.kind=='global'}
            assert {'alias','inputs'} <= global_names
            matched=bool(mutations)==expected and formal_owned==expected and fallback_owned==expected and result.state=='completed'
            report['observations'].append({'case':label,'source':text,'expected_owned':expected,'formal_owned':formal_owned,'fallback_owned':fallback_owned,'actual_mutation':bool(mutations),'matched':matched,'result_state':result.state,'effect_policy':result.to_dict()['records']['effect_policy']['value'],'findings':findings,'source_references':[asdict(item) for item in context.references],'global_names':sorted(global_names)})
        # This selected root has an external nonlocal cell. Its owned writes
        # stay visible to its own calls but cannot become module global facts.
        external_text="alias = None\ndef sink(payload):\n    return payload.pop('seed', None)\nclass Task:\n    def run_pure(self, inputs, params):\n        alias = {}\n        def inner(owned):\n            nonlocal alias\n            alias = owned\n            sink(alias)\n            def global_reader():\n                global alias\n                sink(alias)\n            global_reader()\n        inner(inputs)\n        return {}\n"
        external=PythonSourceFile.parse('/virtual/external_cell.py','external_cell',external_text)
        inner=next(statement for statement in ast.walk(external._tree)
                   if isinstance(statement,ast.FunctionDef) and statement.name=='inner')
        external_calls=_input_call_facts(inner,{'owned'})
        external_sites=[{'line':call.lineno,'owned':flags[0][0]} for call,flags in external_calls.items()
                        if getattr(call.func,'id',None)=='sink']
        assert external_sites==[{'line':10,'owned':True},{'line':13,'owned':False}],external_sites
        report['external_function_root_controls']=external_sites
        # An intervening global declaration cannot be jumped by nonlocal. A
        # target used only by a comprehension also cannot bind an outer cell.
        invalid=[
            'def outer():\n    alias = None\n    def middle():\n        global alias\n        def inner():\n            nonlocal alias\n',
            'def outer():\n    values = [alias for alias in ()]\n    def inner():\n        nonlocal alias\n',
        ]
        syntax=[]
        for text in invalid:
            try:
                compile(text,'/virtual/invalid_nonlocal.py','exec')
            except SyntaxError as error:
                syntax.append({'source':text,'rejected':True,'message':str(error)})
            else:
                syntax.append({'source':text,'rejected':False})
        assert all(item['rejected'] for item in syntax)
        report['syntax_controls']=syntax
        loaded={name:str(getattr(module,'__file__','')) for name,module in sys.modules.items() if name=='vibeflow' or name.startswith('vibeflow.')}
        prefix=str(product/'vibeflow')+'/'
        foreign={name:path for name,path in loaded.items() if not path or not path.startswith(prefix)}
        report['loaded_product_modules']=loaded
        report['loaded_module_count']=len(loaded)
        report['foreign_product_modules']=foreign
        assert not foreign,foreign
        rel='vibeflow/targets/python/quality/source_analysis/input_tracking.py'
        if args.kernel:
            with zipfile.ZipFile(product) as archive: payload=archive.read(rel)
        else: payload=(product/rel).read_bytes()
        report['input_tracking_sha256']=hashlib.sha256(payload).hexdigest()
        report['summary']={'cases':len(CASES),'matched':sum(item['matched'] for item in report['observations']),'mismatches':sum(not item['matched'] for item in report['observations'])}
        report['expected_state_observed']=report['summary']['mismatches']==0 if args.expect=='fixed' else report['summary']['mismatches']>0
    except Exception:
        report['probe_error']=traceback.format_exc();report['expected_state_observed']=False
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ('summary','probe_error','expected_state_observed','input_tracking_sha256','foreign_product_modules')}))
    return 0 if report['expected_state_observed'] else 1


if __name__=='__main__':
    raise SystemExit(replay())
