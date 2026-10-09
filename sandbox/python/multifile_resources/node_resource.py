from vibeflow.targets.python.sdk import node
from math_resource import increment
from node_support import multiply

@node(type_key="demo.model", tags=["model_block"], base_libs=["demo.math"], implementation_files=["node_support.py"], rulesets=["vibeflow.process"], contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["Computed value"]}}, presentation={"fill":"#add8e6","stroke":"#1a5276","text":"#123456","shape":"rounded","icon":"M"})
class Model:
    def run_pure(self, inputs, params):
        return {"result":multiply(increment(2), 2)}

@node(type_key="demo.start",flow_kind="terminal",rulesets=[],contract={})
class Start:
    def run_pure(self, inputs, params):
        return {}
