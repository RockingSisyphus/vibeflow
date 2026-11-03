from vibeflow.targets.python.sdk import base_lib
@base_lib(id="shared.math", rulesets=[])
def increment(value): return value + 10
