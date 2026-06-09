from __future__ import annotations


class RaisePolicyPlugin:
    name = "sandbox_raise_policy"

    def extend_policy(self, policy):
        raise RuntimeError("policy boom")


class RelaxPolicyPlugin:
    name = "sandbox_relax_policy"

    def extend_policy(self, policy):
        return {"imports": {"allowed_roots": ["numpy"]}}


class BadShapePlugin:
    name = "sandbox_bad_shape"

    def extend_policy(self, policy):
        return ["not", "an", "object"]
