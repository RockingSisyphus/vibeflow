from vibeflow.targets.python.sdk import node

@node(id="selection.node", flow_kind="terminal", contract={}, rulesets=[], node_type="vibeflow.node")
class Boundary:
    def run_pure(self, inputs, params):
        return {}
