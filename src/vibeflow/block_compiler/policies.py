"""Attach evaluated call policy data to the portable execution plan."""
from dataclasses import replace

from .model import freeze_json_object


def apply_call_policies(plan, policies):
    return replace(plan, blocks=tuple(replace(block, nodes=tuple(
        replace(call, capability_policy=freeze_json_object(policies.get((*block.path, call.id), {})))
        for call in block.nodes)) for block in plan.blocks))
