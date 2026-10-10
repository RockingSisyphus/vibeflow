from vibeflow.targets.python.sdk import node

@node(**{'type_key': 'math.square', 'display_name': 'Square', 'description': 'Square in the composite formula.', 'version': '1.0.0', 'flow_kind': 'process', 'contract': {'requires': [{'type': 'math.routed', 'cardinality': 'exactly_one', 'display_name': 'math.routed'}], 'provides': [{'key': 'positive', 'type': 'math.positive', 'display_name': 'positive'}], 'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'math.routed': ['math.routed']}, 'output_semantics': {'positive': ['math.positive']}}, 'rulesets': ['math.process', 'math.source_rules'], 'tags': ['comprehensive-math']})
class Square:
    def run_pure(self, inputs, params):
        return {"positive": inputs["math.routed"]["value"] ** 2}
