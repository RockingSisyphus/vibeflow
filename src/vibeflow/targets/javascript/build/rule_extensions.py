"""Declared Ruleset review for a standalone extension before native binding."""
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.descriptors import DescriptorCatalogs, ImplementationDescriptor, PluginDescriptor, SourceLocator
from vibeflow.core.flow import GraphConfig
from vibeflow.core.rules.builtin import builtin_rule_resources
from vibeflow.targets.javascript.frontend.plugin_descriptors import JavascriptPluginError


def check_plugin_rules(plugin: Mapping[str, Any], *, package_root: Path, target: str,
                       catalogs: DescriptorCatalogs | None = None, node_command: str = "node") -> None:
    """Use exactly the same engine as project review, with an explicit selection."""
    from vibeflow.targets.javascript.build.rule_session import run_javascript_rules
    from vibeflow.targets.javascript.build.project_resources import target_neutral_import_policy
    selected = tuple(plugin.get("rulesets", ()))
    if not selected:
        return
    package_root = package_root.resolve()
    module = Path(plugin["module"]).resolve()
    language = "typescript" if module.suffix in {".ts", ".tsx", ".mts"} else "javascript"
    descriptor = PluginDescriptor(id=plugin["id"], plugin_type=plugin.get("type", "runtime"),
        targets=(target,), rulesets=selected, implementations=(ImplementationDescriptor(language, (target,),
            SourceLocator("file", module.relative_to(package_root).as_posix(), plugin.get("export", "createPlugin")),
            completion=plugin.get("completion", "immediate")),))
    catalogs = catalogs or DescriptorCatalogs.empty()
    from vibeflow.core.descriptors import PluginCatalog, RuleCatalog, RulesetCatalog
    rules, rulesets = builtin_rule_resources()
    def merged(catalog, defaults, catalog_type):
        result = catalog_type()
        for item in defaults:
            result.register(item, source="builtin:" + item.id)
        for item in catalog:
            previous = result.get(item.id)
            if previous is not None and previous != item:
                details = {"resource_id":item.id, "source":catalog.source_for(item.id),
                           "previous_source":result.source_for(item.id)}
                raise JavascriptPluginError("RULE.RESOURCE.CONFLICT", f"conflicting rule resource '{item.id}'",
                    descriptor.id, details=details)
            if previous is None:
                result.register(item, source=catalog.source_for(item.id))
        return result
    plugins = PluginCatalog()
    for item in catalogs.plugins:
        if item.id != descriptor.id:
            plugins.register(item, source=catalogs.plugins.source_for(item.id))
    plugins.register(descriptor, source=catalogs.plugins.source_for(descriptor.id) or str(module))
    catalogs = replace(catalogs, plugins=plugins, rules=merged(catalogs.rules, rules, RuleCatalog),
                       rulesets=merged(catalogs.rulesets, rulesets, RulesetCatalog))
    policy, _ = target_neutral_import_policy(catalogs=catalogs, project_root=package_root,
        allowed_external=set(plugin.get("external_packages", ())), node_ids=frozenset(), plugin_ids=frozenset({descriptor.id}))
    report = run_javascript_rules(GraphConfig(nodes=(), rulesets=()), catalogs, project_root=package_root,
        package_root=package_root, target=target, import_policy=policy, node_command=node_command)
    errors = [item.to_dict() for item in report.findings if item.severity == "error"]
    if errors:
        raise JavascriptPluginError(errors[0]["code"], errors[0]["message"], descriptor.id, details={"diagnostics": errors})
