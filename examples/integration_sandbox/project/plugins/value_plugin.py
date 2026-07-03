from __future__ import annotations

from vibeflow import PluginInfo


PLUGIN_INFO = PluginInfo(
    name="sandbox_value_shift",
    plugin_type="runtime",
    display_name="Sandbox Value Shift",
    category="runtime",
    description="Configures a pure value shift helper used by sandbox resource arithmetic.",
    version="0.1.0",
)

SHIFT_BY = 0


def plugin_shift(value: int | float) -> int | float:
    return value + SHIFT_BY


class ValueShiftPlugin:
    name = "sandbox_value_shift"
    priority = 5
    PLUGIN_INFO = PLUGIN_INFO

    def configure(self, config):
        global SHIFT_BY
        SHIFT_BY = config.get("shift", 0)
