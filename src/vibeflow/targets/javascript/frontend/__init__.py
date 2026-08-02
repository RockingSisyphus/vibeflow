"""JavaScript/TypeScript project frontend and binding preparation."""

from vibeflow.targets.javascript.frontend.build_contracts import (
    node_contract_check,
    validate_schema_subset,
)
from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptBindingPlan,
    JavascriptPluginBinding,
    build_javascript_binding_plan,
)
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    PLUGIN_ABI_VERSION,
    JavascriptPluginBindingPlan,
    JavascriptPluginError,
    build_javascript_plugin_binding_plan,
    parse_javascript_plugin_descriptor,
    parse_javascript_plugin_selection,
    resolve_javascript_plugins,
)

__all__ = [
    "PLUGIN_ABI_VERSION",
    "JavascriptBindingPlan",
    "JavascriptPluginBinding",
    "JavascriptPluginBindingPlan",
    "JavascriptPluginError",
    "build_javascript_plugin_binding_plan",
    "build_javascript_binding_plan",
    "node_contract_check",
    "parse_javascript_plugin_descriptor",
    "parse_javascript_plugin_selection",
    "resolve_javascript_plugins",
    "validate_schema_subset",
]
