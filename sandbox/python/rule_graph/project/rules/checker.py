"""A consumer receives the engine-bound typed record, never fake empty facts."""
import json
from pathlib import Path


def check(context, inputs, params):
    record = inputs["numbers"]
    proof = {"handler": "checker", "phase": context.phase,
        "call": context.subject.get("rule_call_id"), "type_id": record.type_id,
        "numbers": list(record.value), "total": sum(record.value)}
    if params["marker"]:
        with Path(params["marker"]).open("a") as stream:
            stream.write(json.dumps(proof) + "\n")
    return {"records": {"proof": {"type_id": "example.proof.v1", "value": proof}}}
