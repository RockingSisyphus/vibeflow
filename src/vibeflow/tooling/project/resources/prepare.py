"""Prepare selected Plugin contributions and independent project/root resources."""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.descriptors.json_values import freeze_json, thaw_json
from vibeflow.core.descriptors.models import SourceLocator
from vibeflow.core.descriptors.contributions import compose_contributions, resource_kind
from vibeflow.core.descriptors.catalogs import DescriptorCatalogError
from vibeflow.core.descriptors.plugin_selection import _validate_plugin_config
from vibeflow.tooling.project.config_loader import load_raw_config_document

@dataclass
class ResourcePreparationError(ValueError):
    code: str
    message: str
    path: str = ""
    field: str = ""
    details: Mapping[str, Any] = dataclass_field(default_factory=dict)

    @property
    def diagnostics(self) -> tuple[Mapping[str, Any], ...]:
        return ({"code": self.code, "severity": "error", "message": self.message,
                 "source_location": {"path": self.path, **self.details.get("location", {})},
                 "details": {"field": self.field, "source": self.path, **self.details}},)

    def __str__(self) -> str:
        location = self.path
        if self.field:
            location = f"{location}:{self.field}" if location else self.field
        previous = self.details.get("previous_source", "")
        return f"{self.code}: {self.message}" + (
            f" ({location})" if location else ""
        ) + (f"; previous declaration: {previous}" if previous else "")

    def __reduce__(self):
        return (
            type(self),
            (self.code, self.message, self.path, self.field, self.details),
        )


@dataclass(frozen=True)
class PreparedResources:
    catalogs: Any
    bindings: Mapping
    records: tuple[Mapping, ...]
    lifecycle_selections: tuple[Mapping, ...]
    resource_bindings: Mapping = dataclass_field(default_factory=dict)
    resource_inventory: tuple = ()
    binding_contexts: Mapping = dataclass_field(default_factory=dict, repr=False, compare=False)
    document: object | None = None
    graph: object | None = None
    syntax_caches: Mapping = dataclass_field(default_factory=dict, repr=False, compare=False)


def prepare_workflow_resources(workspace, config_path, *, node_command="node", discovery_cache=None, syntax_caches=None, binding_contexts=None) -> PreparedResources:
    return _resource_scope(workspace, config_path, node_command=node_command, discovery_cache=discovery_cache, syntax_caches=syntax_caches, binding_contexts=binding_contexts)


def prepare_governance_resources(workspace, config, *, root=None, node_command="node", syntax_caches=None, binding_contexts=None):
    from vibeflow.tooling.project.resources.ownership import ResourceScope
    scope = root or ResourceScope("project", workspace.root, "project", {})
    return _resource_scope(workspace, config.path, node_command=node_command,
                           root=scope, selections=config.plugins, include_business=False, syntax_caches=syntax_caches, binding_contexts=binding_contexts)


def _resource_scope(workspace, config_path, *, node_command, **scope_options):
    definitions = {}
    try:
        return _prepare_workflow_resources(workspace, config_path, node_command=node_command, definitions=definitions, **scope_options)
    except Exception as error:
        cleanup_errors = []
        for target, values in definitions.items():
            for definition in values:
                close = getattr(definition, "close", None)
                if close is not None:
                    try:
                        close()
                    except Exception as cleanup_error:
                        cleanup_errors.append({"target": target, "error": str(cleanup_error)})
        if cleanup_errors:
            previous = getattr(error, "details", {})
            try:
                error.details = {**(previous if isinstance(previous, Mapping) else {}),
                                 "cleanup_errors": cleanup_errors}
            except Exception:
                error.add_note(f"plugin cleanup errors: {cleanup_errors}")
        raise


def _prepare_workflow_resources(workspace, config_path, *, node_command, definitions,
                           root=None, selections=None, include_business=True, discovery_cache=None, syntax_caches=None, binding_contexts=None) -> PreparedResources:
    syntax_caches = {} if syntax_caches is None else syntax_caches
    binding_contexts = {} if binding_contexts is None else binding_contexts
    config_path = Path(config_path).resolve()
    root = root or workspace.root_for_path(config_path)
    if root is None:
        raise ResourcePreparationError("PLUGIN.CONFIG.ROOT", "workflow must belong to a registered root", str(config_path))
    from vibeflow.tooling.project.config_loader import load_workspace_config_document
    from vibeflow.tooling.project.config_schema import collect_config_schema_findings, ConfigSchemaError
    from vibeflow.tooling.project.graph_config import parse_graph_config
    document = load_workspace_config_document(config_path, workspace=workspace) if include_business else None
    graph = None
    if document is not None:
        errors = tuple(item for item in collect_config_schema_findings(document.data) if item.severity == "error")
        if errors:
            raise ConfigSchemaError(errors)
        graph = parse_graph_config(document.data, project_root=root.path, root_id=root.id,
                                   root_path=root.path, source_path=config_path)
    raw = document.data if selections is None else {"plugins": list(selections)}
    selections = raw.get("plugins", [])
    if not isinstance(selections, list):
        raise ResourcePreparationError("PLUGIN.SELECTION.SHAPE", "plugins must be a list", str(config_path), "plugins")
    from vibeflow.tooling.project.config_schema import collect_plugin_selection_findings
    selection_errors = collect_plugin_selection_findings(selections)
    if selection_errors:
        issue = selection_errors[0]
        raise ResourcePreparationError(issue.rule_id, issue.message, str(config_path), str(issue.source_location.get("field", issue.object_id)), {"selection_errors": [item.to_dict() for item in selection_errors]})
    from vibeflow.tooling.application.plugin_definitions import load_builtin_definition
    builtin = load_builtin_definition(root.project_target)
    definitions.setdefault(root.project_target, []).append(builtin)
    contributions = [builtin.contributions()]
    bindings = {(builtin.id, *key): value for key, value in builtin.bindings().items()}
    records, lifecycle, load_states = [], [], {}
    for index, spec in enumerate(selections):
        field = f"plugins[{index}]"
        if not isinstance(spec, Mapping):
            raise ResourcePreparationError("PLUGIN.SELECTION.MIGRATION", "select plugins by explicit source; ID-only registration was removed", str(config_path), field)
        spec = {"scope": "project" if root.project_target == "project" else "root", **spec}
        if not isinstance(spec.get("enabled", True), bool):
            raise ResourcePreparationError("PLUGIN.SELECTION.SHAPE", "enabled must be boolean", str(config_path), field)
        if not spec.get("enabled", True):
            continue
        unknown = set(spec) - {"id", "source", "scope", "language", "config", "enabled", "status", "display_name", "description", "type", "targets", "priority", "version", "style"}
        if unknown:
            raise ResourcePreparationError("PLUGIN.SELECTION.MIGRATION", f"unsupported plugin fields: {sorted(unknown)}; use an SDK plugin source", str(config_path), field)
        status = spec.get("status", "implemented")
        if status not in {"implemented", "planned"}:
            raise ResourcePreparationError("PLUGIN.SELECTION.STATUS", "status must be implemented or planned", str(config_path), field)
        if status == "planned":
            records.append({**dict(spec), "loaded": False, "status": status})
            continue
        try:
            from vibeflow.tooling.project.resources.ownership import selected_plugin_scope
            owner = selected_plugin_scope(workspace, root, spec)
        except (KeyError, ValueError) as exc:
            raise ResourcePreparationError("PLUGIN.SELECTION.SCOPE", str(exc), str(config_path), field + ".scope") from exc
        source_data = spec.get("source")
        if not isinstance(source_data, Mapping) or set(source_data) - {"kind", "ref", "export"}:
            raise ResourcePreparationError("PLUGIN.SELECTION.SOURCE", "implemented plugins require a source with kind, ref and optional export", str(config_path), field + ".source")
        try:
            source = SourceLocator(**source_data)
            if source.kind == "file" and not (owner.path / source.ref).resolve().is_relative_to(owner.path):
                raise ValueError("plugin file must belong to its selected workspace root")
            from vibeflow.tooling.application.plugin_definitions import load_plugin_definition
            plugin = load_plugin_definition(source, owner=owner, workspace=workspace, node_command=node_command, loading_context=binding_contexts.setdefault(owner.project_target, {}))
            definitions.setdefault(owner.project_target, []).append(plugin)
            plugin_id, schema, defaults = plugin.id, plugin.config_schema, plugin.config_defaults
            plugin_bindings = plugin.bindings() if hasattr(plugin, "bindings") else {}
            load_states.update(getattr(plugin, "load_states", {}))
            make_contributions = plugin.contributions
            if spec.get("id") and spec["id"] != plugin_id:
                raise ValueError(f"selected plugin ID '{spec['id']}' does not match exported ID '{plugin_id}'")
            overrides = spec.get("config", {})
            if not isinstance(overrides, Mapping):
                raise ValueError("plugin config must be an object")
            config = {**thaw_json(defaults), **dict(overrides)}
            _validate_plugin_config(config, schema, plugin_id=plugin_id)
            package_path = Path(plugin.source).resolve().parent
            if source.kind == "file":
                relative = Path(plugin.source).resolve().relative_to(owner.path / "plugins")
                if len(relative.parts) < 2:
                    raise ValueError("file Plugins require their own package directory under plugins/")
                package_path = owner.path / "plugins" / relative.parts[0]
            contribution = _resolved_contributions(make_contributions(config), package_path)
            from vibeflow.tooling.application.plugin_definitions import normalize_contributions
            contribution = normalize_contributions(contribution, plugin_bindings, owner=owner, workspace=workspace)
            if contribution.declaration:
                from dataclasses import replace
                export = source.export or "plugin"
                if any(item["source"].get("export") != export for item in contribution.declaration["implementations"]):
                    declaration = thaw_json(contribution.declaration)
                    for implementation in declaration["implementations"]:
                        # The selected export is the actual declaration entry.
                        implementation["source"]["export"] = export
                    contribution = replace(contribution, declaration=declaration)
            from vibeflow.tooling.project.resources.ownership import check_plugin_package, bind_plugin_owner
            from vibeflow.tooling.application.plugin_definitions import plugin_source_paths
            sources = plugin_source_paths(plugin, contribution, owner=owner, workspace=workspace,
                                          package=package_path, node_command=node_command, syntax_cache=syntax_caches.setdefault(owner.project_target, {}))
            check_plugin_package(contribution, package_path=package_path, source_paths=sources,
                                 project_path=workspace.root)
            contribution = bind_plugin_owner(contribution,
                root_id=root.id if spec.get("scope", "root") == "root" else "", package_path=package_path)
            contributions.append(contribution)
            bindings.update({(plugin_id, *key): value for key, value in plugin_bindings.items()})
            records.append({"id": plugin_id, "source": source.to_dict(), "root": owner.id,
                            "scope": spec.get("scope", "root"), "package_path": str(package_path),
                            "config": config, "loaded": True, "status": status,
                            "declaration": dict(contribution.declaration), "style": dict(spec.get("style", {}))})
            for resource in contribution.resources:
                if resource_kind(resource.descriptor) == "plugin":
                    lifecycle.append({"id": resource.descriptor.id, "config": config})
        except ResourcePreparationError:
            raise
        except Exception as exc:
            details = {"plugin_source": dict(source_data), "root": owner.id}
            if getattr(exc, "location", None):
                details["location"] = dict(exc.location)
            source_details = getattr(exc, "details", {})
            if isinstance(source_details, Mapping):
                details.update(source_details)
            if isinstance(exc, DescriptorCatalogError):
                details.update({"source": exc.source, "previous_source": exc.previous_source, **exc.details})
            code = getattr(exc, "code", "DESCRIPTOR.INVALID" if isinstance(exc, ValueError) else "PLUGIN.DECLARATION.LOAD")
            raise ResourcePreparationError(code, str(exc),
                                      str((owner.path / source_data.get("ref", "")).resolve()) if source_data.get("kind") == "file" else str(config_path), field, details) from exc
    try:
        from vibeflow.tooling.project.resources.ownership import standalone_resources, referenced_definition_ids
        from vibeflow.tooling.project.config_loader import load_workspace_config_document
        resources, resource_bindings, resource_inventory, discovered_states = (standalone_resources(workspace, root, contributions,
            node_ids=referenced_definition_ids(graph), node_command=node_command, discovery_cache=discovery_cache,
            syntax_cache=syntax_caches.setdefault(root.project_target, {}), loading_context=binding_contexts.setdefault(root.project_target, {})) if include_business else ((), {}, (), {}))
        load_states.update(discovered_states)
        catalogs = compose_contributions(tuple(contributions), resources=resources)
    except DescriptorCatalogError as exc:
        raise ResourcePreparationError(exc.code, exc.message, exc.source, details={"resource_id": exc.descriptor_id,
                                  "previous_source": exc.previous_source, **exc.details}) from exc
    except SyntaxError as exc:
        raise ResourcePreparationError("QUALITY.SYNTAX.PYTHON",str(exc),str(exc.filename or config_path),
            details={"location":{"line":exc.lineno or 1,"column":exc.offset or 1}}) from exc
    except (ValueError, TypeError) as exc:
        details=dict(getattr(exc,"details",{}) or {})
        location=getattr(exc,"location",{})
        if location:details['location']=dict(location)
        path=details.get('location',{}).get('path',details.get('actual',{}).get('path',str(config_path)))
        raise ResourcePreparationError(getattr(exc,'code','DESCRIPTOR.INVALID'),str(exc),path,details=details) from exc
    except Exception as exc:
        if not hasattr(exc, "code"):
            raise
        details = dict(getattr(exc, "details", {}))
        if getattr(exc, "location", None):
            details["location"] = dict(exc.location)
        path = details.get("location", {}).get("path", details.get("actual", {}).get("path", str(config_path)))
        raise ResourcePreparationError(exc.code, str(exc), path, details=details) from exc
    lifecycle.extend({key:value for key,value in record.items() if key not in {"source","root","enabled","loaded"}} for record in records if record.get("status") == "planned")
    from dataclasses import replace
    source_roots = (str(root.path), str(workspace.root))
    for name in ("nodes", "base_libs",  "plugins", "rules"):
        getattr(catalogs, name).source_roots = source_roots
    catalogs = replace(catalogs, plugin_records=freeze_json(records, field_name="plugins"),
                       lifecycle_selections=freeze_json(lifecycle, field_name="plugins.lifecycle"),
                       source_load_states=freeze_json(load_states, field_name="plugins.sources"),
                       source_roots=source_roots)
    from vibeflow.tooling.application.plugin_definitions import attach_plugin_definitions
    attach_plugin_definitions(catalogs, definitions)
    from types import MappingProxyType
    return PreparedResources(catalogs, MappingProxyType(bindings), catalogs.plugin_records, catalogs.lifecycle_selections,
                         MappingProxyType(resource_bindings), resource_inventory, binding_contexts=binding_contexts,
                         document=document, graph=graph, syntax_caches=syntax_caches)


def _resolved_contributions(contribution, directory):
    from dataclasses import replace
    from vibeflow.tooling.project.resources.ownership import resolve_descriptor_sources
    return replace(contribution, resources=tuple(replace(entry,
        descriptor=resolve_descriptor_sources(entry.descriptor, directory)) for entry in contribution.resources))


def prepare_workflow_catalogs(workflow_config, *, workspace=None, node_command="node"):
    if workspace is None:
        from vibeflow.tooling.project.workspace_loader import load_project_workspace
        workspace = load_project_workspace(workflow_config)
    return prepare_workflow_resources(workspace, workflow_config, node_command=node_command).catalogs


def load_builtin_plugins(target="python") -> PreparedResources:
    """Use the same composition boundary for programmatic and standalone commands."""
    from types import MappingProxyType
    from vibeflow.tooling.application.plugin_definitions import load_builtin_definition
    from vibeflow.tooling.application.plugin_definitions import attach_plugin_definitions
    definition = load_builtin_definition(target)
    catalogs = compose_contributions((definition.contributions(),))
    attach_plugin_definitions(catalogs, {target: (definition,)})
    bindings = MappingProxyType({(definition.id, *key): value for key, value in definition.bindings().items()})
    return PreparedResources(catalogs, bindings, (), ())
