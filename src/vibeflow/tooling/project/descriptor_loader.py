"""Workflow-selected plugin loading. No project resource discovery."""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Mapping

from vibeflow.core.descriptors.models import SourceLocator, _thaw_json
from vibeflow.core.descriptors.contributions import compose_contributions, resource_kind
from vibeflow.core.descriptors.catalogs import DescriptorCatalogError
from vibeflow.core.descriptors.plugin_selection import _validate_plugin_config
from vibeflow.tooling.project.config_loader import load_raw_config_document

@dataclass
class DescriptorLoadError(ValueError):
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
class LoadedPlugins:
    catalogs: Any
    bindings: Mapping
    records: tuple[Mapping, ...]
    lifecycle_selections: tuple[Mapping, ...]


def load_workflow_plugins(workspace, config_path, *, node_command="node") -> LoadedPlugins:
    definitions = {}
    try:
        return _load_workflow_plugins(workspace, config_path, node_command=node_command, definitions=definitions)
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


def _load_workflow_plugins(workspace, config_path, *, node_command, definitions) -> LoadedPlugins:
    config_path = Path(config_path).resolve()
    root = workspace.root_for_path(config_path)
    if root is None:
        raise DescriptorLoadError("PLUGIN.CONFIG.ROOT", "workflow must belong to a registered root", str(config_path))
    raw = load_raw_config_document(config_path).data
    selections = raw.get("plugins", [])
    if not isinstance(selections, list):
        raise DescriptorLoadError("PLUGIN.SELECTION.SHAPE", "plugins must be a list", str(config_path), "plugins")
    from vibeflow.tooling.project.config_schema import collect_plugin_selection_findings
    selection_errors = collect_plugin_selection_findings(selections)
    if selection_errors:
        issue = selection_errors[0]
        raise DescriptorLoadError(issue.rule_id, issue.message, str(config_path), str(issue.source_location.get("field", issue.object_id)), {"selection_errors": [item.to_dict() for item in selection_errors]})
    from vibeflow.tooling.application.plugin_definitions import load_builtin_definition
    builtin = load_builtin_definition(root.project_target)
    definitions.setdefault(root.project_target, []).append(builtin)
    contributions = [builtin.contributions()]
    bindings = {(builtin.id, *key): value for key, value in builtin.bindings().items()}
    records, lifecycle, load_states = [], [], {}
    for index, spec in enumerate(selections):
        field = f"plugins[{index}]"
        if not isinstance(spec, Mapping):
            raise DescriptorLoadError("PLUGIN.SELECTION.MIGRATION", "select plugins by explicit source; ID-only registration was removed", str(config_path), field)
        if not isinstance(spec.get("enabled", True), bool):
            raise DescriptorLoadError("PLUGIN.SELECTION.SHAPE", "enabled must be boolean", str(config_path), field)
        if not spec.get("enabled", True):
            continue
        unknown = set(spec) - {"id", "source", "root", "config", "enabled", "status", "display_name", "description", "type", "targets", "priority", "version", "style"}
        if unknown:
            raise DescriptorLoadError("PLUGIN.SELECTION.MIGRATION", f"unsupported plugin fields: {sorted(unknown)}; use an SDK plugin source", str(config_path), field)
        status = spec.get("status", "implemented")
        if status not in {"implemented", "planned"}:
            raise DescriptorLoadError("PLUGIN.SELECTION.STATUS", "status must be implemented or planned", str(config_path), field)
        if status == "planned":
            records.append({**dict(spec), "loaded": False, "status": status})
            continue
        try:
            owner = workspace.root_by_id(spec["root"]) if spec.get("root") else root
        except (KeyError, ValueError) as exc:
            raise DescriptorLoadError("PLUGIN.SELECTION.ROOT", f"unknown workspace root: {spec.get('root')}", str(config_path), field + ".root") from exc
        source_data = spec.get("source")
        if not isinstance(source_data, Mapping) or set(source_data) - {"kind", "ref", "export"}:
            raise DescriptorLoadError("PLUGIN.SELECTION.SOURCE", "implemented plugins require a source with kind, ref and optional export", str(config_path), field + ".source")
        try:
            source = SourceLocator(**source_data)
            if source.kind == "file" and not (owner.path / source.ref).resolve().is_relative_to(owner.path):
                raise ValueError("plugin file must belong to its selected workspace root")
            from vibeflow.tooling.application.plugin_definitions import load_plugin_definition
            plugin = load_plugin_definition(source, owner=owner, workspace=workspace, node_command=node_command)
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
            config = {**_thaw_json(defaults), **dict(overrides)}
            _validate_plugin_config(config, schema, plugin_id=plugin_id)
            contribution = _resolved_contributions(make_contributions(config), owner.path)
            from vibeflow.tooling.application.plugin_definitions import normalize_contributions
            contribution = normalize_contributions(contribution, plugin_bindings, owner=owner, workspace=workspace)
            if contribution.declaration:
                from dataclasses import replace
                export = source.export or "plugin"
                if any(item["source"].get("export") != export for item in contribution.declaration["implementations"]):
                    declaration = _thaw_json(contribution.declaration)
                    for implementation in declaration["implementations"]:
                        # The selected export is the actual declaration entry.
                        implementation["source"]["export"] = export
                    contribution = replace(contribution, declaration=declaration)
            _validate_support_sources(contribution, workspace)
            contributions.append(contribution)
            bindings.update({(plugin_id, *key): value for key, value in plugin_bindings.items()})
            records.append({"id": plugin_id, "source": source.to_dict(), "root": owner.id,
                            "config": config, "loaded": True, "status": status,
                            "declaration": dict(contribution.declaration), "style": dict(spec.get("style", {}))})
            for resource in contribution.resources:
                if resource_kind(resource.descriptor) == "plugin":
                    lifecycle.append({"id": resource.descriptor.id, "config": config})
        except DescriptorLoadError:
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
            raise DescriptorLoadError(code, str(exc),
                                      str((owner.path / source_data.get("ref", "")).resolve()) if source_data.get("kind") == "file" else str(config_path), field, details) from exc
    try:
        catalogs = compose_contributions(tuple(contributions))
    except DescriptorCatalogError as exc:
        raise DescriptorLoadError(exc.code, exc.message, exc.source, details={"resource_id": exc.descriptor_id,
                                  "previous_source": exc.previous_source, **exc.details}) from exc
    lifecycle.extend({key:value for key,value in record.items() if key not in {"source","root","enabled","loaded"}} for record in records if record.get("status") == "planned")
    from dataclasses import replace
    from vibeflow.core.descriptors.models import _freeze_json
    source_roots = tuple(str(item.path) for item in workspace.roots)
    for name in ("nodes", "base_libs", "host_extensions", "plugins", "rules"):
        getattr(catalogs, name).source_roots = source_roots
    catalogs = replace(catalogs, plugin_records=_freeze_json(records, field_name="plugins"),
                       lifecycle_selections=_freeze_json(lifecycle, field_name="plugins.lifecycle"),
                       source_load_states=_freeze_json(load_states, field_name="plugins.sources"),
                       source_roots=source_roots)
    from vibeflow.tooling.application.plugin_definitions import attach_plugin_definitions
    attach_plugin_definitions(catalogs, definitions)
    from types import MappingProxyType
    return LoadedPlugins(catalogs, MappingProxyType(bindings), catalogs.plugin_records, catalogs.lifecycle_selections)


def _resolved_contributions(contribution, root):
    """Resolve relative locators in the selected plugin's root, once."""
    from dataclasses import replace
    resources = []
    changed = False
    for resource in contribution.resources:
        descriptor = resource.descriptor
        implementations = getattr(descriptor, "implementations", None)
        if implementations is not None:
            values = []
            for implementation in implementations:
                source = implementation.source
                if source.kind == "file":
                    reference = str((root / source.ref).resolve())
                    if source.ref != reference:
                        source = replace(source, ref=reference)
                files = []
                for part in getattr(implementation, "implementation_files", ()):
                    reference = str((root / part.ref).resolve())
                    files.append(replace(part, ref=reference) if part.ref != reference else part)
                if source != implementation.source or tuple(files) != getattr(implementation,"implementation_files", ()):
                    implementation = replace(implementation, source=source, **({"implementation_files":tuple(files)} if hasattr(implementation,"implementation_files") else {}))
                values.append(implementation)
            if tuple(values) != implementations:
                descriptor = replace(descriptor, implementations=tuple(values))
                resource = replace(resource, descriptor=descriptor)
                changed = True
        resources.append(resource)
    return replace(contribution, resources=tuple(resources)) if changed else contribution



def _validate_support_sources(contribution, workspace):
    from vibeflow.core.descriptors.source_bundle import declaration_descriptor
    descriptors = [(entry.descriptor,entry.origin) for entry in contribution.resources]
    if contribution.declaration:
        descriptors.append((declaration_descriptor(contribution.declaration),None))
    for descriptor,origin in descriptors:
        for implementation in getattr(descriptor,"implementations", ()):
            for index,source in enumerate(getattr(implementation,"implementation_files", ())):
                path = Path(source.ref)
                field = f"{resource_kind(descriptor)}.{descriptor.id}.implementation_files[{index}]"
                if not any(path.is_relative_to(root.path) for root in workspace.roots):
                    raise DescriptorLoadError("RESOURCE.SOURCE.ROOT","support source must belong to a registered workspace root",str(path),field)
                if not path.is_file():
                    raise DescriptorLoadError("RESOURCE.SOURCE.UNAVAILABLE","registered support source is not a file",str(path),field,
                        {"declaration":origin.to_dict() if origin else {"path":contribution.source}})

def load_workflow_catalogs(project_root, *, workflow_config, workspace=None, project_config=None, node_command="node"):
    if workspace is None:
        from vibeflow.tooling.project.workspace_loader import load_workspace_config
        root = Path(project_root).resolve()
        workspace_file = next((directory / "vibeflow_config.jsonc" for directory in (root, *root.parents)
                               if (directory / "vibeflow_config.jsonc").is_file()), None)
        if workspace_file is None:
            from vibeflow.tooling.project.workspace_model import WorkspaceConfig, WorkspaceRoot
            from vibeflow.tooling.project.workspace_loader import load_project_target
            path = Path(project_config or root / "vibeflow_project.jsonc")
            data = load_raw_config_document(path).data
            workspace = WorkspaceConfig(path, root, {}, (WorkspaceRoot("project", root, path, data, load_project_target(path)),))
        else:
            workspace = load_workspace_config(workspace_file)
    return load_workflow_plugins(workspace, workflow_config, node_command=node_command).catalogs


def load_builtin_plugins(target="python") -> LoadedPlugins:
    """Use the same composition boundary for programmatic and standalone commands."""
    from types import MappingProxyType
    from vibeflow.tooling.application.plugin_definitions import load_builtin_definition
    from vibeflow.tooling.application.plugin_definitions import attach_plugin_definitions
    definition = load_builtin_definition(target)
    catalogs = compose_contributions((definition.contributions(),))
    attach_plugin_definitions(catalogs, {"python" if target == "project" else target: (definition,)})
    bindings = MappingProxyType({(definition.id, *key): value for key, value in definition.bindings().items()})
    return LoadedPlugins(catalogs, bindings, (), ())
