from vibeflow.targets.python.sdk import node
class Box:
    pass
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def run_pure(self, inputs, params):
        box = Box()
        setattr(box, 'count', 1)
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
