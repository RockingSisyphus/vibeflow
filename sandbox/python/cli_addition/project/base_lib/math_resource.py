from vibeflow.targets.python.sdk import base_lib
from .math_support import add

@base_lib(id="addition.math", implementation_files=["math_support.py"], rulesets=["vibeflow.base_lib"])
def total(a, b, c):
    return add(a, b, c)
