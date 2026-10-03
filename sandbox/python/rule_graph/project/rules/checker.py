"""A consumer receives the engine-bound typed record, never fake empty facts."""

from vibeflow.targets.python.sdk import rule
import json
from pathlib import Path


@rule(**{'id': 'example.number_checker',
 'description': 'Consume facts bound by the requires relation.',
 'scope': 'call',
 'params_schema': {'marker': {'type': 'string'}},
 'params_defaults': {'marker': ''},
 'inputs': {'numbers': 'example.numbers.v1'},
 'outputs': {'proof': 'example.proof.v1'}})
def check(context, inputs, params):
    record = inputs["numbers"]
    proof = {"handler": "checker", "phase": context.phase,
        "call": context.subject.get("rule_call_id"), "type_id": record.type_id,
        "numbers": list(record.value), "total": sum(record.value)}
    if params["marker"]:
        with Path(params["marker"]).open("a") as stream:
            stream.write(json.dumps(proof) + "\n")
    return {"records": {"proof": {"type_id": "example.proof.v1", "value": proof}}}
