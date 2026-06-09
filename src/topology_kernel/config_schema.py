from __future__ import annotations

from typing import Any, Mapping

from .health_types import HealthFinding


def collect_config_schema_findings(config: Mapping[str, Any]) -> tuple[HealthFinding, ...]:
    findings: list[HealthFinding] = []
    pipeline = config.get("pipeline", config)
    if not isinstance(pipeline, Mapping):
        findings.append(_error("CONFIG.SCHEMA.PIPELINE_OBJECT", "pipeline must be an object", "pipeline"))
        return tuple(findings)
    _validate_pipeline(pipeline, "pipeline", findings)
    if "nodesets" in config:
        _validate_nodesets(config["nodesets"], findings)
    if "boundary" in config:
        _validate_boundary(config["boundary"], findings)
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
        loops = value["loops"]
        if not isinstance(loops, list):
            findings.append(_error("CONFIG.SCHEMA.LOOPS_LIST", f"{prefix}.loops must be a list", f"{prefix}.loops"))
        else:
            for index, loop in enumerate(loops):
                _validate_loop(loop, f"{prefix}.loops[{index}]", findings)


def _validate_node(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_OBJECT", f"{prefix} must be an object", prefix))
        return
    if not _non_empty_string(value.get("name")):
        findings.append(_error("CONFIG.SCHEMA.NODE_MISSING_NAME", f"{prefix}.name must be a non-empty string", f"{prefix}.name"))
    if not (_non_empty_string(value.get("type")) or _non_empty_string(value.get("registry_key"))):
        findings.append(
            _error(
                "CONFIG.SCHEMA.NODE_MISSING_TYPE",
                f"{prefix} must define non-empty string field 'type' or 'registry_key'",
                f"{prefix}.type",
            )
        )
    for field in ("requires", "provides"):
        if field in value:
            _validate_string_list(value[field], f"{prefix}.{field}", findings, f"CONFIG.SCHEMA.NODE_{field.upper()}_LIST")


def _validate_edge(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if isinstance(value, list):
        if len(value) != 2 or not all(_non_empty_string(item) for item in value):
            findings.append(_error("CONFIG.SCHEMA.EDGE_PAIR", f"{prefix} must be [from, to] with non-empty strings", prefix))
        return
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.EDGE_OBJECT", f"{prefix} must be [from, to] or an object", prefix))
        return
    if not (_non_empty_string(value.get("from")) or _non_empty_string(value.get("source"))):
        findings.append(_error("CONFIG.SCHEMA.EDGE_FROM", f"{prefix}.from must be a non-empty string", f"{prefix}.from"))
    if not (_non_empty_string(value.get("to")) or _non_empty_string(value.get("target"))):
        findings.append(_error("CONFIG.SCHEMA.EDGE_TO", f"{prefix}.to must be a non-empty string", f"{prefix}.to"))
    if "max_executions" in value:
        _validate_positive_int(value["max_executions"], f"{prefix}.max_executions", findings, "CONFIG.SCHEMA.EDGE_MAX_EXECUTIONS")


def _validate_loop(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.LOOP_OBJECT", f"{prefix} must be an object", prefix))
        return
    if not _non_empty_string(value.get("name")):
        findings.append(_error("CONFIG.SCHEMA.LOOP_MISSING_NAME", f"{prefix}.name must be a non-empty string", f"{prefix}.name"))
    edges = value.get("edges")
    if not isinstance(edges, list) or not edges:
        findings.append(_error("CONFIG.SCHEMA.LOOP_EDGES", f"{prefix}.edges must be a non-empty list", f"{prefix}.edges"))
    else:
        for index, edge in enumerate(edges):
            if not (isinstance(edge, list) and len(edge) == 2 and all(_non_empty_string(item) for item in edge)):
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.LOOP_EDGE_PAIR",
                        f"{prefix}.edges[{index}] must be [from, to] with non-empty strings",
                        f"{prefix}.edges[{index}]",
                    )
                )
    if "max_iterations" not in value and "max_executions" not in value:
        findings.append(
            _error(
                "CONFIG.SCHEMA.LOOP_MAX_ITERATIONS",
                f"{prefix} must define max_iterations or max_executions",
                f"{prefix}.max_iterations",
            )
        )
    for field in ("max_iterations", "max_executions"):
        if field in value:
            _validate_positive_int(value[field], f"{prefix}.{field}", findings, "CONFIG.SCHEMA.LOOP_MAX_ITERATIONS")


def _validate_nodesets(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.NODESETS_LIST", "nodesets must be a list", "nodesets"))
        return
    for index, item in enumerate(value):
        prefix = f"nodesets[{index}]"
        if not isinstance(item, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODESET_OBJECT", f"{prefix} must be an object", prefix))
            continue
        if not _non_empty_string(item.get("name")):
            findings.append(_error("CONFIG.SCHEMA.NODESET_MISSING_NAME", f"{prefix}.name must be a non-empty string", f"{prefix}.name"))
        for field in ("display_name", "category", "description", "version", "purity"):
            if not _non_empty_string(item.get(field)):
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.NODESET_METADATA",
                        f"{prefix}.{field} must be a non-empty string",
                        f"{prefix}.{field}",
                    )
                )
        if item.get("purity") not in {None, "pure"}:
            findings.append(_error("CONFIG.SCHEMA.NODESET_PURITY", f"{prefix}.purity must be 'pure'", f"{prefix}.purity"))
        for required_field in ("requires", "provides", "exports"):
            if required_field not in item:
                findings.append(
                    _error(
                        "CONFIG.SCHEMA.NODESET_CONTRACT",
                        f"{prefix}.{required_field} must be declared",
                        f"{prefix}.{required_field}",
                    )
                )
        pipeline = item.get("pipeline")
        if not isinstance(pipeline, Mapping):
            findings.append(_error("CONFIG.SCHEMA.NODESET_PIPELINE", f"{prefix}.pipeline must be an object", f"{prefix}.pipeline"))
        else:
            _validate_pipeline(pipeline, f"{prefix}.pipeline", findings)
        for field in ("requires", "provides", "exports"):
            if field in item:
                _validate_string_list(item[field], f"{prefix}.{field}", findings, "CONFIG.SCHEMA.NODESET_CONTRACT_LIST")


def _validate_boundary(value: Any, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.BOUNDARY_OBJECT", "boundary must be an object", "boundary"))
        return
    if not _non_empty_string(value.get("type")):
        findings.append(_error("CONFIG.SCHEMA.BOUNDARY_TYPE", "boundary.type must be a non-empty string", "boundary.type"))
    if "config" in value and not isinstance(value["config"], Mapping):
        findings.append(_error("CONFIG.SCHEMA.BOUNDARY_CONFIG", "boundary.config must be an object", "boundary.config"))
    for field in ("consumes", "provides", "allowed_paths"):
        if field in value:
            _validate_string_list(value[field], f"boundary.{field}", findings, "CONFIG.SCHEMA.BOUNDARY_STRING_LIST")
    for index, key in enumerate(value.get("consumes", []) if isinstance(value.get("consumes", []), list) else []):
        if isinstance(key, str) and not (key.startswith("effects.") or key.startswith("outbox.")):
            findings.append(
                _error(
                    "CONFIG.SCHEMA.BOUNDARY_CONSUMES_KEY",
                    "boundary.consumes keys must start with effects. or outbox.",
                    f"boundary.consumes[{index}]",
                )
            )
    for index, key in enumerate(value.get("provides", []) if isinstance(value.get("provides", []), list) else []):
        if isinstance(key, str) and not key.startswith("io."):
            findings.append(
                _error(
                    "CONFIG.SCHEMA.BOUNDARY_PROVIDES_KEY",
                    "boundary.provides keys must start with io.",
                    f"boundary.provides[{index}]",
                )
            )


def _validate_policy(value: Any, prefix: str, findings: list[HealthFinding], *, rule_source: str) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.POLICY_ROOT", f"{prefix} must be an object", prefix, rule_source=rule_source))
        return
    if "node_source" in value:
        _validate_policy_section(value["node_source"], f"{prefix}.node_source", findings, rule_source=rule_source)
        for field in ("max_lines", "max_bytes", "warn_lines", "warn_bytes"):
            if isinstance(value["node_source"], Mapping) and field in value["node_source"]:
                _validate_positive_int(
                    value["node_source"][field],
                    f"{prefix}.node_source.{field}",
                    findings,
                    "CONFIG.SCHEMA.POLICY_POSITIVE_INT",
                    rule_source=rule_source,
                )
    if "complexity" in value:
        _validate_policy_section(value["complexity"], f"{prefix}.complexity", findings, rule_source=rule_source)
        for field in ("max_functions", "max_branches", "max_nesting_depth", "max_params", "max_contract_keys"):
            if isinstance(value["complexity"], Mapping) and field in value["complexity"] and value["complexity"][field] is not None:
                _validate_positive_int(
                    value["complexity"][field],
                    f"{prefix}.complexity.{field}",
                    findings,
                    "CONFIG.SCHEMA.POLICY_POSITIVE_INT",
                    rule_source=rule_source,
                )
    if "imports" in value:
        _validate_policy_section(value["imports"], f"{prefix}.imports", findings, rule_source=rule_source)
        if isinstance(value["imports"], Mapping):
            for field in ("allowed_roots", "banned_roots"):
                if field in value["imports"]:
                    _validate_string_list(
                        value["imports"][field],
                        f"{prefix}.imports.{field}",
                        findings,
                        "CONFIG.SCHEMA.POLICY_STRING_LIST",
                        rule_source=rule_source,
                    )
    if "base_lib" in value:
        _validate_policy_section(value["base_lib"], f"{prefix}.base_lib", findings, rule_source=rule_source)
        if isinstance(value["base_lib"], Mapping):
            for field in ("allowed_paths", "allowed_modules", "banned_modules"):
                if field in value["base_lib"]:
                    _validate_string_list(
                        value["base_lib"][field],
                        f"{prefix}.base_lib.{field}",
                        findings,
                        "CONFIG.SCHEMA.POLICY_STRING_LIST",
                        rule_source=rule_source,
                    )
    if "maintainability" in value:
        _validate_policy_section(value["maintainability"], f"{prefix}.maintainability", findings, rule_source=rule_source)
        for field in ("warn_call_chain_length", "max_call_chain_length", "warn_dependency_chain_length", "max_dependency_chain_length"):
            if isinstance(value["maintainability"], Mapping) and field in value["maintainability"]:
                _validate_positive_int(
                    value["maintainability"][field],
                    f"{prefix}.maintainability.{field}",
                    findings,
                    "CONFIG.SCHEMA.POLICY_POSITIVE_INT",
                    rule_source=rule_source,
                )
    if "rules" in value:
        _validate_policy_section(value["rules"], f"{prefix}.rules", findings, rule_source=rule_source)
        if isinstance(value["rules"], Mapping):
            for field in ("downgrades", "exemptions"):
                if field in value["rules"]:
                    _validate_rule_entries(value["rules"][field], f"{prefix}.rules.{field}", findings, rule_source=rule_source)


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
        if item.get("type", "policy") not in {"policy", "compiler", "runtime", "boundary"}:
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_TYPE", f"{prefix}.type must be policy, compiler, runtime, or boundary", f"{prefix}.type"))
        if "priority" in item:
            _validate_positive_int(item["priority"], f"{prefix}.priority", findings, "CONFIG.SCHEMA.PLUGIN_PRIORITY")
        if item.get("conflict", "error") not in {"error", "replace"}:
            findings.append(_error("CONFIG.SCHEMA.PLUGIN_CONFLICT", f"{prefix}.conflict must be error or replace", f"{prefix}.conflict"))


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
    return HealthFinding(
        rule_id=rule_id,
        severity="error",
        object_type="config",
        object_id=object_id,
        failure_layer="schema",
        message=message,
        suggested_fix_type="fix_config",
        rule_source=rule_source,
    )
