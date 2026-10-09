"""Concrete import-time expression and statement syntax, with real markers."""
from pathlib import Path
import runpy

case=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))["case"]
METHOD='class DemoNode:\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'


def _bad(name,source,old="NODE.INSPECT.LOAD_ERROR",current="NODE.IMPORT.SIDE_EFFECT"):
    return case("import."+name,name,"import-syntax",source=source,code=current,expect={"metrics":{"marker":""},
        "variants":{"baseline":{"codes":[{"code":old,"severity":"error"}]}}})


def case_specs():
    cases=[
        case("import.default_literal","Literal default argument is safe","import-syntax",source='class DemoNode:\n    def _value(self,value=1):\n        return value\n    def run_pure(self,inputs,params):\n        return {"demo.out":self._value()}\n'),
        _bad("keyword_default_call",'class DemoNode:\n    def _value(self,*,value=open(__MARKER__,"w").write("keyword default")):\n        return value\n    def run_pure(self,inputs,params):\n        return {"demo.out":self._value()}\n'),
        _bad("nested_default_call",'class DemoNode:\n    def _value(self,value=(1,open(__MARKER__,"w").write("nested default"))):\n        return value\n    def run_pure(self,inputs,params):\n        return {"demo.out":self._value()}\n'),
        _bad("base_call",'def base():\n    open(__MARKER__,"w").write("base")\n    return object\nclass DemoNode(base()):\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'),
        _bad("init_subclass",'class Base:\n    def __init_subclass__(cls):\n        open(__MARKER__,"w").write("subclass")\nclass DemoNode(Base):\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'),
        _bad("metaclass",'class Meta(type):\n    def __new__(cls,name,bases,namespace):\n        open(__MARKER__,"w").write("metaclass")\n        return super().__new__(cls,name,bases,namespace)\nclass DemoNode(metaclass=Meta):\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'),
        _bad("explicit_type_metaclass",'class DemoNode(metaclass=type):\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n'),
        case("import.object_base","Builtin object base is safe","import-syntax",source=METHOD.replace('DemoNode:','DemoNode(object):')),
        case("import.local_base","Local base without declaration hook is safe","import-syntax",source='class Base:\n    pass\n'+METHOD.replace('DemoNode:','DemoNode(Base):')),
    ]
    for name,decorator in (("static","staticmethod"),("class","classmethod"),("qualified_static","builtins.staticmethod"),("property","property")):
        prefix='import builtins\n' if decorator.startswith('builtins.') else ''
        parameter='cls' if name=='class' else 'self'
        source=prefix+f'class DemoNode:\n    @{decorator}\n    def _value({parameter}):\n        return 1\n    def run_pure(self,inputs,params):\n        return {{"demo.out":1}}\n'
        cases.append(case("import.decorator_"+name,"Builtin decorator "+decorator,"import-syntax",source=source))
    for name,statement in (
        ("with",'with open(__MARKER__,"w") as stream:\n    stream.write("with")\n'),
        ("for",'for value in (1,):\n    open(__MARKER__,"w").write("for")\n'),
        ("while",'while False:\n    pass\n'),
        ("if",'if False:\n    pass\n'),
        ("try",'try:\n    pass\nexcept ValueError:\n    pass\n'),
        ("match",'match 1:\n    case 1:\n        pass\n'),
        ("raise",'raise ValueError("import")\n'),
    ):
        cases.append(_bad(name,statement+METHOD))
    cases.extend([
        case("import.type_checking","TYPE_CHECKING-only declarations are safe","import-syntax",source='from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import math\n'+METHOD),
        case("import.immutable_tuple","Immutable module tuple is safe","import-syntax",source='VALUES=(1,2)\n'+METHOD),
        _bad("annotated_mutable",'CACHE:dict={}\n'+METHOD,old="NODE.PURITY.MODULE_GLOBAL_STATE"),
        _bad("annotation_call",'class DemoNode:\n    def _value(self,value:open(__MARKER__,"w").write("annotation")):\n        return value\n    def run_pure(self,inputs,params):\n        return {"demo.out":1}\n',current="NODE.EFFECT.CALL_FORBIDDEN"),
    ])
    for name, statement in (
        ("try_marker", 'try:\n    open(__MARKER__,"w").write("try executed")\nexcept ValueError:\n    pass\n'),
        ("match_marker", 'match 1:\n    case 1:\n        open(__MARKER__,"w").write("match executed")\n'),
    ):
        cases.append(case("import."+name,"Actual import side effect inside "+name,"import-syntax",
            entrypoint="cli.run", source=statement+METHOD, rulesets=["parity.import_only"],
            code="NODE.IMPORT.SIDE_EFFECT", expect={"metrics":{"marker":""},"variants":{"baseline":{
                "codes":[{"code":"WORKSPACE.REGISTRY.IMPORT","severity":"error"}]}}},
            notes="Formal CLI run attempts real implementation assembly. Current Node selects only the import entrypoint; static/run are empty, so default static effect checking cannot mask a missing pre-bind import rejection."))
    for spec in cases:
        if spec["id"].endswith(("import.if","import.try","import.match")):
            spec["expected"]["variants"]["baseline"]["codes"]=[{"code":"NODE.PURITY.MODULE_SIDE_EFFECT","severity":"error"}]
        if spec["id"].endswith("import.type_checking"):
            spec["classification"]="baseline_limitation"
            spec["expected"]["variants"]={"baseline":{"should_accept":False,"codes":[{"code":"NODE.PURITY.MODULE_SIDE_EFFECT","severity":"error"}]}}
            spec["notes"]="Baseline preflight recognizes TYPE_CHECKING but its subsequent module visitor still rejects this non-executing static annotation convention. Current preserves the static-only exception."
    return cases
