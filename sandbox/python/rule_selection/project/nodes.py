from vibeflow.targets.python.sdk import node

@node(type_key="selection.node", flow_kind="terminal", contract={}, rulesets=[])
class Boundary:
    def run_pure(self, inputs, params):
        return {}
