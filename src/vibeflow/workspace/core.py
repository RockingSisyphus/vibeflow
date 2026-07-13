from __future__ import annotations

import importlib
import importlib.util
import sys
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping

from vibeflow.config.loader import ConfigLoadError, load_raw_config_document
from vibeflow.config.resources import BaseLibRegistry, ConfigResources, PluginResourceRegistry, config_base_lib_policy, load_config_resources
from vibeflow.devtools.code_quality_types import QualityStructureLimits
from vibeflow.health.types import HealthFinding
from vibeflow.plugin import PluginRegistry, load_plugins_from_config
from vibeflow.registry import NodeRegistrationInfo, NodeRegistry
from vibeflow.workspace.policy import resolve_workspace_effective_policy
from vibeflow.workspace.types import PROJECT_CONFIG_NAME, WorkspaceConfig, WorkspaceConfigError, WorkspaceEnvironment, WorkspaceResourceRegistries, WorkspaceRoot


def load_workspace_config(path: str | Path) -> WorkspaceConfig:
    workspace_path = Path(path).resolve()
    try:
        document = load_raw_config_document(workspace_path)
    except ConfigLoadError as exc:
        raise WorkspaceConfigError(exc.rule_id, exc.message, exc.source_location, exc.failure_layer) from exc
    data = document.data
    _validate_workspace_keys(data, workspace_path)
    roots = _workspace_roots(data.get("roots"), workspace_path=workspace_path)
    return WorkspaceConfig(path=workspace_path, root=workspace_path.parent.resolve(), policy=data.get("policy", {}), roots=tuple(roots))


def build_workspace_environment(workspace: WorkspaceConfig) -> WorkspaceEnvironment:
    registry = build_workspace_node_registry(workspace)
    resource_registries, available_resources, resource_findings = load_workspace_resources(workspace)
    policy_result = resolve_workspace_effective_policy(
        workspace.policy,
        workspace_path=workspace.path,
    )
    return WorkspaceEnvironment(
        registry=registry,
        plugin_registry=PluginRegistry(),
        resources=available_resources,
        available_resources=available_resources,
        resource_registries=resource_registries,
        effective_policy=policy_result.effective_policy,
        findings=(*resource_findings, *policy_result.findings),
    )


def build_workspace_node_registry(workspace: WorkspaceConfig) -> NodeRegistry:
    registry = NodeRegistry()
    sources: dict[str, dict[str, object]] = {}
    for root in workspace.roots:
        if not root.registry_ref:
            continue
        root_registry = _load_root_registry(root)
        _merge_node_registry(registry, root_registry, root=root, sources=sources)
    return registry


def load_workspace_resources(workspace: WorkspaceConfig) -> tuple[dict[str, WorkspaceResourceRegistries], ConfigResources, tuple[HealthFinding, ...]]:
    findings: list[HealthFinding] = []
    base_lib_paths: list[str] = []
    base_libs: list[object] = []
    plugins: list[object] = []
    registries: dict[str, WorkspaceResourceRegistries] = {}
    for root in workspace.roots:
        base_registry, plugin_registry, has_base_registry, has_plugin_registry, registry_findings = _load_root_resource_registries(root)
        findings.extend(annotate_findings(registry_findings, root=root, source_path=root.config_path))
        legacy_resources, resource_findings = load_config_resources(root.project_config, base_path=root.path)
        findings.extend(annotate_findings(resource_findings, root=root, source_path=root.config_path))
        root_base_paths = legacy_resources.base_lib_paths or (str(root.path),)
        registries[root.id] = WorkspaceResourceRegistries(base_registry, plugin_registry, root_base_paths, has_base_registry, has_plugin_registry)
        base_lib_paths.extend(root_base_paths)
        base_libs.extend(_with_resource_source((*base_registry.resources(), *legacy_resources.base_libs), root=root))
        plugins.extend(_with_resource_source((*plugin_registry.resources(), *legacy_resources.plugins), root=root))
    return (
        registries,
        ConfigResources(base_lib_paths=tuple(dict.fromkeys(base_lib_paths)), base_libs=tuple(base_libs), plugins=tuple(plugins)),
        tuple(findings),
    )


def workspace_finding(
    rule_id: str,
    message: str,
    *,
    root: WorkspaceRoot,
    source_path: Path,
    object_id: str = "workspace",
    failure_layer: str = "workspace",
    severity: str = "error",
) -> HealthFinding:
    return HealthFinding(
        rule_id=rule_id,
        severity=severity,
        object_type=failure_layer,
        object_id=object_id,
        source_location={"path": str(source_path)},
        failure_layer=failure_layer,
        message=message,
        suggested_fix_type="fix_config",
        root_id=root.id,
        root_path=str(root.path),
        source_path=str(source_path),
    )


def annotate_findings(findings, *, root: WorkspaceRoot, source_path: Path) -> tuple[HealthFinding, ...]:
    out: list[HealthFinding] = []
    for finding in findings:
        if isinstance(finding, HealthFinding):
            out.append(with_health_source(finding, root=root, source_path=source_path))
    return tuple(out)


def with_health_source(finding: HealthFinding, *, root: WorkspaceRoot, source_path: Path) -> HealthFinding:
    return replace(
        finding,
        root_id=finding.root_id or root.id,
        root_path=finding.root_path or str(root.path),
        source_path=finding.source_path or str(source_path),
    )


def _workspace_roots(value: object, *, workspace_path: Path) -> list[WorkspaceRoot]:
    if not isinstance(value, list) or not value:
        raise WorkspaceConfigError("WORKSPACE.ROOTS", "workspace roots must be a non-empty list", {"path": str(workspace_path)})
    roots: list[WorkspaceRoot] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise WorkspaceConfigError("WORKSPACE.ROOT.SHAPE", f"roots[{index}] must be an object", {"path": str(workspace_path)})
        unknown = set(item) - {"id", "path", "config"}
        if unknown:
            raise WorkspaceConfigError("WORKSPACE.ROOT.UNKNOWN_FIELD", f"roots[{index}] contains unknown fields: {sorted(unknown)}", {"path": str(workspace_path)})
        root_id = str(item.get("id", "")).strip()
        raw_path = str(item.get("path", "")).strip()
        if not root_id or not raw_path:
            raise WorkspaceConfigError("WORKSPACE.ROOT.REQUIRED", f"roots[{index}] requires id and path", {"path": str(workspace_path)})
        if root_id in seen:
            raise WorkspaceConfigError("WORKSPACE.ROOT.DUPLICATE", f"duplicate workspace root id: {root_id}", {"path": str(workspace_path)})
        seen.add(root_id)
        roots.append(_workspace_root_from_item(root_id, item, workspace_path=workspace_path))
    return roots


def _workspace_root_from_item(root_id: str, item: Mapping[str, Any], *, workspace_path: Path) -> WorkspaceRoot:
    root_path = _resolve_workspace_relative(str(item.get("path", "")).strip(), base=workspace_path.parent)
    if not root_path.is_dir():
        raise WorkspaceConfigError("WORKSPACE.ROOT.PATH", f"workspace root path does not exist: {root_path}", {"path": str(workspace_path)})
    config_name = str(item.get("config", PROJECT_CONFIG_NAME)).strip() or PROJECT_CONFIG_NAME
    config_path = _resolve_workspace_relative(config_name, base=root_path)
    if not config_path.is_file():
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.MISSING", f"project config does not exist: {config_path}", {"path": str(config_path)})
    project_config = _load_project_config(config_path)
    return WorkspaceRoot(
        id=root_id,
        path=root_path,
        config_path=config_path,
        project_config=project_config,
        registry_ref=str(project_config.get("registry", "")).strip(),
        quality_enabled=bool(project_config.get("quality_enabled", True)),
        quality_structure=_project_quality_structure(project_config, config_path),
        runtime_options=_project_runtime_options(project_config, config_path),
    )


def _load_project_config(path: Path) -> Mapping[str, Any]:
    try:
        document = load_raw_config_document(path)
    except ConfigLoadError as exc:
        raise WorkspaceConfigError(exc.rule_id, exc.message, exc.source_location, exc.failure_layer) from exc
    data = document.data
    unknown = set(data) - {"registry", "quality_enabled", "quality", "runtime", "base_lib", "plugins"}
    if unknown:
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.UNKNOWN_FIELD", f"project config contains unknown fields: {sorted(unknown)}", {"path": str(path)})
    if "registry" in data and not isinstance(data["registry"], str):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.REGISTRY", "project config registry must be a string", {"path": str(path)})
    if "quality_enabled" in data and not isinstance(data["quality_enabled"], bool):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", "project config quality_enabled must be a boolean", {"path": str(path)})
    _project_quality_structure(data, path)
    _project_runtime_options(data, path)
    return data


def _project_runtime_options(data: Mapping[str, Any], path: Path) -> Mapping[str, object]:
    raw_runtime = data.get("runtime")
    if raw_runtime in (None, {}):
        return {}
    if not isinstance(raw_runtime, Mapping):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.RUNTIME", "project config runtime must be an object", {"path": str(path)})
    allowed = {"async_max_workers", "async_flush_timeout", "nodeset_max_depth"}
    unknown = set(raw_runtime) - allowed
    if unknown:
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.RUNTIME",
            f"project config runtime contains unknown fields: {sorted(unknown)}",
            {"path": str(path)},
        )
    return {
        name: _project_runtime_value(name, value, path=path)
        for name, value in raw_runtime.items()
    }


def _project_runtime_value(name: str, value: object, *, path: Path) -> object:
    if name in {"async_max_workers", "nodeset_max_depth"}:
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        raise WorkspaceConfigError(
            "WORKSPACE.PROJECT_CONFIG.RUNTIME",
            f"runtime.{name} must be a positive integer",
            {"path": str(path)},
        )
    if value is None or (isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0):
        return value
    raise WorkspaceConfigError(
        "WORKSPACE.PROJECT_CONFIG.RUNTIME",
        "runtime.async_flush_timeout must be null or a non-negative number",
        {"path": str(path)},
    )


def _project_quality_structure(data: Mapping[str, Any], path: Path) -> QualityStructureLimits:
    raw_quality = data.get("quality")
    if raw_quality in (None, {}):
        return QualityStructureLimits()
    if not isinstance(raw_quality, Mapping):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", "project config quality must be an object", {"path": str(path)})
    unknown_quality = set(raw_quality) - {"structure"}
    if unknown_quality:
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", f"project config quality contains unknown fields: {sorted(unknown_quality)}", {"path": str(path)})
    raw_structure = raw_quality.get("structure")
    if raw_structure in (None, {}):
        return QualityStructureLimits()
    if not isinstance(raw_structure, Mapping):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", "project config quality.structure must be an object", {"path": str(path)})

    allowed = set(QualityStructureLimits().to_dict())
    unknown = set(raw_structure) - allowed
    if unknown:
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", f"project config quality.structure contains unknown fields: {sorted(unknown)}", {"path": str(path)})
    values = _quality_structure_values(raw_structure, path)
    limits = QualityStructureLimits(**values)
    _validate_quality_structure_pairs(limits, path)
    return limits


def _quality_structure_values(raw: Mapping[str, Any], path: Path) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for field, value in raw.items():
        if field in {"enabled", "enforce_role_imports"}:
            if not isinstance(value, bool):
                raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", f"quality.structure.{field} must be a boolean", {"path": str(path)})
            values[field] = value
        elif field == "allowed_root_code_files":
            values[field] = _string_tuple(value, f"quality.structure.{field}", path)
        else:
            values[field] = _positive_int(value, f"quality.structure.{field}", path)
    return values


def _validate_quality_structure_pairs(limits: QualityStructureLimits, path: Path) -> None:
    for warn_field, max_field in (
        ("warn_root_code_files", "max_root_code_files"),
        ("warn_code_dirs", "max_code_dirs"),
        ("warn_code_files_per_dir", "max_code_files_per_dir"),
        ("warn_code_dir_depth", "max_code_dir_depth"),
        ("warn_child_code_dirs_per_dir", "max_child_code_dirs_per_dir"),
        ("warn_root_level_code_files", "max_root_level_code_files"),
    ):
        if getattr(limits, warn_field) > getattr(limits, max_field):
            raise WorkspaceConfigError(
                "WORKSPACE.PROJECT_CONFIG.QUALITY",
                f"quality.structure.{warn_field} must be <= {max_field}",
                {"path": str(path)},
            )


def _positive_int(value: object, field: str, path: Path) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", f"{field} must be a positive integer", {"path": str(path)})
    return value


def _string_tuple(value: object, field: str, path: Path) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise WorkspaceConfigError("WORKSPACE.PROJECT_CONFIG.QUALITY", f"{field} must be a list of non-empty strings", {"path": str(path)})
    return tuple(dict.fromkeys(item.strip() for item in value))


def _validate_workspace_keys(data: Mapping[str, Any], path: Path) -> None:
    unknown = set(data) - {"policy", "roots"}
    if unknown:
        raise WorkspaceConfigError("WORKSPACE.UNKNOWN_FIELD", f"workspace config contains unknown fields: {sorted(unknown)}", {"path": str(path)})
    if "roots" not in data:
        raise WorkspaceConfigError("WORKSPACE.ROOTS", "workspace config requires roots", {"path": str(path)})


def _resolve_workspace_relative(value: str, *, base: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def _load_root_registry(root: WorkspaceRoot) -> NodeRegistry:
    module_ref, sep, factory_name = root.registry_ref.partition(":")
    if not sep or not module_ref.strip() or not factory_name.strip():
        raise WorkspaceConfigError("WORKSPACE.REGISTRY.REF", f"registry must use module_or_file:function syntax: {root.registry_ref}", {"path": str(root.config_path)})
    with _temporary_sys_path(root.path):
        module = _registry_module_or_error(module_ref.strip(), root=root)
        factory = _registry_factory_or_error(module, factory_name.strip(), root=root)
        try:
            registry = factory()
        except Exception as exc:
            raise WorkspaceConfigError("WORKSPACE.REGISTRY.FACTORY", f"registry factory failed for root '{root.id}' ({root.registry_ref}): {exc}", {"path": str(root.config_path)}) from exc
    if not isinstance(registry, NodeRegistry):
        raise WorkspaceConfigError("WORKSPACE.REGISTRY.RETURN", f"registry factory must return NodeRegistry: {root.registry_ref}", {"path": str(root.config_path)})
    return registry


def _load_root_resource_registries(root: WorkspaceRoot) -> tuple[BaseLibRegistry, PluginResourceRegistry, bool, bool, tuple[HealthFinding, ...]]:
    base_registry = BaseLibRegistry()
    plugin_registry = PluginResourceRegistry()
    has_base_registry = False
    has_plugin_registry = False
    findings: list[HealthFinding] = []
    if not root.registry_ref:
        return base_registry, plugin_registry, has_base_registry, has_plugin_registry, ()
    module_ref, sep, _ = root.registry_ref.partition(":")
    if not sep or not module_ref.strip():
        return base_registry, plugin_registry, has_base_registry, has_plugin_registry, ()
    try:
        with _temporary_sys_path(root.path):
            module = _registry_module_or_error(module_ref.strip(), root=root)
    except WorkspaceConfigError as exc:
        findings.append(
            workspace_finding(
                exc.rule_id,
                exc.message,
                root=root,
                source_path=root.config_path,
                object_id="registry",
                failure_layer=exc.failure_layer,
            )
        )
        return base_registry, plugin_registry, has_base_registry, has_plugin_registry, tuple(findings)
    for function_name, expected_type, target in (
        ("build_base_lib_registry", BaseLibRegistry, "base_lib"),
        ("build_plugin_registry", PluginResourceRegistry, "plugin"),
    ):
        factory = getattr(module, function_name, None)
        if factory is None:
            continue
        if target == "base_lib":
            has_base_registry = True
        else:
            has_plugin_registry = True
        if not callable(factory):
            findings.append(workspace_finding("WORKSPACE.REGISTRY.FACTORY", f"registry factory is not callable for root '{root.id}': {function_name}", root=root, source_path=root.config_path, object_id=function_name, failure_layer=target))
            continue
        try:
            value = factory()
        except Exception as exc:
            findings.append(workspace_finding("WORKSPACE.REGISTRY.FACTORY", f"registry factory failed for root '{root.id}' ({function_name}): {exc}", root=root, source_path=root.config_path, object_id=function_name, failure_layer=target))
            continue
        if not isinstance(value, expected_type):
            findings.append(workspace_finding("WORKSPACE.REGISTRY.RETURN", f"registry factory must return {expected_type.__name__}: {function_name}", root=root, source_path=root.config_path, object_id=function_name, failure_layer=target))
            continue
        if target == "base_lib":
            base_registry = value
        else:
            plugin_registry = value
    return base_registry, plugin_registry, has_base_registry, has_plugin_registry, tuple(findings)


def _registry_module_or_error(module_ref: str, *, root: WorkspaceRoot):
    try:
        return _import_registry_module(module_ref, root=root)
    except Exception as exc:
        raise WorkspaceConfigError("WORKSPACE.REGISTRY.IMPORT", f"registry import failed for root '{root.id}' ({root.registry_ref}): {exc}", {"path": str(root.config_path)}) from exc


def _registry_factory_or_error(module: object, factory_name: str, *, root: WorkspaceRoot):
    try:
        factory = getattr(module, factory_name)
    except AttributeError as exc:
        raise WorkspaceConfigError("WORKSPACE.REGISTRY.FACTORY", f"registry factory '{factory_name}' not found for root '{root.id}': {root.registry_ref}", {"path": str(root.config_path)}) from exc
    if not callable(factory):
        raise WorkspaceConfigError("WORKSPACE.REGISTRY.FACTORY", f"registry factory is not callable for root '{root.id}': {root.registry_ref}", {"path": str(root.config_path)})
    return factory


def _import_registry_module(module_ref: str, *, root: WorkspaceRoot):
    candidate = (root.path / module_ref).resolve()
    if module_ref.endswith(".py") or candidate.exists():
        path = Path(module_ref).resolve() if Path(module_ref).is_absolute() else candidate
        module_name = f"_vibeflow_workspace_registry_{abs(hash((str(root.path), str(path))))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load registry module: {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(module_ref)


def _merge_node_registry(target: NodeRegistry, source: NodeRegistry, *, root: WorkspaceRoot, sources: dict[str, dict[str, object]]) -> None:
    for key in source.available():
        if key in getattr(target, "_registry", {}):
            previous = sources.get(key, {})
            message = f"duplicate node type_key '{key}' from root '{root.id}' ({root.config_path}) conflicts with root '{previous.get('root_id', '')}' ({previous.get('source_path', '')})"
            raise WorkspaceConfigError("WORKSPACE.REGISTRY.DUPLICATE_TYPE_KEY", message, {"path": str(root.config_path)})
        getattr(target, "_registry")[key] = getattr(source, "_registry")[key]
        getattr(target, "_config_specs")[key] = getattr(source, "_config_specs")[key]
        info = getattr(source, "_registration_info", {}).get(key) or NodeRegistrationInfo(key=key, function="", path=str(root.config_path), line=1)
        getattr(target, "_registration_info")[key] = info
        sources[key] = {"root_id": root.id, "root_path": str(root.path), "source_path": str(root.config_path)}


def _merge_plugin_registry(target: PluginRegistry, source: PluginRegistry) -> None:
    for plugin_type in ("policy", "compiler", "runtime"):
        for plugin in getattr(source, f"{plugin_type}_plugins")():
            descriptor = getattr(source, "_descriptors")[id(plugin)]
            target.register(
                plugin,
                plugin_type=descriptor.plugin_type,
                name=descriptor.name,
                priority=descriptor.priority,
                scope=descriptor.scope,
                source=descriptor.source,
                class_name=descriptor.class_name,
                info=descriptor.info,
                config_keys=descriptor.config_keys,
                root_id=descriptor.root_id,
                root_path=descriptor.root_path,
                source_path=descriptor.source_path,
                conflict="error",
            )


def _with_resource_source(resources, *, root: WorkspaceRoot) -> tuple[object, ...]:
    return tuple(
        replace(
            resource,
            root_id=getattr(resource, "root_id", "") or root.id,
            root_path=getattr(resource, "root_path", "") or str(root.path),
            source_path=getattr(resource, "source_path", "") or str(root.config_path),
        )
        for resource in resources
    )


@contextmanager
def _temporary_sys_path(path: Path):
    value = str(path.resolve())
    inserted = value not in sys.path
    if inserted:
        sys.path.insert(0, value)
    try:
        yield
    finally:
        if inserted:
            try:
                sys.path.remove(value)
            except ValueError:
                pass
