"""Node library policy and standalone AST scanner concrete branches."""
from pathlib import Path
import runpy

case=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))["case"]


def _scan(name,text,code=None,**options):
    return case("library."+name,name,"base-lib",entrypoint="target.scan_base_lib",files={"base_lib/example.py":text},code=code,**options)


def case_specs():
    cases=[]
    files={"base_lib/__init__.py":"", "base_lib/helper.py":"def step(value):\n    return value+1\n"}
    for location in ("module","method"):
        source='from base_lib.helper import step\nclass DemoNode:\n    def run_pure(self,inputs,params):\n        return {"demo.out":step(1)}\n' if location=="module" else 'class DemoNode:\n    def run_pure(self,inputs,params):\n        from base_lib.helper import step\n        return {"demo.out":step(1)}\n'
        for permission in ("undeclared","banned","allowed"):
            policy={"base_lib":{"allowed_paths":["base_lib"],"allowed_modules":[] if permission=="undeclared" else ["base_lib"],"banned_modules":["base_lib.helper"] if permission=="banned" else []}}
            code={"undeclared":"NODE.BASE_LIB.BASE_LIB_UNDECLARED","banned":"NODE.BASE_LIB.BASE_LIB_BANNED","allowed":None}[permission]
            cases.append(case("library.node_"+location+"_"+permission,location+" library permission "+permission,"base-lib",source=source,files=files,policy=policy,code=code))
    for name,text,code in (
        ("top_with",'with open("ignored","w"):\n    pass\n',"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        ("top_for",'for item in ():\n    pass\n',"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        ("top_while",'while False:\n    pass\n',"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        ("top_try",'try:\n    pass\nexcept ValueError:\n    pass\n',"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        ("top_expression",'print("not executed")\n',"BASE_LIB.TOP_LEVEL_SIDE_EFFECT"),
        ("immutable_tuple",'VALUE=(1,2)\n',None),
        ("namespace_locals",'def value():\n    return locals()["unknown"]\n',"BASE_LIB.SIDE_EFFECT_CALL"),
        ("namespace_module",'import math\ndef value():\n    return math.__dict__["sqrt"]\n',None),
        ("namespace_sensitive",'import builtins\ndef value(key):\n    return builtins.__dict__[key]\n',"BASE_LIB.SIDE_EFFECT_CALL"),
        ("ordinary_lookup",'def value():\n    return {"known":1}["known"]\n',None),
        ("exit_raise",'def value():\n    raise SystemExit\n',"BASE_LIB.SIDE_EFFECT_CALL"),
        ("exit_sys_alias",'import sys as s\ndef value():\n    s.exit(1)\n',"BASE_LIB.SIDE_EFFECT_CALL"),
        ("argv_alias",'from sys import argv as arguments\n',"BASE_LIB.BANNED_IMPORT"),
        ("ordinary_raise",'def value():\n    raise ValueError("ordinary")\n',None),
    ):
        cases.append(_scan(name,text,code))
    for count,limit in ((100,100),(10,1000)):
        cases.append(_scan("bytes_"+str(count),'VALUE="'+'界'*count+'"\n',"BASE_LIB.SOURCE.MAX_BYTES" if count==100 else None,purity_kwargs={"max_source_bytes":limit}))
    nested='def value(x):\n    if x:\n        if x>1:\n            return 1\n    return 0\n'
    for limit in (1,2):
        cases.append(_scan("branches_"+str(limit),nested,"BASE_LIB.COMPLEXITY.MAX_BRANCHES" if limit==1 else None,purity_kwargs={"max_branches":limit}))
        cases.append(_scan("nesting_"+str(limit),nested,"BASE_LIB.COMPLEXITY.MAX_NESTING_DEPTH" if limit==1 else None,purity_kwargs={"max_nesting_depth":limit}))
    cases.append(_scan("explicit_banned_module","import math\n", "BASE_LIB.BANNED_MODULE",purity_kwargs={"banned_base_lib_modules":["math"]}))
    cases.append(_scan("math_allowed","import math\n",None))
    closure={"base_lib/a.py":"from .b import value\ndef entry():\n    return value()\n","base_lib/b.py":"def value():\n    print('bad')\n    return 1\n"}
    cases.append(case("library.dependency_closure","Library dependency closure retains indirect violation","base-lib",entrypoint="target.scan_base_lib",files=closure,code="BASE_LIB.DEPENDENCY_CLOSURE_VIOLATION"))
    cases.append(case("library.dependency_closure_valid","Pure dependency closure neighbour","base-lib",entrypoint="target.scan_base_lib",files={**closure,"base_lib/b.py":"def value():\n    return 1\n"}))
    for spec in cases:
        if spec["id"].endswith(("node_module_undeclared","node_module_banned")):
            spec["expected"]={"should_accept":True,"codes":[],"forbidden_codes":["NODE.BASE_LIB.BASE_LIB_UNDECLARED","NODE.BASE_LIB.BASE_LIB_BANNED"]}
            spec["classification"]="baseline_limitation"
            spec["notes"]="Baseline and current both skip the Node allow/banned library declaration judgment on a module-level import; the same import inside run_pure has separate refusing neighbours."
    return cases
