from __future__ import annotations
from vibeflow.targets.python.project import BaseLibRegistry, PluginResourceRegistry

def build_base_lib_registry() -> BaseLibRegistry:
    registry = BaseLibRegistry()
    registry.register('good_math', module='base_lib.good_math', display_name='Good Math', category='sandbox', description='Validated arithmetic helper functions for sandbox resource checks.', version='0.1.0')
    registry.register('good_chain_a', module='base_lib.good_chain_a', display_name='Good Chain A', category='sandbox', description='A valid dependency-chain helper module for sandbox resource checks.', version='0.1.0')
    registry.register('sandbox_arithmetic', module='base_lib.sandbox_arithmetic', display_name='Sandbox Arithmetic', category='sandbox', description='Arithmetic helper functions used by the resource nodeset fixture.', version='0.1.0')
    return registry

def build_plugin_registry() -> PluginResourceRegistry:
    registry = PluginResourceRegistry()
    registry.register('value_shift', module='plugins.value_plugin', class_name='ValueShiftPlugin', plugin_type='runtime', display_name='Sandbox Value Shift', category='sandbox', description='Runtime plugin that shifts sandbox values during resource fixture execution.', version='0.1.0')
    registry.register('compiler_hook', module='plugins.hook_plugins', class_name='CompilerPlugin', plugin_type='compiler', display_name='Compiler Hook Plugin', category='sandbox', description='Records compiler hook calls for the plugin fixture.', version='0.1.0')
    registry.register('runtime_hook', module='plugins.hook_plugins', class_name='RuntimePlugin', plugin_type='runtime', display_name='Runtime Hook Plugin', category='sandbox', description='Records runtime hook calls for the plugin fixture.', version='0.1.0')
    return registry
