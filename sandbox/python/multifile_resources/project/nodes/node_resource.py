from vibeflow.targets.python.sdk import node
from base_lib.math_resource import increment
from .node_support import multiply

@node(id="demo.model", tags=["model_block"], base_libs=["demo.math"], implementation_files=["node_support.py"], rulesets=["vibeflow.process"], contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Computed value"]}}, presentation={"fill":"#add8e6","stroke":"#1a5276","text":"#123456","shape":"rounded","icon":"M"}, node_type="vibeflow.node")
class Model:
    def run_pure(self, inputs, params):
        return {"result":multiply(increment(2), 2)}

@node(id="demo.start",flow_kind="terminal",rulesets=[],contract={}, node_type="vibeflow.node")
class Start:
    def run_pure(self, inputs, params):
        return {}
