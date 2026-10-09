from vibeflow.targets.python.sdk import base_lib
from math_support import add

@base_lib(id="demo.math", implementation_files=["math_support.py"], rulesets=["vibeflow.base_lib"], presentation={"fill":"#c8e4ff", "shape":"cyl", "icon":"Σ"})
def increment(value):
    return add(value, 1)
