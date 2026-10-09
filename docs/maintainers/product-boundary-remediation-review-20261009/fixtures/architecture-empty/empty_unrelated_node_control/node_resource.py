from vibeflow.targets.python.sdk import node
@node(type_key="probe.foreign", rulesets=[], contract={})
class Foreign:
    _value = 1
    def run_pure(self, inputs, params):
        return {}
@node(type_key="probe.task", rulesets=[], contract={})
class Task:
    def run_pure(self, inputs, params):
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
