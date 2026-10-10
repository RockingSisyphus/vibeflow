from __future__ import annotations

from typing import Any, Mapping

from vibeflow.tooling.project.schema_common import (
    _validate_rule_selection,
    _error,
    _non_empty_string,
    _validate_execution_lock,
    _validate_positive_int,
    _validate_provider_list,
    _validate_requirement_list,
    _validate_string_list,
)
from vibeflow.tooling.project.schema_node import _validate_node, _validate_node_similarity_targets, _validate_planned_behavior
from vibeflow.core.findings import HealthFinding
from vibeflow.core.constants import FLOW_KINDS
from vibeflow.core.flow import ENTRY_MODES

STATUSES = {"planned", "implemented"}


def collect_config_schema_findings(config: Mapping[str, Any]) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    if "rulesets" in config:
        _validate_rule_selection(config["rulesets"], "rulesets", findings)
    if _is_nodeset_definition(config):
        _validate_nodeset(config, "nodeset", findings)
        if "nodeset_imports" in config:
            _validate_nodeset_imports(config["nodeset_imports"], findings)
        return tuple(findings)
    pipeline = config.get("pipeline", config)
    if not isinstance(pipeline, Mapping):
        findings.append(_error("CONFIG.SCHEMA.PIPELINE_OBJECT", "pipeline must be an object", "pipeline"))
        return tuple(findings)
    _validate_pipeline(pipeline, "pipeline", findings)
    if "nodesets" in config:
        if config.get("__vibeflow_expanded_nodesets__") is True:
            _validate_nodesets(config["nodesets"], findings)
        else:
            findings.append(_error("CONFIG.NODESETS.INLINE_REMOVED", "inline nodesets are removed; import one nodeset JSONC file per type_key with nodeset_imports", "nodesets"))
    if "nodeset_imports" in config:
        _validate_nodeset_imports(config["nodeset_imports"], findings)
    if "boundary" in config:
        findings.append(_error("CONFIG.BOUNDARY.REMOVED", "boundary is removed; use terminal/io/data_store/document nodes", "boundary"))
    if "global_config" in config:
        _validate_global_config(config["global_config"], "global_config", findings)
    if "base_lib" in config:
        _validate_base_lib_resources(config["base_lib"], findings)
    if "plugins" in config:
        _validate_plugins(config["plugins"], findings)
    if "host_extensions" in config:
        _validate_host_extensions(config["host_extensions"], findings)
    if "policy" in config:
        _validate_policy(config["policy"], "policy", findings, rule_source="config.inline_policy")
    return tuple(findings)


def collect_policy_schema_findings(
    policy: Any,
    *,
    object_prefix: str = "policy",
    rule_source: str = "config.inline_policy",
) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    _validate_policy(policy, object_prefix, findings, rule_source=rule_source)
    return tuple(findings)


def _validate_pipeline(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    from vibeflow.core.contracts import parse_pipeline_inputs

    if "inputs" in value:
        try:
            parse_pipeline_inputs(value["inputs"], field=f"{prefix}.inputs")
        except ValueError as exc:
            findings.append(_error("CONFIG.SCHEMA.PIPELINE_INPUTS", str(exc), f"{prefix}.inputs"))
    if "execution_lock" in value:
        _validate_execution_lock(
            value["execution_lock"],
            f"{prefix}.execution_lock",
            findings,
        )
    if "entry_mode" in value and value["entry_mode"] not in ENTRY_MODES:
        findings.append(
            _error(
                "CONFIG.SCHEMA.ENTRY_MODE",
                f"{prefix}.entry_mode must be one of {sorted(ENTRY_MODES)}",
                f"{prefix}.entry_mode",
            )
        )
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        findings.append(_error("CONFIG.SCHEMA.NODES_LIST", f"{prefix}.nodes must be a non-empty list", f"{prefix}.nodes"))
    elif not nodes:
        findings.append(_error("CONFIG.SCHEMA.NODES_NON_EMPTY", f"{prefix}.nodes must be a non-empty list", f"{prefix}.nodes"))
    else:
        for index, node in enumerate(nodes):
            _validate_node(node, f"{prefix}.nodes[{index}]", findings)
        _validate_node_similarity_targets(nodes, f"{prefix}.nodes", findings)

    if "edges" in value:
        edges = value["edges"]
        if not isinstance(edges, list):
            findings.append(_error("CONFIG.SCHEMA.EDGES_LIST", f"{prefix}.edges must be a list", f"{prefix}.edges"))
        else:
            for index, edge in enumerate(edges):
                _validate_edge(edge, f"{prefix}.edges[{index}]", findings)

    if "loops" in value:
        findings.append(_error("CONFIG.LOOPS.REMOVED", f"{prefix}.loops is removed; use vibeflow.loop.while nodes", f"{prefix}.loops"))
    if "max_steps" in value:
        _validate_positive_int(value["max_steps"], f"{prefix}.max_steps", findings, "CONFIG.SCHEMA.MAX_STEPS")


def _validate_edge(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if isinstance(value, list):
        _validate_edge_pair(value, prefix, findings)
        return
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.EDGE_OBJECT", f"{prefix} must be [from, to] or an object", prefix))
        return
    _validate_edge_endpoints(value, prefix, findings)
    _validate_removed_edge_fields(value, prefix, findings)
    if "when" in value and not isinstance(value["when"], str):
        findings.append(_error("CONFIG.SCHEMA.EDGE_WHEN", f"{prefix}.when must be a string", f"{prefix}.when"))
    for role in ("schedule", "transfer"):
        if role in value and not isinstance(value[role], bool):
            findings.append(
                _error(
                    f"CONFIG.SCHEMA.EDGE_{role.upper()}",
                    f"{prefix}.{role} must be a boolean",
                    f"{prefix}.{role}",
                )
            )
    if value.get("schedule") is False and value.get("transfer") is False:
        findings.append(
            _error(
                "CONFIG.SCHEMA.EDGE_ROLES",
                f"{prefix} must schedule, transfer, or both",
                prefix,
            )
        )


def _validate_edge_pair(value: list[Any], prefix: str, findings: list[HealthFinding]) -> None:
    if len(value) != 2 or not all(_non_empty_string(item) for item in value):
        findings.append(_error("CONFIG.SCHEMA.EDGE_PAIR", f"{prefix} must be [from, to] with non-empty strings", prefix))


def _validate_edge_endpoints(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if not (_non_empty_string(value.get("from")) or _non_empty_string(value.get("source"))):
        findings.append(_error("CONFIG.SCHEMA.EDGE_FROM", f"{prefix}.from must be a non-empty string", f"{prefix}.from"))
    if not (_non_empty_string(value.get("to")) or _non_empty_string(value.get("target"))):
        findings.append(_error("CONFIG.SCHEMA.EDGE_TO", f"{prefix}.to must be a non-empty string", f"{prefix}.to"))


def _validate_removed_edge_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "max_executions" in value:
        findings.append(_error("CONFIG.LOOP_LIMITS.REMOVED", f"{prefix}.max_executions is removed; use pipeline.max_steps", f"{prefix}.max_executions"))
    if "max" in value:
        findings.append(_error("CONFIG.LOOP_LIMITS.REMOVED", f"{prefix}.max is removed; use pipeline.max_steps", f"{prefix}.max"))
    if "loop" in value:
        findings.append(_error("CONFIG.LOOPS.REMOVED", f"{prefix}.loop is removed; use vibeflow.loop.while nodes", f"{prefix}.loop"))


def _validate_nodesets(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.NODESETS_LIST", "nodesets must be a list", "nodesets"))
        return
    for index, item in enumerate(value):
        prefix = f"nodesets[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODESET_OBJECT", f"{prefix} must be an object", prefix))
            continue
        _validate_nodeset(item, prefix, findings)


def _validate_nodeset(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    status = str(item.get("status", "implemented")).strip()
    if "rulesets" in item:
        _validate_rule_selection(item["rulesets"], f"{prefix}.rulesets", findings)
    _validate_nodeset_identity(item, prefix, findings, status=status)
    _validate_nodeset_metadata(item, prefix, findings, status=status)
    _validate_nodeset_contract(item, prefix, findings, status=status)
    _validate_planned_behavior(item, prefix, findings, status=status)
    if "global_config" in item:
        _validate_global_config(item["global_config"], f"{prefix}.global_config", findings)
    _validate_nodeset_pipeline(item, prefix, findings, status=status)


def _validate_nodeset_identity(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    for removed in ("name", "category", "version", "purity", "exports"):
        if removed in item:
            findings.append(_error("CONFIG.SCHEMA.NODESET_FIELD_REMOVED", f"{prefix}.{removed} is removed from nodeset definitions", f"{prefix}.{removed}"))
    if not _non_empty_string(item.get("type_key")):
        findings.append(_error("CONFIG.SCHEMA.NODESET_MISSING_TYPE_KEY", f"{prefix}.type_key must be a non-empty string", f"{prefix}.type_key"))
    if status not in STATUSES:
        findings.append(_error("GRAPH.PLANNED.STATUS_INVALID", f"{prefix}.status must be planned or implemented", f"{prefix}.status"))
    flow_kind = str(item.get("flow_kind", "predefined")).strip() or "predefined"
    if flow_kind not in FLOW_KINDS:
        findings.append(_error("NODE.FLOW_KIND.INVALID", f"{prefix}.flow_kind must be one of {sorted(FLOW_KINDS)}", f"{prefix}.flow_kind"))


def _validate_nodeset_metadata(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    for field in ("display_name", "description"):
        if not _non_empty_string(item.get(field)):
            findings.append(_error("CONFIG.SCHEMA.NODESET_METADATA", f"{prefix}.{field} must be a non-empty string", f"{prefix}.{field}"))
    if "expand" in item and not isinstance(item["expand"], bool):
        findings.append(_error("CONFIG.SCHEMA.NODESET_EXPAND", f"{prefix}.expand must be a boolean", f"{prefix}.expand"))


def _validate_nodeset_contract(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    for required_field in ("requires", "provides"):
        if required_field not in item:
            findings.append(_error("CONFIG.SCHEMA.NODESET_CONTRACT", f"{prefix}.{required_field} must be declared", f"{prefix}.{required_field}"))
        if required_field in item:
            if required_field == "requires":
                _validate_requirement_list(item[required_field], f"{prefix}.{required_field}", findings, "CONFIG.SCHEMA.NODESET_CONTRACT_LIST")
            else:
                _validate_provider_list(item[required_field], f"{prefix}.{required_field}", findings, "CONFIG.SCHEMA.NODESET_CONTRACT_LIST")


def _validate_nodeset_pipeline(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    pipeline = item.get("pipeline")
    if pipeline is None and status == "planned":
        return
    if not isinstance(pipeline, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODESET_PIPELINE", f"{prefix}.pipeline must be an object", f"{prefix}.pipeline"))
        return
    _validate_pipeline(pipeline, f"{prefix}.pipeline", findings)


def _validate_nodeset_imports(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.NODESET_IMPORTS_LIST", "nodeset_imports must be a list", "nodeset_imports"))
        return
    for index, item in enumerate(value):
        prefix = f"nodeset_imports[{index}]"
        if isinstance(item, str):
            if not item.strip():
                findings.append(_error("CONFIG.SCHEMA.NODESET_IMPORT_PATH", f"{prefix} must be a non-empty path string", prefix))
            continue
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODESET_IMPORT_OBJECT", f"{prefix} must be a string or object", prefix))
            continue
        if not _non_empty_string(item.get("path")):
            findings.append(_error("CONFIG.SCHEMA.NODESET_IMPORT_PATH", f"{prefix}.path must be a non-empty string", f"{prefix}.path"))
        if "names" in item:
            findings.append(_error("CONFIG.SCHEMA.NODESET_IMPORT_NAMES_REMOVED", f"{prefix}.names is removed; each nodeset file defines exactly one type_key", f"{prefix}.names"))


def _validate_policy(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.POLICY_ROOT", f"{prefix} must be an object", prefix, rule_source=rule_source))
        return
    if "node_source" in value:
        _validate_node_source_policy(value["node_source"], f"{prefix}.node_source", findings, rule_source=rule_source)
    if "complexity" in value:
        _validate_int_policy(value["complexity"], f"{prefix}.complexity", ("max_functions", "max_branches", "max_nesting_depth", "max_params", "max_contract_keys"), findings, rule_source=rule_source, allow_null=True)
    if "imports" in value:
        _validate_string_list_policy(value["imports"], f"{prefix}.imports", ("allowed_roots", "banned_roots", "allowed_modules", "banned_modules"), findings, rule_source=rule_source)
    if "base_lib" in value:
        findings.append(_error("CONFIG.POLICY.BASE_LIB.REMOVED", "policy.base_lib is removed; declare BaseLib dependencies on resources and configure external imports through policy.imports", f"{prefix}.base_lib", rule_source=rule_source))
    if "maintainability" in value:
        _validate_int_policy(value["maintainability"], f"{prefix}.maintainability", ("warn_call_chain_length", "max_call_chain_length", "warn_dependency_chain_length", "max_dependency_chain_length"), findings, rule_source=rule_source, allow_null=False)
    if "rules" in value:
        findings.append(_error("CONFIG.POLICY.RULES.REMOVED", "policy rules are removed; select a Ruleset with overrides", f"{prefix}.rules"))


def _validate_node_source_policy(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    _validate_int_policy(value, prefix, ("max_lines", "max_bytes", "warn_lines", "warn_bytes"), findings, rule_source=rule_source, allow_null=False)


def _validate_int_policy(value: Any, prefix: str, fields: tuple[str, ...], findings: list[HealthFinding], *, rule_source: str, allow_null: bool) -> None:
    _validate_policy_section(value, prefix, findings, rule_source=rule_source)
    if isinstance(value, Mapping):
        _validate_policy_int_fields(value, prefix, fields, findings, rule_source=rule_source, allow_null=allow_null)


def _validate_policy_int_fields(value: Mapping[str, Any], prefix: str, fields: tuple[str, ...], findings: list[HealthFinding], *, rule_source: str, allow_null: bool) -> None:
    for field in fields:
        if field in value and not (allow_null and value[field] is None):
            _validate_positive_int(
                value[field],
                f"{prefix}.{field}",
                findings,
                "CONFIG.SCHEMA.POLICY_POSITIVE_INT",
                rule_source=rule_source,
            )


def _validate_string_list_policy(value: Any, prefix: str, fields: tuple[str, ...], findings: list[HealthFinding], *, rule_source: str) -> None:
    _validate_policy_section(value, prefix, findings, rule_source=rule_source)
    if not isinstance(value, Mapping):
        return
    for field in fields:
        if field in value:
            _validate_string_list(
                value[field],
                f"{prefix}.{field}",
                findings,
                "CONFIG.SCHEMA.POLICY_STRING_LIST",
                rule_source=rule_source,
            )


def collect_plugin_selection_findings(value: Any) -> list[HealthFinding]:
    """Validate only selection fields before loading trusted entry modules."""
    findings: list[HealthFinding] = []
    _validate_plugins(value, findings)
    return findings


def _validate_plugins(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.PLUGINS_LIST", "plugins must be a list", "plugins"))
        return
    allowed = {"id", "source", "root", "config", "enabled", "status", "style"}
    planned_fields = {"type", "targets", "display_name", "description", "version", "priority"}
    for index, item in enumerate(value):
        prefix = f"plugins[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error("PLUGIN.SELECTION.MIGRATION", "plugins require explicit SDK entry sources", prefix))
            continue
        if "enabled" in item and not isinstance(item["enabled"], bool):
            findings.append(_error("PLUGIN.SELECTION.SHAPE", "enabled must be boolean", prefix + ".enabled"))
        if "style" in item:
            from vibeflow.core.descriptors.presentation import normalize_presentation
            try:
                if not isinstance(item["style"], Mapping) or set(item["style"]) - {"fill","stroke","text"}:
                    raise ValueError("resource style only accepts fill/stroke/text")
                normalize_presentation(item["style"],field_name=prefix + ".style")
            except ValueError as exc:
                findings.append(_error("CONFIG.SCHEMA.RESOURCE_STYLE", str(exc), prefix + ".style"))
        status = item.get("status", "implemented")
        if not isinstance(status, str) or status not in {"implemented", "planned"}:
            findings.append(_error("CONFIG.SCHEMA.RESOURCE_STATUS", "plugin status must be implemented or planned", prefix + ".status"))
        unknown = set(item) - allowed - (planned_fields if status == "planned" else set())
        if unknown:
            findings.append(_error("PLUGIN.SELECTION.MIGRATION", f"unsupported plugin fields: {sorted(unknown)}; use an SDK plugin source", prefix))
        for field in ("id", "root"):
            if field in item and not _non_empty_string(item[field]):
                findings.append(_error("PLUGIN.SELECTION.SHAPE", f"{field} must be a non-empty string", prefix + "." + field))
        if "config" in item and not isinstance(item["config"], Mapping):
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_CONFIG", "plugin config must be an object", prefix + ".config"))
        if status == "planned":
            if not _non_empty_string(item.get("id")):
                findings.append(_error("CONFIG.SCHEMA.PLUGIN_PLANNED_ID", "planned plugins require an id", prefix))
            for field in ("display_name", "description", "version"):
                if field in item and not isinstance(item[field], str):
                    findings.append(_error("CONFIG.SCHEMA.RESOURCE_METADATA_STRING", f"{field} must be a string", prefix + "." + field))
            if "priority" in item and (isinstance(item["priority"], bool) or not isinstance(item["priority"], int)):
                findings.append(_error("PLUGIN.SELECTION.PRIORITY", "priority must be an integer", prefix + ".priority"))
            if "type" in item and item["type"] not in ("compiler", "runtime"):
                findings.append(_error("CONFIG.SCHEMA.PLUGIN_TYPE", "planned plugin type must be compiler or runtime", prefix + ".type"))
            if "targets" in item:
                _validate_string_list(item["targets"], prefix + ".targets", findings, "CONFIG.SCHEMA.PLUGIN_TARGETS")
        source = item.get("source")
        if source is None and (status == "planned" or item.get("enabled") is False):
            continue
        if not isinstance(source, Mapping):
            findings.append(_error("PLUGIN.SELECTION.SOURCE", "implemented plugins require an explicit source", prefix + ".source"))
            continue
        if set(source) - {"kind", "ref", "export"} or source.get("kind") not in ("file", "module", "package") or not _non_empty_string(source.get("ref")):
            findings.append(_error("PLUGIN.SELECTION.SOURCE", "source requires kind (file/module/package), ref and optional export", prefix + ".source"))
        if "export" in source and not _non_empty_string(source["export"]):
            findings.append(_error("PLUGIN.SELECTION.SOURCE", "export must be a non-empty string", prefix + ".source.export"))


def _validate_host_extensions(
    value: Any,
    findings: list[HealthFinding],
) -> None:
    if not isinstance(value, list):
        findings.append(
            _error(
                "CONFIG.SCHEMA.HOST_EXTENSIONS_LIST",
                "host_extensions must be a list",
                "host_extensions",
            )
        )
        return
    seen: set[str] = set()
    for index, item in enumerate(value):
        prefix = f"host_extensions[{index}]"
        active = True
        if isinstance(item, str):
            extension_id = item.strip()
            if not extension_id:
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.HOST_EXTENSION_ID",
                        f"{prefix} must be a non-empty host_extension id",
                        prefix,
                    )
                )
                continue
        elif isinstance(item, Mapping):
            extension_id = str(
                item.get("id", item.get("name", ""))
            ).strip()
            if not extension_id:
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.HOST_EXTENSION_ID",
                        f"{prefix}.id must be a non-empty string",
                        f"{prefix}.id",
                    )
                )
            status = (
                str(item.get("status", "implemented")).strip()
                or "implemented"
            )
            if status not in STATUSES:
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.RESOURCE_STATUS",
                        (
                            f"{prefix}.status must be implemented "
                            "or planned"
                        ),
                        f"{prefix}.status",
                    )
                )
            if "enabled" in item and not isinstance(item["enabled"], bool):
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.HOST_EXTENSION_ENABLED",
                        f"{prefix}.enabled must be a boolean",
                        f"{prefix}.enabled",
                    )
                )
            active = item.get("enabled", True) is not False
            for field in ("config", "settings"):
                if field in item and not isinstance(item[field], Mapping):
                    findings.append(
                        _error(
                            "CONFIG.SCHEMA.HOST_EXTENSION_CONFIG",
                            f"{prefix}.{field} must be an object",
                            f"{prefix}.{field}",
                        )
                    )
            for field in ("targets", "provides", "dependencies"):
                if field in item:
                    _validate_string_list(
                        item[field],
                        f"{prefix}.{field}",
                        findings,
                        "CONFIG.SCHEMA.HOST_EXTENSION_STRING_LIST",
                    )
            _validate_resource_metadata_strings(item, prefix, findings)
        else:
            findings.append(
                _error(
                    "CONFIG.SCHEMA.HOST_EXTENSION_OBJECT",
                    f"{prefix} must be a string or object",
                    prefix,
                )
            )
            continue
        if active and extension_id and extension_id in seen:
            findings.append(
                _error(
                    "CONFIG.SCHEMA.HOST_EXTENSION_DUPLICATE",
                    f"duplicate host_extension id: {extension_id}",
                    prefix,
                )
            )
        if active and extension_id:
            seen.add(extension_id)


def _validate_base_lib_resources(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.BASE_LIB", "base_lib must be an object", "base_lib"))
        return
    if "paths" in value:
        findings.append(_error("CONFIG.BASE_LIB.REGISTRATION_REMOVED", "base_lib.paths is removed; contribute BaseLib resources through an SDK plugin", "base_lib.paths"))
    if "modules" not in value:
        return
    modules = value["modules"]
    if not isinstance(modules, list):
        findings.append(_error("CONFIG.SCHEMA.BASE_LIB_MODULES", "base_lib.modules must be a list", "base_lib.modules"))
        return
    for index, item in enumerate(modules):
        prefix = f"base_lib.modules[{index}]"
        if isinstance(item, str):
            if not item.strip():
                findings.append(_error("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix} must be a non-empty resource ID", prefix))
            continue
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix} must be a string or object", prefix))
            continue
        if "module" in item or "name" in item:
            findings.append(_error("CONFIG.BASE_LIB.REGISTRATION_REMOVED", f"{prefix} must select a contributed BaseLib by id; module/name registration is removed", prefix))
        if not _non_empty_string(item.get("id")):
            findings.append(_error("CONFIG.SCHEMA.BASE_LIB_MODULE", f"{prefix}.id must be a non-empty resource ID", f"{prefix}.id"))
        status = str(item.get("status", "implemented")).strip() or "implemented"
        if status not in STATUSES:
            findings.append(_error("CONFIG.SCHEMA.RESOURCE_STATUS", f"{prefix}.status must be implemented or planned", f"{prefix}.status"))
        _validate_resource_metadata_strings(item, prefix, findings)


def _validate_global_config(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.GLOBAL_CONFIG", f"{prefix} must be an object", prefix))
        return
    for field in ("allow_config_override", "override_child_config"):
        if field in value and not isinstance(value[field], bool):
            findings.append(_error("CONFIG.SCHEMA.CONFIG_OVERRIDE_FLAG", f"{prefix}.{field} must be a boolean", f"{prefix}.{field}"))
    for field in ("config", "values"):
        if field in value and not isinstance(value[field], Mapping):
            findings.append(_error("CONFIG.SCHEMA.GLOBAL_CONFIG_VALUES", f"{prefix}.{field} must be an object", f"{prefix}.{field}"))


def _validate_resource_metadata_strings(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "style" in value:
        from vibeflow.core.descriptors.presentation import normalize_presentation
        try:
            if not isinstance(value["style"], Mapping) or set(value["style"]) - {"fill", "stroke", "text"}:
                raise ValueError("resource style only accepts fill/stroke/text")
            normalize_presentation(value["style"], field_name=prefix + ".style")
        except ValueError as error:
            findings.append(_error("CONFIG.SCHEMA.RESOURCE_STYLE", str(error), prefix + ".style"))
    for field in ("display_name", "category", "description", "version"):
        if field in value and not isinstance(value[field], str):
            findings.append(_error("CONFIG.SCHEMA.RESOURCE_METADATA_STRING", f"{prefix}.{field} must be a string", f"{prefix}.{field}"))


def _validate_policy_section(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.POLICY_SECTION", f"{prefix} must be an object", prefix, rule_source=rule_source))


def _is_nodeset_definition(config: Mapping[str, Any]) -> bool:
    return isinstance(config.get("type_key"), str)


__all__ = [
    "collect_config_schema_findings",
    "collect_policy_schema_findings",
]
