"""Pure execution fixtures; their declarations live in a separate module."""

from __future__ import annotations


def V(inputs, data_type: str):
    return inputs[data_type]["value"]


class StartNode:

    def run_pure(self, inputs, params):
        return {}


class ValueInputNode:

    def run_pure(self, inputs, params):
        return {}


class OutEndNode:

    def run_pure(self, inputs, params):
        return {}


class InEndNode:

    def run_pure(self, inputs, params):
        return {}


class SeedNode:

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class LargePredictionNode:

    def run_pure(self, inputs, params):
        return {"value.out": {f"sample_{index:04d}": index for index in range(1000)}}


class AddNode:

    def run_pure(self, inputs, params):
        return {"value.out": V(inputs, "value.in") + params.get("delta", 1)}


class CopyNode:

    def run_pure(self, inputs, params):
        return {"value.in": V(inputs, "value.out")}


class RouteNode:

    def run_pure(self, inputs, params):
        return {"flow.route": "done"}


class NanOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": float("nan")}


class EffectRequestNode:

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": V(inputs, "value.in")}}


class SetOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class OpaqueOutputNode:

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class MutatingInputNode:

    def run_pure(self, inputs, params):
        V(inputs, "value.in").append(3)
        return {"value.out": V(inputs, "value.in")}


class IdentityObjectNode:

    def run_pure(self, inputs, params):
        return {"value.out": V(inputs, "value.in")}


class RuntimeFailNode:

    def run_pure(self, inputs, params):
        if params.get("fail", False):
            raise RuntimeError("boom")
        return {"value.out": 1}


class CountingInitNode:
    instances = 0


    def __init__(self) -> None:
        type(self).instances += 1

    def run_pure(self, inputs, params):
        return {"value.out": params.get("value", 3)}


class DuplicateOneNode:

    def run_pure(self, inputs, params):
        return {"dup.one": 1}


class DuplicateTwoNode:

    def run_pure(self, inputs, params):
        return {"dup.two": 1}


class DuplicateThreeNode:

    def run_pure(self, inputs, params):
        return {"dup.three": 1}


class SinkNode:

    def run_pure(self, inputs, params):
        return {}


class GlobalParamNode:

    def run_pure(self, inputs, params):
        return {"value.out": params["_global"]["offset"]}
