"""Public-rule probes for evaluated ownership identity; inspected snippets never execute."""
import argparse, hashlib, json, sys
from pathlib import Path
from textwrap import indent
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'src'))
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.quality.rules.effects import no_side_effects
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
from vibeflow.targets.python.quality.source_analysis.input_tracking import source_input_parameters

CASES=(
 ('get_receiver_owned_to_local', "alias=inputs\nborrowed=alias.get((alias := 'seed'), {})\nborrowed.pop('seed',None)", True),
 ('get_receiver_local_to_owned', "alias={'seed':{}}\nborrowed=alias.get((alias := inputs) and 'seed', {})\nborrowed.pop('seed',None)", False),
 ('subscript_receiver_owned_to_local', "alias=inputs\nborrowed=alias[(alias := 'seed')]\nborrowed.pop('seed',None)", True),
 ('subscript_receiver_local_to_owned', "alias={'seed':{}}\nborrowed=alias[(alias := inputs) and 'seed']\nborrowed.pop('seed',None)", False),
 ('direct_pop_receiver_owned_to_local', "alias=inputs\nalias.pop((alias := 'seed'),None)", True),
 ('direct_pop_receiver_local_to_owned', "alias={}\nalias.pop((alias := inputs) and 'seed',None)", False),
 ('helper_get_receiver_owned_to_local', "alias=inputs\nsink(alias.get((alias := 'seed'), {}))", True),
 ('helper_get_receiver_local_to_owned', "alias={'seed':{}}\nsink(alias.get((alias := inputs) and 'seed', {}))", False),
 ('helper_first_arg_keeps_earlier_owned_value', "alias=inputs\nsink(alias,(alias := {}))", True),
 ('helper_first_arg_keeps_earlier_local_value', "alias={}\nsink(alias,(alias := inputs))", False),
 ('keyword_first_arg_keeps_earlier_owned_value', "alias=inputs\nsink(payload=alias,other=(alias := {}))", True),
 ('keyword_first_arg_keeps_earlier_local_value', "alias={}\nsink(payload=alias,other=(alias := inputs))", False),
)

def hashes():
 return {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in (
  'src/vibeflow/targets/python/quality/source_analysis/input_tracking.py',
  'src/vibeflow/targets/python/quality/source_analysis/visitors.py',
  'src/vibeflow/targets/python/quality/rules/effects.py')}

def main():
 parser=argparse.ArgumentParser(); parser.add_argument('--report',type=Path,required=True); args=parser.parse_args()
 before=hashes(); rows=[]
 for label,body,expected in CASES:
  text="def sink(payload,other=None):\n    payload.pop('seed',None)\nclass Task:\n    def run_pure(self,inputs,params):\n"+indent(body+"\nreturn {}\n",'        ')
  compile(text,'/virtual/evaluation_order.py','exec')
  parsed=PythonSourceFile.parse('/virtual/evaluation_order.py','evaluation_order',text)
  desc=NodeDescriptor(type_key='example.task',display_name='Task',description='Evaluated input identity.',version='1',flow_kind='process',contract=NodeContractDescriptor())
  node=PythonSourceNode(desc,parsed.path,'Task'); sources=build_python_source_context((node,),(parsed,))
  result=no_side_effects(RuleContext(subject={'kind':'node','type_key':'example.task'},target='python',facts={'source_context':sources,'node_catalog':(),'source_owners':()}),{},{'effect_scope':'global_state'})
  actual=any('mutate inputs' in f.message for f in result.findings)
  rows.append({'case':label,'expected':expected,'actual':actual,'matched':result.state=='completed' and actual==expected,'source':text,'parameter_seeds':{k:sorted(v) for k,v in source_input_parameters(sources,node).items()},'findings':[f.to_dict() for f in result.findings]})
 after=hashes(); report={'count':len(rows),'mismatches':sum(not r['matched'] for r in rows),'hashes':before,'changed_during_probe':[k for k in before if before[k]!=after[k]],'rows':rows}
 args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:report[k] for k in ('count','mismatches','changed_during_probe')}))
 for row in rows:
  if not row['matched']:print(row['case'],row['expected'],row['actual'])
if __name__=='__main__':main()
