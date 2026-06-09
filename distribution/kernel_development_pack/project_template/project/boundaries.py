from __future__ import annotations


class DemoBoundary:
    def before_run(self, run_config):
        return {}

    def after_run(self, outputs, run_config):
        return {}

    def before_iteration(self, iteration, state):
        return {}

    def after_iteration(self, iteration, outputs, state):
        return {}

