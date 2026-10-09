"""Mutator spellings and helper parameter ownership use real source bodies."""
from pathlib import Path
import runpy

case=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))["case"]


def case_specs():
    methods={"append":"1","clear":"","extend":"[1]","insert":"0,1","pop":"","popitem":"","remove":"1","setdefault":"'key',1","sort":"","update":"{'key':1}"}
    cases=[]
    for method,args in methods.items():
        allocation="{}" if method in {"popitem","setdefault","update"} else "[1]"
        for owned in (False,True):
            seed=allocation if owned else 'inputs["demo.in"]'
            body=f'value={seed}\nvalue.{method}({args})\nreturn {{"demo.out":1}}'
            cases.append(case("ownership."+method+("_local" if owned else "_input"),method+" local/input neighbour","input-ownership",body=body,code=None if owned else "NODE.PURITY.INPUT_MUTATION"))
    variants=[
        ("nested_set",'inputs["demo.in"]["value"][0]=1'),
        ("nested_delete",'del inputs["demo.in"]["value"][0]'),
        ("nested_attribute",'value=inputs["demo.in"]["value"]\nvalue.field=1'),
        ("annotated_alias",'value:list=inputs["demo.in"]\nvalue.append(1)'),
        ("augmented_alias",'value=inputs["demo.in"]\nvalue+=[1]'),
        ("get_alias",'value=inputs.get("demo.in",{})\nvalue.update({"x":1})'),
        ("alias_chain",'value=inputs\nsecond=value\nsecond["x"]=1'),
        ("conditional_alias",'if params.get("choose"):\n    value=inputs["demo.in"]\nelse:\n    value=[]\nvalue.append(1)'),
    ]
    for name,body in variants:
        cases.append(case("ownership."+name,name,"input-ownership",body=body+'\nreturn {"demo.out":1}',code="NODE.PURITY.INPUT_MUTATION"))
    for name,body in (
        ("rebound_local",'value=inputs["demo.in"]\nvalue=[]\nvalue.append(1)'),
        ("copy_list",'value=list(inputs["demo.in"])\nvalue.append(1)'),
        ("copy_dict",'value=dict(inputs)\nvalue["local"]=1'),
        ("ordinary_read",'value=inputs.get("demo.in",{})'),
    ):
        cases.append(case("ownership."+name,name,"input-ownership",body=body+'\nreturn {"demo.out":1}'))
    for name,invocation,helper in (
        ("helper_position","change(inputs)",'def change(value):\n    value["x"]=1\n    return 1\n'),
        ("helper_keyword","change(value=inputs)",'def change(*,value):\n    value["x"]=1\n    return 1\n'),
        ("helper_chain","outer(inputs)",'def inner(value):\n    value["x"]=1\n    return 1\ndef outer(data):\n    return inner(data)\n'),
        ("helper_local","change({})",'def change(value):\n    value["x"]=1\n    return 1\n'),
    ):
        source=helper+'class DemoNode:\n    def run_pure(self,inputs,params):\n        return {"demo.out":'+invocation+'}\n'
        cases.append(case("ownership."+name,name,"input-ownership",source=source,code=None if name=="helper_local" else "NODE.PURITY.INPUT_MUTATION"))
    for name,invocation in (("class_helper_position","self._change(inputs)"),("class_helper_keyword","self._change(value=inputs)")):
        source='class DemoNode:\n    def _change(self,value):\n        value["x"]=1\n        return 1\n    def run_pure(self,inputs,params):\n        return {"demo.out":'+invocation+'}\n'
        cases.append(case("ownership."+name,name,"input-ownership",source=source,code="NODE.PURITY.INPUT_MUTATION"))
    cases.extend([
        case("syntax.yield_from","yield from is a generator execution method","pure-syntax",body='yield from ({"demo.out":1},)\nreturn {"demo.out":1}',code="NODE.PURITY.GENERATOR_RUN_PURE"),
        case("syntax.for_allowed","Ordinary bounded for remains legal","pure-syntax",body='total=0\nfor value in (1,2):\n    total+=value\nreturn {"demo.out":total}'),
        case("syntax.comprehension_allowed","Owned comprehension remains legal","pure-syntax",body='value=[number+1 for number in (1,2)]\nreturn {"demo.out":value}'),
    ])
    for spec in cases:
        name=spec["id"].removeprefix("python.variant.ownership.")
        if name == "augmented_alias":
            spec["expected"]={"should_accept":True,"codes":[],"forbidden_codes":["NODE.PURITY.INPUT_MUTATION"]}
            spec["classification"]="baseline_limitation"
            spec["notes"]="Both kernels actually miss this concrete input ownership path; it is an original limit, not a loss inferred from the word mutation."
        if name == "conditional_alias":
            spec["expected"]["variants"]={"baseline":{"should_accept":True,"codes":[],"forbidden_codes":["NODE.PURITY.INPUT_MUTATION"]}}
            spec["classification"]="new_feature"
            spec["notes"]="Frozen kernels missed the borrowed value on the true branch. The current branch join retains possible input ownership and rejects append."
        if name in {"class_helper_position","class_helper_keyword"}:
            spec["expected"]["variants"]={"baseline":{"should_accept":True,"codes":[],"forbidden_codes":["NODE.PURITY.INPUT_MUTATION"]}}
            spec["classification"]="new_feature"
            spec["notes"]="Baseline only propagated taint into module helper parameters, not this private class method parameter. The current SourceContext propagates actual input ownership to it."
    return cases
