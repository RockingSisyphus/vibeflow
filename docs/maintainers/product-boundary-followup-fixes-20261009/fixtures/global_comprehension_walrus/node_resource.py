from vibeflow.targets.python.sdk import node
from contextlib import nullcontext
VERSION = 1
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def run_pure(self, inputs, params):
        global VERSION
        [(VERSION := item) for item in [2]]
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
