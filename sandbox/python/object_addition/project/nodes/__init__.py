from vibeflow.targets.python.sdk import node
from base_lib.math_resource import add

def value(inputs, key):
    return inputs[key]["value"]

@node(**{'node_type': 'vibeflow.node', 'id': 'addition.boundary', 'display_name': 'Boundary', 'description': 'Boundary', 'flow_kind': 'terminal', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [], 'provides': [], 'input_semantics': {}, 'output_semantics': {}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Boundary:
    def run_pure(self, inputs, params):
        return {}

@node(**{'node_type': 'vibeflow.node', 'id': 'addition.add', 'display_name': 'Add', 'description': 'Add', 'flow_kind': 'process', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'object.box', 'cardinality': 'exactly_one', 'display_name': 'object.box'}, {'type': 'object.counter', 'cardinality': 'exactly_one', 'display_name': 'object.counter'}], 'provides': [{'key': 'object.box_after', 'type': 'object.box_after', 'display_name': 'object.box_after'}, {'key': 'object.counter_input', 'type': 'object.counter', 'display_name': 'object.counter'}], 'input_semantics': {'object.box': ['object.box'], 'object.counter': ['object.counter']}, 'output_semantics': {'object.box_after': ['object.box_after'], 'object.counter_input': ['object.counter']}, 'params_schema': {'delta': {'type': 'number'}}, 'params_defaults': {'delta': 1}}, 'base_libs': ['addition.math']})
class Add:
    def run_pure(self, inputs, params):
        box = value(inputs, "object.box")
        box.value = add(box.value, params["delta"])
        return {"object.box_after": box, "object.counter_input": value(inputs, "object.counter")}

@node(**{'node_type': 'vibeflow.node', 'id': 'addition.report', 'display_name': 'Report', 'description': 'Report', 'flow_kind': 'process', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'object.box_after', 'cardinality': 'exactly_one', 'display_name': 'object.box_after'}, {'type': 'object.counter', 'cardinality': 'exactly_one', 'display_name': 'object.counter'}], 'provides': [{'key': 'object.counter_after', 'type': 'object.counter_after', 'display_name': 'object.counter_after'}, {'key': 'object.snapshot', 'type': 'object.snapshot', 'display_name': 'object.snapshot'}, {'key': 'object.metadata', 'type': 'object.metadata', 'display_name': 'object.metadata'}, {'key': 'object.value', 'type': 'object.value', 'display_name': 'object.value'}, {'key': 'object.done', 'type': 'object.done', 'display_name': 'object.done'}], 'input_semantics': {'object.box_after': ['object.box_after'], 'object.counter': ['object.counter']}, 'output_semantics': {'object.counter_after': ['object.counter_after'], 'object.snapshot': ['object.snapshot'], 'object.metadata': ['object.metadata'], 'object.value': ['object.value'], 'object.done': ['object.done']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Report:
    def run_pure(self, inputs, params):
        box = value(inputs, "object.box_after")
        counter = value(inputs, "object.counter")
        counter.steps += 1
        return {"object.counter_after": counter, "object.snapshot": {"value": box.value, "steps": counter.steps}, "object.metadata": {"box": box, "tags": {"sandbox", "add"}, "unstable": float("nan")}, "object.value": box.value, "object.done": counter.steps >= 2}
