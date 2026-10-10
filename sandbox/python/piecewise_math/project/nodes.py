from vibeflow.targets.python.sdk import node
from math_resource import add





@node(**{'type_key': 'piecewise.boundary',
 'display_name': 'boundary',
 'description': 'boundary',
 'flow_kind': 'terminal',
 'rulesets': ['vibeflow.process'],
 'base_libs': [],
 'contract': {'requires': [],
              'provides': [],
              'input_semantics': {},
              'output_semantics': {},
              'params_schema': {},
              'params_defaults': {}}})
class Boundary:
    def run_pure(self, inputs, params):
        return {}


@node(**{'type_key': 'piecewise.sum_u',
 'display_name': 'sum_u',
 'description': 'sum_u',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'a', 'cardinality': 'exactly_one', 'display_name': 'a'},
                           {'type': 'b', 'cardinality': 'exactly_one', 'display_name': 'b'}],
              'provides': [{'key': 'u', 'type': 'u', 'display_name': 'u'}],
              'input_semantics': {'a': ['a'], 'b': ['b']},
              'output_semantics': {'u': ['u']},
              'params_schema': {},
              'params_defaults': {}}})
class SumU:
    def run_pure(self, inputs, params):
        return {"u": add(inputs["a"]["value"], inputs["b"]["value"])}


@node(**{'type_key': 'piecewise.sum_v',
 'display_name': 'sum_v',
 'description': 'sum_v',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'c', 'cardinality': 'exactly_one', 'display_name': 'c'},
                           {'type': 'd', 'cardinality': 'exactly_one', 'display_name': 'd'}],
              'provides': [{'key': 'v', 'type': 'v', 'display_name': 'v'}],
              'input_semantics': {'c': ['c'], 'd': ['d']},
              'output_semantics': {'v': ['v']},
              'params_schema': {},
              'params_defaults': {}}})
class SumV:
    def run_pure(self, inputs, params):
        return {"v": add(inputs["c"]["value"], inputs["d"]["value"])}


@node(**{'type_key': 'piecewise.compare',
 'display_name': 'compare',
 'description': 'compare',
 'flow_kind': 'decision',
 'rulesets': ['vibeflow.process'],
 'base_libs': [],
 'contract': {'requires': [{'type': 'u', 'cardinality': 'exactly_one', 'display_name': 'u'},
                           {'type': 'v', 'cardinality': 'exactly_one', 'display_name': 'v'}],
              'provides': [{'key': 'route', 'type': 'route', 'display_name': 'route'}],
              'input_semantics': {'u': ['u'], 'v': ['v']},
              'output_semantics': {'route': ['route']},
              'params_schema': {},
              'params_defaults': {}}})
class Compare:
    def run_pure(self, inputs, params):
        return {"route": "left" if inputs["u"]["value"] >= inputs["v"]["value"] else "right"}


@node(**{'type_key': 'piecewise.left',
 'display_name': 'left',
 'description': 'left',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'u', 'cardinality': 'exactly_one', 'display_name': 'u'}],
              'provides': [{'key': 'left.w', 'type': 'selected_w', 'display_name': 'left.w'}],
              'input_semantics': {'u': ['u']},
              'output_semantics': {'left.w': ['left.w']},
              'params_schema': {},
              'params_defaults': {}}})
class Left:
    def run_pure(self, inputs, params):
        return {"left.w": add(inputs["u"]["value"], 1)}


@node(**{'type_key': 'piecewise.right',
 'display_name': 'right',
 'description': 'right',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'v', 'cardinality': 'exactly_one', 'display_name': 'v'}],
              'provides': [{'key': 'right.w',
                            'type': 'selected_w',
                            'display_name': 'right.w'}],
              'input_semantics': {'v': ['v']},
              'output_semantics': {'right.w': ['right.w']},
              'params_schema': {},
              'params_defaults': {}}})
class Right:
    def run_pure(self, inputs, params):
        return {"right.w": add(inputs["v"]["value"], -1)}


@node(**{'type_key': 'piecewise.finish',
 'display_name': 'finish',
 'description': 'finish',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'selected_w',
                            'cardinality': 'exactly_one',
                            'display_name': 'selected_w'},
                           {'type': 'u', 'cardinality': 'exactly_one', 'display_name': 'u'}],
              'provides': [{'key': 'result', 'type': 'result', 'display_name': 'result'},
                           {'key': 'selected.key',
                            'type': 'selected.key',
                            'display_name': 'selected.key'}],
              'input_semantics': {'selected_w': ['selected_w'], 'u': ['u']},
              'output_semantics': {'result': ['result'], 'selected.key': ['selected.key']},
              'params_schema': {},
              'params_defaults': {}}})
class Finish:
    def run_pure(self, inputs, params):
        selected = inputs["selected_w"]
        return {"result": add(selected["value"], inputs["u"]["value"]), "selected.key": selected["key"]}


@node(**{'type_key': 'piecewise.left_end',
 'display_name': 'left_end',
 'description': 'left_end',
 'flow_kind': 'terminal',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'selected_w',
                            'cardinality': 'exactly_one',
                            'display_name': 'selected_w'},
                           {'type': 'u', 'cardinality': 'exactly_one', 'display_name': 'u'}],
              'provides': [{'key': 'left.result',
                            'type': 'left.result',
                            'display_name': 'left.result'}],
              'input_semantics': {'selected_w': ['selected_w'], 'u': ['u']},
              'output_semantics': {'left.result': ['left.result']},
              'params_schema': {},
              'params_defaults': {}}})
class LeftEnd:
    def run_pure(self, inputs, params):
        return {"left.result": add(inputs["selected_w"]["value"], inputs["u"]["value"])}


@node(**{'type_key': 'piecewise.right_end',
 'display_name': 'right_end',
 'description': 'right_end',
 'flow_kind': 'terminal',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'selected_w',
                            'cardinality': 'exactly_one',
                            'display_name': 'selected_w'},
                           {'type': 'u', 'cardinality': 'exactly_one', 'display_name': 'u'}],
              'provides': [{'key': 'right.result',
                            'type': 'right.result',
                            'display_name': 'right.result'}],
              'input_semantics': {'selected_w': ['selected_w'], 'u': ['u']},
              'output_semantics': {'right.result': ['right.result']},
              'params_schema': {},
              'params_defaults': {}}})
class RightEnd:
    def run_pure(self, inputs, params):
        return {"right.result": add(inputs["selected_w"]["value"], inputs["u"]["value"])}


@node(**{'type_key': 'piecewise.copy',
 'display_name': 'copy',
 'description': 'copy',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': [],
 'contract': {'requires': [{'type': 'selected_w',
                            'cardinality': 'exactly_one',
                            'display_name': 'selected_w'}],
              'provides': [{'key': 'copied', 'type': 'copied', 'display_name': 'copied'}],
              'input_semantics': {'selected_w': ['selected_w']},
              'output_semantics': {'copied': ['copied']},
              'params_schema': {},
              'params_defaults': {}}})
class Copy:
    def run_pure(self, inputs, params):
        return {"copied": inputs["selected_w"]["value"]}


@node(**{'type_key': 'piecewise.linear_finish',
 'display_name': 'linear_finish',
 'description': 'linear_finish',
 'flow_kind': 'process',
 'rulesets': ['vibeflow.process'],
 'base_libs': ['piecewise.math'],
 'contract': {'requires': [{'type': 'copied',
                            'cardinality': 'exactly_one',
                            'display_name': 'copied'}],
              'provides': [{'key': 'result', 'type': 'result', 'display_name': 'result'}],
              'input_semantics': {'copied': ['copied']},
              'output_semantics': {'result': ['result']},
              'params_schema': {},
              'params_defaults': {}}})
class LinearFinish:
    def run_pure(self, inputs, params):
        return {"result": add(inputs["copied"]["value"], -1)}
