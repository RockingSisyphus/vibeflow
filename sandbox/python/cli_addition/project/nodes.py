from vibeflow.targets.python.sdk import node
from math_resource import total

def value(inputs, key):
    return inputs[key]["value"]

@node(**{'type_key': 'addition.boundary', 'display_name': 'Boundary', 'description': 'Boundary', 'flow_kind': 'terminal', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [], 'provides': [], 'input_semantics': {}, 'output_semantics': {}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Boundary:
    def run_pure(self, inputs, params):
        return {}

@node(**{'type_key': 'addition.argv', 'display_name': 'Argv', 'description': 'Argv', 'flow_kind': 'io', 'rulesets': ['vibeflow.io'], 'contract': {'requires': [{'type': 'cli.argv', 'cardinality': 'exactly_one', 'display_name': 'cli.argv'}], 'provides': [{'key': 'cli.left', 'type': 'cli.left', 'display_name': 'cli.left'}, {'key': 'cli.right', 'type': 'cli.right', 'display_name': 'cli.right'}, {'key': 'cli.output', 'type': 'cli.output', 'display_name': 'cli.output'}, {'key': 'cli.verbose', 'type': 'cli.verbose', 'display_name': 'cli.verbose'}], 'input_semantics': {'cli.argv': ['cli.argv']}, 'output_semantics': {'cli.left': ['cli.left'], 'cli.right': ['cli.right'], 'cli.output': ['cli.output'], 'cli.verbose': ['cli.verbose']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Argv:
    def run_pure(self, inputs, params):
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--left", required=True)
        parser.add_argument("--right", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--verbose", action="store_true")
        args = parser.parse_args(list(value(inputs, "cli.argv")))
        return {"cli.left": args.left, "cli.right": args.right, "cli.output": args.output, "cli.verbose": args.verbose}

@node(**{'type_key': 'addition.input', 'display_name': 'Input', 'description': 'Input', 'flow_kind': 'io', 'rulesets': ['vibeflow.io'], 'contract': {'requires': [], 'provides': [{'key': 'number.stdin', 'type': 'number.stdin', 'display_name': 'number.stdin'}], 'input_semantics': {}, 'output_semantics': {'number.stdin': ['number.stdin']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Input:
    def run_pure(self, inputs, params):
        return {"number.stdin": int(input())}

@node(**{'type_key': 'addition.stream_input', 'display_name': 'StreamInput', 'description': 'StreamInput', 'flow_kind': 'io', 'rulesets': ['vibeflow.io'], 'contract': {'requires': [], 'provides': [{'key': 'number.stdin', 'type': 'number.stdin', 'display_name': 'number.stdin'}], 'input_semantics': {}, 'output_semantics': {'number.stdin': ['number.stdin']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class StreamInput:
    def run_pure(self, inputs, params):
        import sys
        return {"number.stdin": int(sys.stdin.readline())}

@node(**{'type_key': 'addition.path_left', 'display_name': 'PathLeft', 'description': 'PathLeft', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.left', 'cardinality': 'exactly_one', 'display_name': 'cli.left'}], 'provides': [{'key': 'number.left', 'type': 'number.left', 'display_name': 'number.left'}], 'input_semantics': {'cli.left': ['cli.left']}, 'output_semantics': {'number.left': ['number.left']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class PathLeft:
    def run_pure(self, inputs, params):
        from pathlib import Path
        return {"number.left": int(Path(value(inputs, "cli.left")).read_text(encoding="utf-8"))}

@node(**{'type_key': 'addition.open_left', 'display_name': 'OpenLeft', 'description': 'OpenLeft', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.left', 'cardinality': 'exactly_one', 'display_name': 'cli.left'}], 'provides': [{'key': 'number.left', 'type': 'number.left', 'display_name': 'number.left'}], 'input_semantics': {'cli.left': ['cli.left']}, 'output_semantics': {'number.left': ['number.left']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class OpenLeft:
    def run_pure(self, inputs, params):
        import builtins
        with builtins.open(value(inputs, "cli.left"), encoding="utf-8") as handle:
            text = handle.read()
        return {"number.left": int(text)}

@node(**{'type_key': 'addition.path_right', 'display_name': 'PathRight', 'description': 'PathRight', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.right', 'cardinality': 'exactly_one', 'display_name': 'cli.right'}], 'provides': [{'key': 'number.right', 'type': 'number.right', 'display_name': 'number.right'}], 'input_semantics': {'cli.right': ['cli.right']}, 'output_semantics': {'number.right': ['number.right']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class PathRight:
    def run_pure(self, inputs, params):
        from pathlib import Path
        return {"number.right": int(Path(value(inputs, "cli.right")).read_text(encoding="utf-8"))}

@node(**{'type_key': 'addition.open_right', 'display_name': 'OpenRight', 'description': 'OpenRight', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.right', 'cardinality': 'exactly_one', 'display_name': 'cli.right'}], 'provides': [{'key': 'number.right', 'type': 'number.right', 'display_name': 'number.right'}], 'input_semantics': {'cli.right': ['cli.right']}, 'output_semantics': {'number.right': ['number.right']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class OpenRight:
    def run_pure(self, inputs, params):
        import builtins
        with builtins.open(value(inputs, "cli.right"), encoding="utf-8") as handle:
            text = handle.readline()
        return {"number.right": int(text)}

@node(**{'type_key': 'addition.yaml', 'display_name': 'Yaml', 'description': 'Yaml', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.left', 'cardinality': 'exactly_one', 'display_name': 'cli.left'}], 'provides': [{'key': 'number.left', 'type': 'number.left', 'display_name': 'number.left'}, {'key': 'number.right', 'type': 'number.right', 'display_name': 'number.right'}], 'input_semantics': {'cli.left': ['cli.left']}, 'output_semantics': {'number.left': ['number.left'], 'number.right': ['number.right']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Yaml:
    def run_pure(self, inputs, params):
        import yaml
        from pathlib import Path
        payload = yaml.safe_load(Path(value(inputs, "cli.left")).read_text(encoding="utf-8"))
        return {"number.left": payload["left"], "number.right": payload["right"]}

@node(**{'type_key': 'addition.sum', 'display_name': 'Sum', 'description': 'Sum', 'flow_kind': 'process', 'rulesets': ['vibeflow.process'], 'contract': {'requires': [{'type': 'number.left', 'cardinality': 'exactly_one', 'display_name': 'number.left'}, {'type': 'number.right', 'cardinality': 'exactly_one', 'display_name': 'number.right'}, {'type': 'number.stdin', 'cardinality': 'exactly_one', 'display_name': 'number.stdin'}], 'provides': [{'key': 'number.total', 'type': 'number.total', 'display_name': 'number.total'}], 'input_semantics': {'number.left': ['number.left'], 'number.right': ['number.right'], 'number.stdin': ['number.stdin']}, 'output_semantics': {'number.total': ['number.total']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': ['addition.math']})
class Sum:
    def run_pure(self, inputs, params):
        return {"number.total": total(value(inputs, "number.left"), value(inputs, "number.right"), value(inputs, "number.stdin"))}

@node(**{'type_key': 'addition.path_write', 'display_name': 'PathWrite', 'description': 'PathWrite', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.output', 'cardinality': 'exactly_one', 'display_name': 'cli.output'}, {'type': 'number.total', 'cardinality': 'exactly_one', 'display_name': 'number.total'}], 'provides': [{'key': 'document.written', 'type': 'document.written', 'display_name': 'document.written'}], 'input_semantics': {'cli.output': ['cli.output'], 'number.total': ['number.total']}, 'output_semantics': {'document.written': ['document.written']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class PathWrite:
    def run_pure(self, inputs, params):
        from pathlib import Path
        path = value(inputs, "cli.output")
        Path(path).write_text(str(value(inputs, "number.total")) + "\n", encoding="utf-8")
        return {"document.written": path}

@node(**{'type_key': 'addition.open_write', 'display_name': 'OpenWrite', 'description': 'OpenWrite', 'flow_kind': 'document', 'rulesets': ['vibeflow.document'], 'contract': {'requires': [{'type': 'cli.output', 'cardinality': 'exactly_one', 'display_name': 'cli.output'}, {'type': 'number.total', 'cardinality': 'exactly_one', 'display_name': 'number.total'}], 'provides': [{'key': 'document.written', 'type': 'document.written', 'display_name': 'document.written'}], 'input_semantics': {'cli.output': ['cli.output'], 'number.total': ['number.total']}, 'output_semantics': {'document.written': ['document.written']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class OpenWrite:
    def run_pure(self, inputs, params):
        import builtins
        path = value(inputs, "cli.output")
        with builtins.open(path, "w", encoding="utf-8") as handle:
            handle.write(str(value(inputs, "number.total")) + "\n")
        return {"document.written": path}

@node(**{'type_key': 'addition.print', 'display_name': 'Print', 'description': 'Print', 'flow_kind': 'io', 'rulesets': ['vibeflow.io'], 'contract': {'requires': [{'type': 'number.total', 'cardinality': 'exactly_one', 'display_name': 'number.total'}, {'type': 'document.written', 'cardinality': 'exactly_one', 'display_name': 'document.written'}, {'type': 'cli.verbose', 'cardinality': 'exactly_one', 'display_name': 'cli.verbose'}], 'provides': [{'key': 'cli.exit_code', 'type': 'cli.exit_code', 'display_name': 'cli.exit_code'}], 'input_semantics': {'number.total': ['number.total'], 'document.written': ['document.written'], 'cli.verbose': ['cli.verbose']}, 'output_semantics': {'cli.exit_code': ['cli.exit_code']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Print:
    def run_pure(self, inputs, params):
        import sys
        print("sum=" + str(value(inputs, "number.total")))
        if value(inputs, "cli.verbose"):
            sys.stderr.write("writer=pathlib\n")
        return {"cli.exit_code": 0}

@node(**{'type_key': 'addition.streams', 'display_name': 'Streams', 'description': 'Streams', 'flow_kind': 'io', 'rulesets': ['vibeflow.io'], 'contract': {'requires': [{'type': 'number.total', 'cardinality': 'exactly_one', 'display_name': 'number.total'}, {'type': 'document.written', 'cardinality': 'exactly_one', 'display_name': 'document.written'}, {'type': 'cli.verbose', 'cardinality': 'exactly_one', 'display_name': 'cli.verbose'}], 'provides': [{'key': 'cli.exit_code', 'type': 'cli.exit_code', 'display_name': 'cli.exit_code'}], 'input_semantics': {'number.total': ['number.total'], 'document.written': ['document.written'], 'cli.verbose': ['cli.verbose']}, 'output_semantics': {'cli.exit_code': ['cli.exit_code']}, 'params_schema': {}, 'params_defaults': {}}, 'base_libs': []})
class Streams:
    def run_pure(self, inputs, params):
        import sys
        sys.stdout.write("sum=" + str(value(inputs, "number.total")) + "\n")
        if value(inputs, "cli.verbose"):
            sys.stderr.write("writer=open\n")
        return {"cli.exit_code": 0}

