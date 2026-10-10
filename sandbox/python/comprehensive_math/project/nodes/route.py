from vibeflow.targets.python.sdk import node

@node(**{'type_key': 'math.route', 'display_name': 'Route', 'description': 'Route in the composite formula.', 'version': '1.0.0', 'flow_kind': 'decision', 'contract': {'requires': [{'type': 'math.q', 'cardinality': 'exactly_one', 'display_name': 'math.q'}], 'provides': [{'key': 'routed', 'type': 'math.routed', 'display_name': 'routed'}, {'key': 'nonnegative', 'type': 'math.nonnegative', 'display_name': 'nonnegative'}], 'params_schema': {}, 'params_defaults': {}, 'input_semantics': {'math.q': ['math.q']}, 'output_semantics': {'routed': ['math.routed'], 'nonnegative': ['math.nonnegative']}}, 'rulesets': ['math.process'], 'tags': ['comprehensive-math']})
class Route:
    def run_pure(self, inputs, params):
        q = inputs["math.q"]["value"]
        return {"routed": q, "nonnegative": q >= 0}
