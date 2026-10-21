"""Bind selected compiler/runtime plugins at their native lifecycle boundaries."""

from vibeflow.core.descriptors.json_values import freeze_mapping
from vibeflow.targets.python.sdk.loading import source_paths

from vibeflow.targets.python.project.plugins import PluginRegistry, create_lifecycle_plugin, dispose_instances


def lifecycle_registry(registry, *, workflow_id, config_path, plugin_types=("compiler", "runtime")):
    """Create instances at the native compile/run boundary, not declaration time."""
    result = PluginRegistry()
    loaded = registry.prepared_resources
    created = []
    try:
        for selection in loaded.lifecycle_selections:
            if selection.get("status") == "planned":
                continue
            descriptor = loaded.catalogs.plugins.require(selection["id"])
            if descriptor.plugin_type not in plugin_types:
                continue
            factory = registry.direct_bindings.get(("plugin", descriptor.id))
            if factory is None:
                from vibeflow.tooling.application.python.project.declarations import _load_rule_handler, _implementation_path
                root = registry.resource_roots[("plugins", descriptor.id)]
                source = descriptor.implementations[0].source
                factory = _load_rule_handler(_implementation_path(source.kind, source.ref, root.path, registry.source_roots), source.export, root, registry)
            config = freeze_mapping(selection["config"], field_name="plugin.config")
            context = freeze_mapping({"config": config, "workflow_id": workflow_id, "config_path": str(config_path)}, field_name="plugin.context")
            with source_paths(registry.source_roots):
                instance = create_lifecycle_plugin(result, descriptor, factory, context,
                    source=descriptor.implementations[0].source.ref,
                    class_name=descriptor.implementations[0].source.export or "", config_keys=tuple(config),
                    source_path=loaded.catalogs.plugins.source_for(descriptor.id), rulesets=descriptor.rulesets, conflict="error")
            created.append(instance)
    except BaseException as error:
        with source_paths(registry.source_roots):
            dispose_instances(created, primary=error)
        raise
    return result


def checked_runtime_plugins(factory, *, config_path, effective_policy, run_dir):
    """Report a native factory failure using the checked-run error contract."""
    from pathlib import Path
    from vibeflow.tooling.application.python.reports import _workspace_error_report
    from vibeflow.tooling.application.python.execution import (CheckedRunError, CheckedRunResult, _write_refused_artifacts)
    try:
        return factory()
    except Exception as error:
        health = _workspace_error_report("PLUGIN.FACTORY.LOAD", str(error), Path(config_path), effective_policy)
        _write_refused_artifacts(run_dir, health)
        raise CheckedRunError("run refused: runtime plugin creation failed",
            CheckedRunResult(run_dir.name, run_dir, health)) from error
