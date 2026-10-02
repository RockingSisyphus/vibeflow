"""Execution only; registration and audit selection live in the bundle."""

class Boundary:
    def run_pure(self, inputs, params):
        return {}

class Calculate:
    def run_pure(self, inputs, params):
        return {"result": inputs["example.input"]["value"] * 2 + 1}
