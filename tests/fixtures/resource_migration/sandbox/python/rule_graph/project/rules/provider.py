"""A facts provider: findings and availability are independent."""
import json
from pathlib import Path


def check(context, inputs, params):
    mode = params["mode"]
    value = [] if mode == "empty" else [params["value"]]
    if params["marker"]:
        with Path(params["marker"]).open("a") as stream:
            stream.write(json.dumps({"handler": "provider", "phase": context.phase,
                "call": context.subject.get("rule_call_id"), "numbers": value}) + "\n")
    findings = []
    if mode in ("warning", "error"):
        findings.append({"code": "EXAMPLE.PROVIDER.FINDING", "severity": mode,
            "message": "A provider can report a finding while supplying valid facts.",
            "source_location": {"path": __file__, "line": 8, "column": 1}})
    if mode in ("failed", "unavailable"):
        return {"state": mode, "findings": findings}
    if mode == "missing":
        return {"records": {}, "findings": findings}
    return {"records": {"numbers": {"type_id": "example.wrong.v1" if mode == "wrong_type" else "example.numbers.v1",
        "value": value}}, "findings": findings}


def replacement(context, inputs, params):
    result = check(context, inputs, {**params, "value": params["value"] + 10})
    return result
