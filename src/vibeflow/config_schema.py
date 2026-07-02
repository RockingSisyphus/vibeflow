from __future__ import annotations

from typing import Any, Mapping

from .health_types import HealthFinding
from .node import FLOW_KINDS
from .schema_findings import schema_finding

STATUSES = {"planned", "implemented"}


def collect_config_schema_findings(config: Mapping[str, Any]) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    pipeline = config.get("pipeline", config)
    if not isinstance(pipeline, Mapping):
        findings.append(_error("CONFIG.SCHEMA.PIPELINE_OBJECT", "pipeline must be an object", "pipeline"))
        return tuple(findings)
    _validate_pipeline(pipeline, "pipeline", findings)
    if "nodesets" in config:
        _validate_nodesets(config["nodesets"], findings)
    if "nodeset_imports" in config:
        _validate_nodeset_imports(config["nodeset_imports"], findings)
    if "boundary" in config:
        findings.append(_error("CONFIG.BOUNDARY.REMOVED", "boundary is removed; use terminal/io/data_store/document nodes", "boundary"))
    if "plugins" in config:
        _validate_plugins(config["plugins"], findings)
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
    nodes = value.get("nodes")
    if not isinstance(nodes, list):
        findings.append(_error("CONFIG.SCHEMA.NODES_LIST", f"{prefix}.nodes must be a non-empty list", f"{prefix}.nodes"))
    elif not nodes:
        findings.append(_error("CONFIG.SCHEMA.NODES_NON_EMPTY", f"{prefix}.nodes must be a non-empty list", f"{prefix}.nodes"))
    else:
        for index, node in enumerate(nodes):
            _validate_node(node, f"{prefix}.nodes[{index}]", findings)

    if "edges" in value:
        edges = value["edges"]
        if not isinstance(edges, list):
            findings.append(_error("CONFIG.SCHEMA.EDGES_LIST", f"{prefix}.edges must be a list", f"{prefix}.edges"))
        else:
            for index, edge in enumerate(edges):
                _validate_edge(edge, f"{prefix}.edges[{index}]", findings)

    if "loops" in value:
        findings.append(_error("CONFIG.LOOPS.REMOVED", f"{prefix}.loops is removed; use decision routed cycles", f"{prefix}.loops"))
    if "max_steps" in value:
        _validate_positive_int(value["max_steps"], f"{prefix}.max_steps", findings, "CONFIG.SCHEMA.MAX_STEPS")


def _validate_node(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_OBJECT", f"{prefix} must be an object", prefix))
        return
    status = str(value.get("status", "implemented")).strip()
    _validate_node_identity(value, prefix, findings, status=status)
    _validate_node_contract_fields(value, prefix, findings)
    _validate_node_config_fields(value, prefix, findings)
    _validate_node_async_fields(value, prefix, findings)


def _validate_node_identity(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    if not _non_empty_string(value.get("name")):
        findings.append(_error("CONFIG.SCHEMA.NODE_MISSING_NAME", f"{prefix}.name must be a non-empty string", f"{prefix}.name"))
    if status not in STATUSES:
        findings.append(_error("GRAPH.PLANNED.STATUS_INVALID", f"{prefix}.status must be planned or implemented", f"{prefix}.status"))
    if status == "planned" and not _non_empty_string(value.get("flow_kind")):
        findings.append(_error("GRAPH.PLANNED.MISSING_FLOW_KIND", f"{prefix}.flow_kind is required for planned nodes", f"{prefix}.flow_kind"))
    if _non_empty_string(value.get("flow_kind")) and value.get("flow_kind") not in FLOW_KINDS:
        findings.append(_error("NODE.FLOW_KIND.INVALID", f"{prefix}.flow_kind must be one of {sorted(FLOW_KINDS)}", f"{prefix}.flow_kind"))
    if status == "implemented" and _non_empty_string(value.get("flow_kind")):
        findings.append(_error("GRAPH.PLANNED.IMPLEMENTED_HAS_CONFIG_FLOW_KIND", f"{prefix}.flow_kind is only allowed for planned nodes", f"{prefix}.flow_kind"))
    if status != "planned" and not (_non_empty_string(value.get("type")) or _non_empty_string(value.get("registry_key"))):
        findings.append(
            _error(
                "CONFIG.SCHEMA.NODE_MISSING_TYPE",
                f"{prefix} must define non-empty string field 'type' or 'registry_key'",
                f"{prefix}.type",
            )
        )


def _validate_node_contract_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    for field in ("requires", "provides"):
        if field in value:
            _validate_string_list(value[field], f"{prefix}.{field}", findings, f"CONFIG.SCHEMA.NODE_{field.upper()}_LIST")


def _validate_node_config_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "config" in value and not isinstance(value["config"], Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_CONFIG_OBJECT", f"{prefix}.config must be an object", f"{prefix}.config"))
    if "node_configs" in value:
        _validate_node_configs(value["node_configs"], f"{prefix}.node_configs", findings)


def _validate_node_async_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    mode = value.get("async", "")
    if mode not in {"", "detached", "result_key"}:
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC", f"{prefix}.async must be 'detached' or 'result_key'", f"{prefix}.async"))
    result_key = value.get("result_key", "")
    if mode == "result_key" and not _non_empty_string(result_key):
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY", f"{prefix}.result_key is required when async is 'result_key'", f"{prefix}.result_key"))
    if mode != "result_key" and result_key:
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY", f"{prefix}.result_key requires async='result_key'", f"{prefix}.result_key"))


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
        findings.append(_error("CONFIG.LOOPS.REMOVED", f"{prefix}.loop is removed; use edge.when", f"{prefix}.loop"))


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
    _validate_nodeset_identity(item, prefix, findings, status=status)
    _validate_nodeset_metadata(item, prefix, findings, status=status)
    _validate_nodeset_contract(item, prefix, findings, status=status)
    _validate_nodeset_pipeline(item, prefix, findings, status=status)


def _validate_nodeset_identity(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    if not _non_empty_string(item.get("name")):
        findings.append(_error("CONFIG.SCHEMA.NODESET_MISSING_NAME", f"{prefix}.name must be a non-empty string", f"{prefix}.name"))
    if status not in STATUSES:
        findings.append(_error("GRAPH.PLANNED.STATUS_INVALID", f"{prefix}.status must be planned or implemented", f"{prefix}.status"))
    flow_kind = str(item.get("flow_kind", "predefined")).strip() or "predefined"
    if flow_kind not in FLOW_KINDS:
        findings.append(_error("NODE.FLOW_KIND.INVALID", f"{prefix}.flow_kind must be one of {sorted(FLOW_KINDS)}", f"{prefix}.flow_kind"))


def _validate_nodeset_metadata(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    for field in ("display_name", "category", "description", "version", "purity"):
        if status != "planned" and not _non_empty_string(item.get(field)):
            findings.append(_error("CONFIG.SCHEMA.NODESET_METADATA", f"{prefix}.{field} must be a non-empty string", f"{prefix}.{field}"))
    if item.get("purity") not in {None, "pure"}:
        findings.append(_error("CONFIG.SCHEMA.NODESET_PURITY", f"{prefix}.purity must be 'pure'", f"{prefix}.purity"))


def _validate_nodeset_contract(item: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    for required_field in ("requires", "provides", "exports"):
        if status != "planned" and required_field not in item:
            findings.append(_error("CONFIG.SCHEMA.NODESET_CONTRACT", f"{prefix}.{required_field} must be declared", f"{prefix}.{required_field}"))
        if required_field in item:
            _validate_string_list(item[required_field], f"{prefix}.{required_field}", findings, "CONFIG.SCHEMA.NODESET_CONTRACT_LIST")


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
            _validate_string_list(item["names"], f"{prefix}.names", findings, "CONFIG.SCHEMA.NODESET_IMPORT_NAMES")


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
        _validate_string_list_policy(value["base_lib"], f"{prefix}.base_lib", ("allowed_paths", "allowed_modules", "banned_modules"), findings, rule_source=rule_source)
    if "maintainability" in value:
        _validate_int_policy(value["maintainability"], f"{prefix}.maintainability", ("warn_call_chain_length", "max_call_chain_length", "warn_dependency_chain_length", "max_dependency_chain_length"), findings, rule_source=rule_source, allow_null=False)
    if "rules" in value:
        _validate_rules_policy(value["rules"], f"{prefix}.rules", findings, rule_source=rule_source)


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


def _validate_rules_policy(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    _validate_policy_section(value, prefix, findings, rule_source=rule_source)
    if not isinstance(value, Mapping):
        return
    for field in ("downgrades", "exemptions"):
        if field in value:
            _validate_rule_entries(value[field], f"{prefix}.{field}", findings, rule_source=rule_source)


def _validate_plugins(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.PLUGINS_LIST", "plugins must be a list", "plugins"))
        return
    for index, item in enumerate(value):
        prefix = f"plugins[{index}]"
        if isinstance(item, str):
            if not item.strip():
                findings.append(_error("CONFIG.SCHEMA.PLUGIN_MODULE", f"{prefix} must be a non-empty module string", prefix))
            continue
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_OBJECT", f"{prefix} must be a string or object", prefix))
            continue
        if not _non_empty_string(item.get("module", item.get("path"))):
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_MODULE", f"{prefix}.module or path must be a non-empty string", f"{prefix}.module"))
        if "class" in item and not _non_empty_string(item["class"]):
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_CLASS", f"{prefix}.class must be a non-empty string", f"{prefix}.class"))
        if item.get("type", "policy") == "boundary":
            findings.append(_error("CONFIG.BOUNDARY.REMOVED", f"{prefix}.type boundary is removed; use runtime plugins", f"{prefix}.type"))
        elif item.get("type", "policy") not in {"policy", "compiler", "runtime"}:
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_TYPE", f"{prefix}.type must be policy, compiler, or runtime", f"{prefix}.type"))
        if "priority" in item:
            _validate_positive_int(item["priority"], f"{prefix}.priority", findings, "CONFIG.SCHEMA.PLUGIN_PRIORITY")
        if item.get("conflict", "error") not in {"error", "replace"}:
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_CONFLICT", f"{prefix}.conflict must be error or replace", f"{prefix}.conflict"))


def _validate_node_configs(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_CONFIGS_OBJECT", f"{prefix} must be an object", prefix))
        return
    for key, item in value.items():
        if not _non_empty_string(key):
            findings.append(_error("CONFIG.SCHEMA.NODE_CONFIGS_KEY", f"{prefix} keys must be non-empty strings", prefix))
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODE_CONFIG_OBJECT", f"{prefix}.{key} must be an object", f"{prefix}.{key}"))


def _validate_policy_section(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.POLICY_SECTION", f"{prefix} must be an object", prefix, rule_source=rule_source))


def _validate_rule_entries(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.POLICY_RULES_LIST", f"{prefix} must be a list", prefix, rule_source=rule_source))
        return
    for index, item in enumerate(value):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_OBJECT", f"{item_prefix} must be an object", item_prefix, rule_source=rule_source))
            continue
        if not _non_empty_string(item.get("rule_id")):
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_ID", f"{item_prefix}.rule_id must be a non-empty string", f"{item_prefix}.rule_id", rule_source=rule_source))
        if prefix.endswith(".downgrades") and item.get("to") not in {"warning", "info", "skip"}:
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_TO", f"{item_prefix}.to must be warning, info, or skip", f"{item_prefix}.to", rule_source=rule_source))
        if not _non_empty_string(item.get("reason")):
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_REASON", f"{item_prefix}.reason must be a non-empty string", f"{item_prefix}.reason", rule_source=rule_source))
        if "scope" in item and not isinstance(item["scope"], Mapping):
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_SCOPE", f"{item_prefix}.scope must be an object", f"{item_prefix}.scope", rule_source=rule_source))
        if not _non_empty_string(item.get("expires")):
            findings.append(_error("CONFIG.SCHEMA.POLICY_RULE_EXPIRES", f"{item_prefix}.expires must be a non-empty string", f"{item_prefix}.expires", rule_source=rule_source))


def _validate_string_list(
    value: Any,
    object_id: str,
    findings: list[HealthFinding],
    rule_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> None:
    if not isinstance(value, list) or any(not _non_empty_string(item) for item in value):
        findings.append(_error(rule_id, f"{object_id} must be a list of non-empty strings", object_id, rule_source=rule_source))


def _validate_positive_int(
    value: Any,
    object_id: str,
    findings: list[HealthFinding],
    rule_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        findings.append(_error(rule_id, f"{object_id} must be an integer >= 1", object_id, rule_source=rule_source))


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _error(
    rule_id: str,
    message: str,
    object_id: str,
    *,
    rule_source: str = "kernel.default_policy",
) -> HealthFinding:
    return schema_finding(
        rule_id=rule_id,
        message=message,
        object_id=object_id,
        object_type="config",
        suggested_fix_type="fix_config",
        rule_source=rule_source,
    )
