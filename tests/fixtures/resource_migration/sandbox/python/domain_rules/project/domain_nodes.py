"""Execution classes; all Node declarations live in the domain bundle."""

from domain_helpers.arithmetic import scale


class Boundary:
    def run_pure(self, inputs, params):
        return {}


class ModelBlock:
    def model_forward(self, value, gain):
        return scale(value, gain)

    def run_pure(self, inputs, params):
        value = inputs["example.input"]["value"]
        return {"feature": self.model_forward(value, params["gain"])}


class DataTransform:
    def run_pure(self, inputs, params):
        value = inputs["example.feature"]["value"]
        return {"result": value + params["offset"]}
