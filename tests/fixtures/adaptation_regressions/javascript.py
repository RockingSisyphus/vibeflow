"""JavaScript adaptation regressions through fixed SDK plugins and official CLI."""
from pathlib import Path

from . import js_analysis,js_lifecycle,js_structure,js_identity,js_structure_scope


def observe(work:Path,kernel:Path,toolchain:Path|None,renderer:Path|None)->list[dict]:
    rows=[]
    for group in (js_lifecycle,js_structure,js_analysis,js_identity,js_structure_scope):
        rows.extend(group.observe(work,kernel,toolchain,renderer))
    return rows
