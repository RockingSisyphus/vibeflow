from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class NumericArgvNode:

    def run_pure(self, inputs, params):
        import argparse
        parser = argparse.ArgumentParser(prog='vibeflow-numeric')
        parser.add_argument('--left', required=True)
        parser.add_argument('--right', required=True)
        parser.add_argument('--output', required=True)
        parsed = parser.parse_args(list(VALUE(inputs, 'cli.argv')))
        return {'cli.left_path': parsed.left, 'cli.right_path': parsed.right, 'cli.output_path': parsed.output}

class NumericBuiltinInputNode:

    def run_pure(self, inputs, params):
        return {'number.stdin': int(input())}

class NumericStreamInputNode:

    def run_pure(self, inputs, params):
        import sys
        return {'number.stdin': int(sys.stdin.readline())}

class NumericPathLeftNode:

    def run_pure(self, inputs, params):
        from pathlib import Path
        text = Path(VALUE(inputs, 'cli.left_path')).read_text(encoding='utf-8')
        return {'number.left': int(text)}

class NumericPathRightNode:

    def run_pure(self, inputs, params):
        from pathlib import Path
        text = Path(VALUE(inputs, 'cli.right_path')).read_text(encoding='utf-8')
        return {'number.right': int(text)}

class NumericOpenLeftNode:

    def run_pure(self, inputs, params):
        import builtins
        with builtins.open(VALUE(inputs, 'cli.left_path'), 'r', encoding='utf-8') as handle:
            text = handle.read()
        return {'number.left': int(text)}

class NumericOpenRightNode:

    def run_pure(self, inputs, params):
        import builtins
        with builtins.open(VALUE(inputs, 'cli.right_path'), 'r', encoding='utf-8') as handle:
            text = handle.readline()
        return {'number.right': int(text)}

class NumericSumNode:

    def run_pure(self, inputs, params):
        total = VALUE(inputs, 'number.stdin') + VALUE(inputs, 'number.left')
        return {'number.total': total + VALUE(inputs, 'number.right')}

class NumericPathWriterNode:

    def run_pure(self, inputs, params):
        from pathlib import Path
        output_path = VALUE(inputs, 'cli.output_path')
        Path(output_path).write_text(f"{VALUE(inputs, 'number.total')}\n", encoding='utf-8')
        return {'document.output_written': output_path}

class NumericOpenWriterNode:

    def run_pure(self, inputs, params):
        import builtins
        output_path = VALUE(inputs, 'cli.output_path')
        with builtins.open(output_path, 'w', encoding='utf-8') as handle:
            handle.write(f"{VALUE(inputs, 'number.total')}\n")
        return {'document.output_written': output_path}

class NumericPrintOutputNode:

    def run_pure(self, inputs, params):
        import sys
        print(f"sum={VALUE(inputs, 'number.total')}")
        sys.stderr.write('writer=pathlib\n')
        return {'cli.exit_code': 0}

class NumericStreamOutputNode:

    def run_pure(self, inputs, params):
        import sys
        sys.stdout.write(f"sum={VALUE(inputs, 'number.total')}\n")
        sys.stderr.write('writer=open\n')
        return {'cli.exit_code': 0}
