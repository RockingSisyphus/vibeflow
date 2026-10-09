"""Concrete alias, argv, stream, exit and reflection effect branches."""
from pathlib import Path
import runpy

case=runpy.run_path(str(Path(__file__).with_name("variant_helpers.py")))["case"]


def case_specs():
    variants=[
        ("argv_module_alias",'import sys as system\nvalue=system.argv',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("argv_from_alias",'from sys import argv as arguments\nvalue=arguments',"NODE.EFFECT.IMPORT_FORBIDDEN"),
        ("stdout_alias",'from sys import stdout as output\noutput.write("bad")',"NODE.EFFECT.IMPORT_FORBIDDEN"),
        ("stderr_module_alias",'import sys as system\nsystem.stderr.write("bad")',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("stdin_read",'import sys\nsys.stdin.read()',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("exit_alias",'from sys import exit as leave\nleave(1)',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("exit_builtin",'raise SystemExit',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("exit_quit",'quit()',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("eval_builtin_alias",'import builtins as b\nb.eval("1")',"NODE.PURITY.BANNED_CALL"),
        ("eval_assignment_alias",'execute=eval\nexecute("1")',"NODE.PURITY.BANNED_CALL"),
        ("dynamic_import_alias",'from importlib import import_module as load\nload("math")',"NODE.PURITY.BANNED_CALL"),
        ("globals_lookup",'value=globals()["anything"]',"NODE.PURITY.BANNED_CALL"),
        ("locals_lookup",'value=locals()["anything"]',"NODE.PURITY.BANNED_CALL"),
        ("vars_module",'import math\nvalue=vars(math)["sqrt"]',None),
        ("dunder_dict",'import math\nvalue=math.__dict__["sqrt"]',None),
        ("vars_sensitive",'import builtins\nkey=params.get("method","eval")\nvalue=vars(builtins)[key]',"NODE.PURITY.BANNED_CALL"),
        ("dunder_sensitive",'import builtins\nkey=params.get("method","eval")\nvalue=builtins.__dict__[key]',"NODE.PURITY.BANNED_CALL"),
        ("ffi_root_alias",'import ctypes as native\nnative.CDLL("bad")',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("callback_hook",'import sys\nsys.settrace(lambda *args:None)',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("path_alias",'from pathlib import Path as FilePath\nFilePath("bad").write_text("bad")',"NODE.EFFECT.CALL_FORBIDDEN"),
        ("boundary_import",'import boundary\nvalue=1',"NODE.PURITY.BOUNDARY_IMPORT"),
    ]
    cases=[case("effect."+name,name,"effect-branches",body=body+'\nreturn {"demo.out":1}',code=code) for name,body,code in variants]
    for name,body,kind,selection in (
        ("argv_declared_input",'value=inputs.get("cli.argv",{})',"process","vibeflow.process"),
        ("stdout_terminal",'import sys\nsys.stdout.write("allowed")',"io","vibeflow.io"),
        ("exit_terminal",'import sys\nsys.exit(1)',"io","vibeflow.io"),
        ("ordinary_exception",'raise ValueError("ordinary")',"process","vibeflow.process"),
        ("ordinary_dict_lookup",'value={"safe":1}["safe"]',"process","vibeflow.process"),
        ("math_alias",'import math as m\nvalue=m.sqrt(4)',"process","vibeflow.process"),
    ):
        cases.append(case("effect."+name,name,"effect-branches",body=body+'\nreturn {"demo.out":1}',flow_kind=kind,rulesets=[selection]))
    for explicit in (False,True):
        body='import argparse\nparser=argparse.ArgumentParser()\nparser.parse_args('+('["--help"]' if explicit else '')+')\nreturn {"demo.out":1}'
        cases.append(case("effect.argparse_"+str(explicit),"argparse explicit argv neighbour "+str(explicit),"effect-branches",body=body,
            flow_kind="document",rulesets=["vibeflow.python_io"],code=None if explicit else "NODE.EFFECT.CALL_FORBIDDEN"))
    for spec in cases:
        if spec["id"].endswith("boundary_import"):
            spec["expected"]["variants"] = {"current":{"should_accept":True,"codes":[]}}
            spec["classification"] = "approved_change"
            spec["notes"] = "A directory/module spelling does not declare a boundary; current role checks use actual canonical owners."
    return cases
