from __future__ import annotations


class DemoBoundary:
    def before_run(self, run_config):
        return {}

    def after_run(self, outputs, run_config):
        return {}

    def before_iteration(self, iteration, state):
        return {}

    def after_iteration(self, iteration, outputs, state):
        request = outputs.get("effects.request", {})
        if isinstance(request, dict) and "value" in request:
            return {"io.result": request["value"] + 10}
        return {}
