from vibeflow.targets.python.sdk import node
@node(type_key="probe.task", rulesets=["probe.selected"], contract={})
class Task:
    def _factorial(self, n):
        return 1 if n <= 1 else n * self._factorial(n - 1)
    def run_pure(self, inputs, params):
        value = self._factorial(3)
        return {}
@node(type_key="probe.start", flow_kind="terminal", rulesets=[], contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
