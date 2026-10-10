from vibeflow.targets.python.sdk import base_lib

@base_lib(id="workflow.add", rulesets=["vibeflow.base_lib"])
def add(a, b):
    return a + b
