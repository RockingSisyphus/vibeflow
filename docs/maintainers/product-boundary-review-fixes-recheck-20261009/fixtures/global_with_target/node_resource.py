from vibeflow.targets.python.sdk import node
VERSION=1
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def run_pure(self, inputs, params):
        global VERSION
        from contextlib import nullcontext
        with nullcontext(2) as VERSION:
            pass
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
