from vibeflow.targets.python.sdk import node
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def run_pure(self, inputs, params):
        i = 0
        for value in (0, 1, 2):
            i += value
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
