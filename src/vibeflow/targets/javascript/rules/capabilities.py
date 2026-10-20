"""Explicit call grants and graph restrictions for this Target."""
from vibeflow.core.rules import RuleDescriptor
from vibeflow.core.workflows.policies import POLICY_TYPE


def policy_rule_resources():
    return (
        RuleDescriptor("vibeflow.capability.allow", scope="call", outputs={"policy": POLICY_TYPE},
            params_schema={"capability":{"type":"string"}, "operations":{"type":"array","items":{"type":"string"}},
                           "actions":{"type":"array","items":{"type":"object"}}},
            params_defaults={"capability":"", "operations":[], "actions":[]}),
        RuleDescriptor("vibeflow.capability.restrict", scope="call", outputs={"policy": POLICY_TYPE},
            params_schema={"capabilities":{"type":"array","items":{"type":"string"}}},
            params_defaults={"capabilities":["vibeflow.port","vibeflow.workflow"]}),
    )
