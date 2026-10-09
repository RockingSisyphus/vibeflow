from vibeflow.targets.python.sdk import node
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def run_pure(self, inputs, params):
        value=1
        def helper():
            nonlocal value
            return value
        answer=helper()
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
