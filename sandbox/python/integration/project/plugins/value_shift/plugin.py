from __future__ import annotations

from vibeflow.targets.python.sdk import Plugin, RuleCall, ruleset
from . import value_state
from .value_state import plugin_shift
from vibeflow.targets.python.sdk import base_lib, node_type


class ValueShiftPlugin:
    def configure(self, config):
        value_state.SHIFT_BY = config.get("shift", 0)


def create(context):
    instance = ValueShiftPlugin()
    instance.configure(context["config"])
    return instance


review = ruleset(
    id="sandbox.value_plugin",
    calls=[
        RuleCall("imports", rule_id="vibeflow.import_side_effects"),
        RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope": "global_state"}),
        RuleCall("interface", rule_id="vibeflow.node_interface"),
    ],
    entrypoints={"import": ["imports"], "static": ["effects", "interface"], "run": ["effects", "interface"]},
)
arithmetic_type = node_type(id="value_shift.arithmetic", rulesets=["sandbox.value_plugin"])
@base_lib(id="value_shift.math", rulesets=[])
def private_math(value):
    return plugin_shift(value)

plugin = Plugin(
    id="value_shift", resources=[review, arithmetic_type, private_math], runtime=create, priority=5,
    rulesets=["sandbox.value_plugin"],
    implementation_files=["value_state.py"],
    display_name="Sandbox Value Shift",
    description="Configures a value shift helper used by sandbox resource arithmetic.",
    config_schema={"type": "object", "properties": {"shift": {"type": "number"}}, "additionalProperties": False},
    config_defaults={"shift": 0}, version="0.1.0",
)
