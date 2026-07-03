from __future__ import annotations

from vibeflow import PluginInfo


class RaisePolicyPlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_raise_policy",
        plugin_type="policy",
        display_name="Sandbox Raise Policy",
        category="policy",
        description="Raises during policy extension for fail-closed tests.",
        version="0.1.0",
    )
    name = "sandbox_raise_policy"

    def extend_policy(self, policy):
        raise RuntimeError("policy boom")


class RelaxPolicyPlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_relax_policy",
        plugin_type="policy",
        display_name="Sandbox Relax Policy",
        category="policy",
        description="Attempts unaudited policy relaxation for fail-closed tests.",
        version="0.1.0",
    )
    name = "sandbox_relax_policy"

    def extend_policy(self, policy):
        return {"imports": {"allowed_roots": ["numpy"]}}


class BadShapePlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_bad_shape",
        plugin_type="policy",
        display_name="Sandbox Bad Shape",
        category="policy",
        description="Returns a bad policy shape for fail-closed tests.",
        version="0.1.0",
    )
    name = "sandbox_bad_shape"

    def extend_policy(self, policy):
        return ["not", "an", "object"]
