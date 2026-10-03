def run_stub(inputs, params):
    return {"calc.scaled": inputs["calc.sum"]["value"] * params["factor"] + params["_global"]["bias"]}
