"""Isolated public Rule comparison for nested writeback clear; snippets never execute."""
import argparse, hashlib, json, sys
from pathlib import Path
from textwrap import indent
parser=argparse.ArgumentParser();parser.add_argument('--package-root',type=Path,required=True);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
package=args.package_root.resolve();sys.path.insert(0,str(package))
import vibeflow
from vibeflow.core.descriptors import NodeContractDescriptor,NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile,PythonSourceNode,build_python_source_context
cases=(
 ('nested_return_before_clear',"alias={}\ndef bind():\n    nonlocal alias\n    alias=inputs\n    return\n    alias={}\nbind()\nalias.pop('seed',None)",True),
 ('nested_raise_before_clear',"alias={}\ndef bind():\n    nonlocal alias\n    alias=inputs\n    raise KeyError('seed')\n    alias={}\ntry:\n    bind()\nexcept KeyError:\n    alias.pop('seed',None)",True),
 ('nested_call_before_clear',"alias={}\ndef fallible():\n    return params['flag']\ndef bind():\n    nonlocal alias\n    alias=inputs\n    fallible()\n    alias={}\ntry:\n    bind()\nexcept KeyError:\n    alias.pop('seed',None)",True),
 ('nested_subscript_before_clear',"alias={}\ndef bind():\n    nonlocal alias\n    alias=inputs\n    params['flag']\n    alias={}\ntry:\n    bind()\nexcept KeyError:\n    alias.pop('seed',None)",True),
 ('nested_attribute_before_clear',"alias={}\ndef bind():\n    nonlocal alias\n    alias=inputs\n    params.missing\n    alias={}\ntry:\n    bind()\nexcept AttributeError:\n    alias.pop('seed',None)",True),
)
source_path=package/'vibeflow/targets/python/quality/source_analysis/input_tracking.py';before=hashlib.sha256(source_path.read_bytes()).hexdigest();rows=[]
for label,body,expected in cases:
 text='class Task:\n    def run_pure(self,inputs,params):\n'+indent(body+'\nreturn {}\n','        ')
 compile(text,'/virtual/writeback_summary.py','exec')
 parsed=PythonSourceFile.parse('/virtual/writeback_summary.py','writeback_summary',text)
 desc=NodeDescriptor(type_key='example.task',display_name='Task',description='Read-only input summary probe.',version='1',flow_kind='process',contract=NodeContractDescriptor());node=PythonSourceNode(desc,parsed.path,'Task');sources=build_python_source_context((node,),(parsed,))
 result=no_side_effects(RuleContext(subject={'kind':'node','type_key':'example.task'},target='python',facts={'source_context':sources,'node_catalog':(),'source_owners':()}),{},{'effect_scope':'global_state'})
 actual=any('mutate inputs' in f.message for f in result.findings)
 rows.append({'case':label,'source':text,'expected':expected,'actual':actual,'matched':actual==expected,'findings':[f.to_dict() for f in result.findings],'calls':[{'source':r.source,'target':r.target,'line':r.line,'column':r.column} for r in sources.references if r.kind=='call']})
foreign={name:str(Path(module.__file__).resolve()) for name,module in sys.modules.items() if (name=='vibeflow' or name.startswith('vibeflow.')) and getattr(module,'__file__',None) and not Path(module.__file__).resolve().is_relative_to(package)}
report={'origin':vibeflow.__file__,'package_root':str(package),'foreign_modules':foreign,'count':len(rows),'mismatches':sum(not r['matched'] for r in rows),'input_tracking_sha256':before,'changed_during_probe':before!=hashlib.sha256(source_path.read_bytes()).hexdigest(),'rows':rows}
args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
for row in rows:print(row['case'],row['expected'],row['actual'])
