from vibeflow.targets.python.sdk import node

@node(**{'type_key': 'math.negative', 'display_name': 'Negative', 'description': 'Negative in the composite formula.', 'version': '1.0.0', 'flow_kind': 'process', 'contract': {'requires': [{'type': 'math.routed', 'cardinality': 'exactly_one', 'display_name': 'math.routed'}], 'provides': [{'key': 'negative', 'type': 'math.negative', 'display_name': 'negative'}], 'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'math.routed': ['math.routed']}, 'output_semantics': {'negative': ['math.negative']}}, 'rulesets': ['math.process'], 'tags': ['comprehensive-math']})
class Negative:
    def run_pure(self, inputs, params):
        return {"negative": -inputs["math.routed"]["value"] + 3}
