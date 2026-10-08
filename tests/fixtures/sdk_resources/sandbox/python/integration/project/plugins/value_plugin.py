from __future__ import annotations

from plugins import value_state



class ValueShiftPlugin:
    name = "sandbox_value_shift"
    priority = 5

    def configure(self, config):
        value_state.SHIFT_BY = config.get("shift", 0)
