from __future__ import annotations

from base_lib.deep_chain_a import step_a


class DeepBaseLibNode:
    def run_pure(self, inputs, params):
        return {"bad.out": step_a(1)}
