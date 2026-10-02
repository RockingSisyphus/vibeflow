from __future__ import annotations

def _value(inputs, data_type: str):
    return inputs[data_type]["value"]


class StartNode:

    def run_pure(self, inputs, params):
        return {}


class InputBoundaryNode:

    def run_pure(self, inputs, params):
        return {"internal_payload": _value(inputs, "payload.request")}


class ProcessPayloadNode:

    def run_pure(self, inputs, params):
        # BUSINESS CODE: replace this pass-through with the real transformation.
        return {"processed_payload": _value(inputs, "payload.internal")}


class OutputBoundaryNode:

    def run_pure(self, inputs, params):
        return {"response": _value(inputs, "payload.processed")}


class EndNode:

    def run_pure(self, inputs, params):
        return {}
