from vibeflow.targets.python.sdk import node

@node(**{'node_type': 'vibeflow.node', 'id': 'math.offset', 'display_name': 'Offset', 'description': 'Offset in the composite formula.', 'version': '1.0.0', 'flow_kind': 'process', 'contract': {'requires': [{'type': 'math.offset', 'cardinality': 'optional_one', 'display_name': 'math.offset'}], 'provides': [{'key': 'offset', 'type': 'math.offset_value', 'display_name': 'offset'}], 'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'math.offset': ['math.offset']}, 'output_semantics': {'offset': ['math.offset_value']}}, 'rulesets': ['math.process'], 'tags': ['comprehensive-math']})
class Offset:
    def run_pure(self, inputs, params):
        offset = inputs["math.offset"]
        return {"offset": offset["value"] if offset else 0}
