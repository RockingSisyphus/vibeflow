"""Native interface Rule observations; source is parsed, never executed."""
import argparse
import json
from pathlib import Path
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.product.resolve()))
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.rules import RuleContext
    from vibeflow.targets.python.quality.rules.node_interface import node_interface
    from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context
    contracts = (
        ('same_input_type_and_output_key','process',NodeContractDescriptor(
            requires=(DataRequirement('data.seed','exactly_one','Seed'),),
            provides=(DataProvider('data.seed','data.seed','Seed'),),
            input_semantics={'data.seed':('Seed input',)},output_semantics={'data.seed':('Seed output',)})),
        ('decision_custom_output_name','decision',NodeContractDescriptor(
            provides=(DataProvider('status.ok','bool','Status'),),output_semantics={'status.ok':('Status flag',)})),
        ('example_output_documentation','process',NodeContractDescriptor(
            examples=({'inputs':{},'params':{},'outputs':{}},))),
        ('empty_control','process',NodeContractDescriptor()),
    )
    rows=[]
    for label, kind, contract in contracts:
        returned = {provider.key: True for provider in contract.provides}
        source = PythonSourceFile.parse('/virtual/boundary_node.py','boundary_node',
            'class Task:\n    def run_pure(self, inputs, params):\n        return ' + repr(returned) + '\n')
        node=PythonSourceNode(NodeDescriptor('probe.task','Task','Boundary probe.','1',kind,contract=contract),source.path,'Task')
        sources=build_python_source_context((node,),(source,))
        context=RuleContext(subject={'kind':'node','type_key':'probe.task'},target='python',facts={'source_context':sources})
        result=node_interface(context,{}, {})
        rows.append({'case':label,'state':result.state,'findings':[item.to_dict() for item in result.findings]})
    args.report.write_text(json.dumps({'rows':rows,'scope':'Native interface Rule only; no workflow routing or business execution.'},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{'case':row['case'],'codes':[f['code'] for f in row['findings']]} for row in rows]))

if __name__=='__main__':
    main()
