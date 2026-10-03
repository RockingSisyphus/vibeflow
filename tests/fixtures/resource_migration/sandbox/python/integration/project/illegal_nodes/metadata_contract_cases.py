from __future__ import annotations

class MissingInfoNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class InfoWrongTypeNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class EmptyTypeKeyNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class NonPureNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class MissingContractNode:

    def run_pure(self, inputs, params):
        return {'bad.out': 1}

class DuplicateKeysNode:

    def run_pure(self, inputs, params):
        return {'bad.out': inputs['bad.in']}

class MissingSemanticsNode:

    def run_pure(self, inputs, params):
        return {'bad.out': inputs['bad.in']}
