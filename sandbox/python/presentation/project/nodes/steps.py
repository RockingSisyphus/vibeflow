from vibeflow.targets.python.sdk import node
from ..base_lib.helper import calculate
@node(node_type='vibeflow.node', id="layout.start", flow_kind="terminal", contract={}, rulesets=["vibeflow.process"])
class Start:
    def run_pure(self, inputs, params):
        return {}
@node(node_type='vibeflow.node', id="layout.end", flow_kind="terminal", contract={}, rulesets=["vibeflow.process"])
class End:
    def run_pure(self, inputs, params):
        return {}
@node(node_type='vibeflow.node', id="layout.step", rulesets=["vibeflow.process"], base_libs=["layout.helper"],
      contract={"provides":[{"key":"result", "type":"number", "display_name":"Result"}],
                "output_semantics":{"result":["The calculated fixture value."]}},
      presentation={"fill":"#d6eaff", "stroke":"#425a78", "text":"#172b45", "shape":"rounded"})
class Step:
    def run_pure(self, inputs, params):
        return {"result": calculate(1)}
@node(node_type='vibeflow.node', id="layout.step_right", rulesets=["vibeflow.process"], base_libs=["layout.helper"],
      contract={"provides":[{"key":"right_result", "type":"number", "display_name":"Right result"}],
                "output_semantics":{"right_result":["A separately named calculated fixture value."]}},
      presentation={"fill":"#d6eaff", "stroke":"#425a78", "text":"#172b45", "shape":"rounded"})
class Right:
    def run_pure(self, inputs, params):
        return {"right_result": calculate(2)}
