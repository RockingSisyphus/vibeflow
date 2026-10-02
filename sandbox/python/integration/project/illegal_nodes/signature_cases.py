from __future__ import annotations

class MissingRunPureNode:
    pass

class ContextRunNode:

    def run(self, context):
        return context

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class TooManyParamsNode:

    def run_pure(self, inputs, params, extra):
        return {'bad.out': 1}

class VarArgsNode:

    def run_pure(self, inputs, params, *args):
        return {'bad.out': 1}

class PublicHelperNode:

    def helper(self):
        return 1

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class InitWithClientNode:

    def __init__(self, client):
        self.client = client

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class ResourceFieldNode:

    def __init__(self):
        self.session = None

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class AsyncRunPureNode:

    async def run_pure(self, inputs, params):
        return {'bad.out': 1}

class GeneratorRunPureNode:

    def run_pure(self, inputs, params):
        yield {'bad.out': 1}
