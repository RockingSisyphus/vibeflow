"""Workflow relationships projected from effective operation facts."""
import json
from urllib.parse import quote
from vibeflow.core.workflows.references import action_references


def workflow_relations(architecture, workflow):
    result = []
    for path, policy in architecture.get("call_policies", {}).items():
        for action in policy.get("actions", ()):
            for reference in action_references(action):
                result.append({"from_root":workflow["root_id"], "from_workflow":workflow["path"],
                    "from_call_path":"/".join(quote(part, safe="'()*!") for part in json.loads(path)),
                    "to_root":reference["root"], "to_workflow":reference["path"],
                    "entry":reference.get("entry"), "kind":action["operation"],
                    "expected":action["operation"] in {"send", "receive"},
                    "label":action["operation"] + (" · 预期交互" if action["operation"] in {"send","receive"} else "")})
    return result
