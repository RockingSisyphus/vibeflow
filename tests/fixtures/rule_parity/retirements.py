"""Explicit retirement of checks for the deleted native IO parser.

Keep reference.json intact. Ordinary SDK port behavior is exercised by native
runtime integration and portable conformance; two old IDs remain as migration
diagnostics. No other historical case may disappear.
"""
RETIRED = {"python":frozenset({"python.source.formal_effects"}),"tooling": frozenset({
    "tooling.system_io.provides", "tooling.system_io.receive_empty", "tooling.system_io.requires",
    "tooling.system_io.send_normal", "tooling.system_io.send_optional",
    "tooling.variant.io.async", "tooling.variant.io.object", "tooling.variant.io.operation",
    "tooling.variant.io.port", "tooling.variant.io.receive_two", "tooling.variant.io.unknown",
})}

# Host Extension factory and host lifecycle contract no longer exist.
RETIRED["javascript"]=frozenset(['js.host.async-factory',
 'js.host.global.normal',
 'js.host.module-write',
 'js.host.node-import',
 'js.host.normal.audit',
 'js.host.normal.build',
 'js.host.timer.normal',
 'js.host.top-call',
 'js.host.top-call.quality-cli',
 'js.host.undeclared-dependency',
 'js.variant.completion.host-async-start',
 'js.variant.imports.host-declared.normal',
 'js.variant.native.absolute-url.normal',
 'js.variant.native.fetch-absolute.normal',
 'js.variant.native.fetch-local',
 'js.variant.native.import-scripts',
 'js.variant.native.module-url',
 'js.variant.native.service-worker',
 'js.variant.native.shared-worker',
 'js.variant.native.wasm',
 'js.variant.native.worker',
 'js.variant.native.worklet',
 'js.variant.state.global-this-write'])

# Deleted Host model and global-policy schema details; representative rejection cases remain.
RETIRED["tooling"] |= frozenset(['tooling.descriptor.host.dependencies.duplicate',
 'tooling.descriptor.host.dependencies.list',
 'tooling.descriptor.host.dependencies_self',
 'tooling.descriptor.host.external_packages.duplicate',
 'tooling.descriptor.host.external_packages.list',
 'tooling.descriptor.host.implementations_empty',
 'tooling.descriptor.host.normal',
 'tooling.descriptor.host.python',
 'tooling.descriptor.host.targets_empty',
 'tooling.descriptor.host.targets_unknown',
 'tooling.descriptor.host.unknown_field',
 'tooling.descriptor.node.missing_type_key',
 'tooling.host_duplicate',
 'tooling.host_enabled',
 'tooling.host_id',
 'tooling.variant.host.config',
 'tooling.variant.host.dependencies',
 'tooling.variant.host.disabled_duplicate',
 'tooling.variant.host.disabled_then_active',
 'tooling.variant.host.provides',
 'tooling.variant.host.settings',
 'tooling.variant.host.targets',
 'tooling.variant.policy.base_lib.allowed_modules',
 'tooling.variant.policy.base_lib.allowed_paths',
 'tooling.variant.policy.base_lib.banned_modules',
 'tooling.variant.policy.base_lib.normal',
 'tooling.variant.policy.base_lib.object',
 'tooling.variant.policy.complexity.disabled',
 'tooling.variant.policy.complexity.max_branches',
 'tooling.variant.policy.complexity.max_contract_keys',
 'tooling.variant.policy.complexity.max_functions',
 'tooling.variant.policy.complexity.max_nesting_depth',
 'tooling.variant.policy.complexity.max_params',
 'tooling.variant.policy.complexity.object',
 'tooling.variant.policy.complexity.one',
 'tooling.variant.policy.imports.allowed_modules',
 'tooling.variant.policy.imports.allowed_roots',
 'tooling.variant.policy.imports.banned_modules',
 'tooling.variant.policy.imports.banned_roots',
 'tooling.variant.policy.imports.normal',
 'tooling.variant.policy.imports.object',
 'tooling.variant.policy.maintainability.max_call_chain_length',
 'tooling.variant.policy.maintainability.max_dependency_chain_length',
 'tooling.variant.policy.maintainability.object',
 'tooling.variant.policy.maintainability.one',
 'tooling.variant.policy.maintainability.warn_call_chain_length',
 'tooling.variant.policy.maintainability.warn_dependency_chain_length',
 'tooling.variant.policy.node_source.max_bytes',
 'tooling.variant.policy.node_source.max_lines',
 'tooling.variant.policy.node_source.object',
 'tooling.variant.policy.node_source.one',
 'tooling.variant.policy.node_source.warn_bytes',
 'tooling.variant.policy.node_source.warn_lines',
 'tooling.variant.policy.removed.exemption',
 'tooling.variant.policy.removed.item',
 'tooling.variant.policy.removed.list',
 'tooling.variant.policy.removed.missing_expires',
 'tooling.variant.policy.removed.missing_reason',
 'tooling.variant.policy.removed.missing_rule_id',
 'tooling.variant.policy.removed.normal',
 'tooling.variant.policy.removed.object',
 'tooling.variant.policy.removed.scope',
 'tooling.variant.policy.removed.to',
 'tooling.variant.policy.source.null',
 'tooling.variant.policy.source.zero',
 'tooling.variant.resource.host.metadata_category',
 'tooling.variant.resource.host.metadata_description',
 'tooling.variant.resource.host.metadata_display_name',
 'tooling.variant.resource.host.metadata_version',
 'tooling.variant.resource.host.planned',
 'tooling.variant.resource.host.status'])
RETIRED["javascript"] |= frozenset({"js.plugin.undeclared-dependency"})

# The source algorithm selection was renamed before project/root governance.
# Current source selection and four-level governance have separate live cases.
RETIRED["core"] = frozenset("core.selection.vibeflow.quality.project." + phase
                            for phase in ("import", "static", "run"))

# Node-local import permission was deleted; resource Rule coverage lives in
# tests/core/test_resource_structure_imports.py and tests/tooling/test_resource_use.py.
RETIRED["python"] |= frozenset({"python.coupling.import_registered_node"})
