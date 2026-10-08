"""Canonical JavaScript/TypeScript Target models and static contracts."""

from vibeflow.targets.javascript.frontend.bindings import (
    JavascriptBindingPlan,
    JavascriptCallBinding,
    JavascriptPluginBinding,
    JavascriptSchemaMemberOrder,
    build_javascript_binding_plan,
)
from vibeflow.targets.javascript.frontend.plugin_descriptors import (
    PLUGIN_ABI_VERSION,
    JavascriptPluginBindingPlan,
    JavascriptPluginError,
    build_javascript_plugin_binding_plan,
    parse_javascript_plugin_selection,
    resolve_javascript_plugins,
)
from vibeflow.targets.javascript.frontend.declarations import declarations, schema_to_typescript
from vibeflow.targets.javascript.frontend.errors import AotBuildError, ProjectBuildError
from vibeflow.block_compiler.model import WORKFLOW_ABI_VERSION as ABI_VERSION
from vibeflow.targets.javascript.frontend.errors import AotPlanError
from vibeflow.targets.javascript.frontend.contracts import (
    CapabilityRequirement, COMPLETIONS, EXECUTORS, SCHEDULES,
)

from vibeflow.targets.javascript.frontend.schema import (
    JAVASCRIPT_SAFE_INTEGER_MAX,
    JavascriptJsonValueError,
    PortableSchemaError,
    validate_javascript_json_value,
    validate_portable_json_schema,
)

__all__ = [
    "PLUGIN_ABI_VERSION",
    "ABI_VERSION",
    "AotBuildError",
    "AotPlanError",
    "CapabilityRequirement",
    "COMPLETIONS",
    "EXECUTORS",
    "JAVASCRIPT_SAFE_INTEGER_MAX",
    "JavascriptBindingPlan",
    "JavascriptCallBinding",
    "JavascriptPluginBinding",
    "JavascriptPluginBindingPlan",
    "JavascriptPluginError",
    "JavascriptSchemaMemberOrder",
    "JavascriptJsonValueError",
    "PortableSchemaError",
    "ProjectBuildError",
    "SCHEDULES",
    "build_javascript_binding_plan",
    "build_javascript_plugin_binding_plan",
    "declarations",
    "parse_javascript_plugin_selection",
    "schema_to_typescript",
    "resolve_javascript_plugins",
    "validate_javascript_json_value",
    "validate_portable_json_schema",
]
