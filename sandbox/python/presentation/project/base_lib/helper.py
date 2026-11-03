from vibeflow.targets.python.sdk import base_lib
@base_lib(id="layout.helper", rulesets=["vibeflow.base_lib"],
          presentation={"fill":"#ffe6b3", "shape":"hex"})
def calculate(value):
    return value + 1
