from __future__ import annotations

def VALUE(inputs, data_type: str):
    return inputs[data_type]['value']

class DelegateArgvNode:

    def run_pure(self, inputs, params):
        import argparse
        parser = argparse.ArgumentParser(prog='vibeflow-sandbox')
        parser.add_argument('--input', required=True)
        parser.add_argument('--verbose', action='store_true')
        parsed = parser.parse_args(list(VALUE(inputs, 'cli.argv')))
        return {'cli.input_path': parsed.input, 'cli.verbose': parsed.verbose}

class DelegateDocumentNode:

    def run_pure(self, inputs, params):
        import json
        from pathlib import Path
        payload = json.loads(Path(VALUE(inputs, 'cli.input_path')).read_text(encoding='utf-8'))
        return {'document.message': str(payload['message'])}

class DelegateBusinessNode:

    def run_pure(self, inputs, params):
        return {'business.message': f"processed:{VALUE(inputs, 'document.message')}"}

class DelegateOutputNode:

    def run_pure(self, inputs, params):
        import sys
        print(VALUE(inputs, 'business.message'))
        if VALUE(inputs, 'cli.verbose'):
            print('verbose:delegate-cli', file=sys.stderr)
        return {'cli.exit_code': 0}

class DelegateEndNode:

    def run_pure(self, inputs, params):
        return {}
