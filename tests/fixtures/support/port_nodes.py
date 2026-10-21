"""Ordinary SDK port nodes used by native runtime behavior tests."""
from vibeflow.targets.python.sdk import node


@node(id="fixture.port.receive", flow_kind="io", rulesets=["vibeflow.io"],
      capabilities=[{"id": "vibeflow.port", "operations": ["receive"]}],
      contract={"provides": [{"key": "number", "type": "number", "display_name": "Number"}],
                "output_semantics": {"number": ["Host-provided number"]},
                "params_schema": {"port": {"type": "string"}}, "params_defaults": {"port": "math.in"}}, node_type="vibeflow.node")
class Receive:
    def run_pure(self, inputs, params, context):
        value = context.capabilities["vibeflow.port"]["receive"]({"port": params["port"]})
        return {"number": value["value"]}


@node(id="fixture.port.send", flow_kind="io", rulesets=["vibeflow.io"],
      capabilities=[{"id": "vibeflow.port", "operations": ["send"]}],
      contract={"requires": [{"type": "answer", "cardinality": "exactly_one", "display_name": "Answer"}],
                "input_semantics": {"answer": ["Answer to send to the host"]},
                "params_schema": {"port": {"type": "string"}}, "params_defaults": {"port": "math.out"}}, node_type="vibeflow.node")
class Send:
    def run_pure(self, inputs, params, context):
        context.capabilities["vibeflow.port"]["send"]({"port": params["port"], "value": inputs["answer"]["value"]})
        return {}


@node(id="fixture.port.boundary", flow_kind="terminal", rulesets=["vibeflow.process"], contract={}, node_type="vibeflow.node")
class Boundary:
    def run_pure(self, inputs, params):
        return {}


def register_ports(registry):
    for implementation in (Receive, Send, Boundary):
        registry.register(implementation.__vibeflow_resource__.descriptor, implementation)
