from vibeflow.targets.python.sdk import node

@node(**{'type_key': 'math.step', 'display_name': 'Step', 'description': 'Step in the composite formula.', 'version': '1.0.0', 'flow_kind': 'process', 'contract': {'requires': [{'type': 'math.value', 'cardinality': 'exactly_one', 'display_name': 'math.value'}, {'type': 'math.counter', 'cardinality': 'exactly_one', 'display_name': 'math.counter'}], 'provides': [{'key': 'next', 'type': 'math.next', 'display_name': 'next'}, {'key': 'counter', 'type': 'math.next_counter', 'display_name': 'counter'}, {'key': 'done', 'type': 'math.done', 'display_name': 'done'}], 'params_schema': {'increment': {'type': 'number'}, 'stop_after': {'type': 'integer'}}, 'params_defaults': {'increment': 2, 'stop_after': 3}, 'input_semantics': {'math.value': ['math.value'], 'math.counter': ['math.counter']}, 'output_semantics': {'next': ['math.next'], 'counter': ['math.next_counter'], 'done': ['math.done']}}, 'rulesets': ['math.process'], 'tags': ['comprehensive-math']})
class Step:
    def run_pure(self, inputs, params):
        counter = inputs["math.counter"]["value"] + 1
        return {"next": inputs["math.value"]["value"] + params["increment"], "counter": counter, "done": counter >= params["stop_after"]}
