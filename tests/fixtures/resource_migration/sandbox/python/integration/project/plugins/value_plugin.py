from __future__ import annotations

from vibeflow.targets.python.project import PluginInfo
from plugins import value_state


PLUGIN_INFO = PluginInfo(
    name="sandbox_value_shift",
    plugin_type="runtime",
    display_name="Sandbox Value Shift",
    category="runtime",
    description="Configures a pure value shift helper used by sandbox resource arithmetic.",
    version="0.1.0",
)

class ValueShiftPlugin:
    name = "sandbox_value_shift"
    priority = 5
    PLUGIN_INFO = PLUGIN_INFO

    def configure(self, config):
        value_state.SHIFT_BY = config.get("shift", 0)
