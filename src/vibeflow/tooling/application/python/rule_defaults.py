"""Read Python Rule defaults without importing business implementations."""

from vibeflow.core.rules.builtin import project_quality_rule_defaults
from vibeflow.targets.python.quality.project_context import source_quality_policy
from vibeflow.tooling.application.python.project.effective_policy import resolve_effective_policy
from vibeflow.tooling.application.python.project.policy import resolve_workspace_effective_policy


def source_rule_defaults(document, *, workspace=None):
    resolved = (resolve_workspace_effective_policy(workspace.policy, workspace_path=workspace.path)
                if workspace else resolve_effective_policy(document.data, config_path=document.path))
    errors = [finding.message for finding in resolved.findings if finding.severity == "error"]
    if errors:
        raise ValueError("; ".join(errors))
    policy = source_quality_policy(resolved.effective_policy.to_purity_policy())
    return project_quality_rule_defaults(policy)


def declared_rule_resources(workspace, config_path, *, loaded_plugins=None):
    """Target-owned declaration assembly, shared by preview and formal checks."""
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry
    from vibeflow.targets.python.quality.rule_adapter import rule_resources
    registry = declared_python_registry(workspace, config_path, loaded_plugins=loaded_plugins)
    rules, rulesets = rule_resources(registry)
    return registry, rules, rulesets


def reached_library_ids(registry, type_keys):
    from vibeflow.tooling.application.python.project.declarations import collect_node_source_context
    from vibeflow.targets.python.project.resource_rules import reached_base_lib_sources
    sources = collect_node_source_context(registry, tuple(key for key in type_keys if key in registry.available()))
    return {descriptor.id for descriptor, _, _ in reached_base_lib_sources(registry, sources)}
