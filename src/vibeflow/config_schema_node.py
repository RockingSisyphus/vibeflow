from __future__ import annotations

from typing import Any, Mapping

from .config_schema_common import (
    _error,
    _non_empty_string,
    _provider_keys,
    _validate_node_configs,
    _validate_positive_int,
    _validate_provider_list,
    _validate_requirement_list,
)
from .graph_config import JOIN_POLICIES, LOOP_NODE_TYPES, LOOP_WHILE_TYPE, SIMILAR_TO_RELATIONSHIPS
from .health_types import HealthFinding
from .node import FLOW_KINDS
from .planned_behavior import PLANNED_BEHAVIOR_BLOCKING, PLANNED_BEHAVIOR_PYTHON_STUB, PLANNED_BEHAVIOR_TRANSPARENT, validate_stub_module_ref
from .visual_style import NODE_STYLE_FIELDS, is_hex_color, is_reserved_system_color, normalize_hex_color

STATUSES = {"planned", "implemented"}

def _validate_node(value: Any, prefix: str, findings: list[HealthFinding]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_OBJECT", f"{prefix} must be an object", prefix))
        return
    status = str(value.get("status", "implemented")).strip()
    _validate_node_identity(value, prefix, findings, status=status)
    _validate_planned_behavior(value, prefix, findings, status=status)
    _validate_node_contract_fields(value, prefix, findings)
    _validate_node_config_fields(value, prefix, findings)
    _validate_node_visual_fields(value, prefix, findings)
    _validate_node_similarity(value, prefix, findings)
    _validate_node_async_fields(value, prefix, findings)
    _validate_node_join_policy(value, prefix, findings)
    _validate_node_loop(value, prefix, findings)

def _validate_node_identity(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    if "name" in value:
        findings.append(_error("CONFIG.SCHEMA.NODE_LEGACY_NAME", f"{prefix}.name is removed; use {prefix}.id", f"{prefix}.name"))
    if "type" in value or "registry_key" in value:
        object_id = f"{prefix}.type" if "type" in value else f"{prefix}.registry_key"
        findings.append(_error("CONFIG.SCHEMA.NODE_LEGACY_TYPE", f"{object_id} is removed; use {prefix}.type_used", object_id))
    if not _non_empty_string(value.get("id")):
        findings.append(_error("CONFIG.SCHEMA.NODE_MISSING_ID", f"{prefix}.id must be a non-empty string", f"{prefix}.id"))
    if status not in STATUSES:
        findings.append(_error("GRAPH.PLANNED.STATUS_INVALID", f"{prefix}.status must be planned or implemented", f"{prefix}.status"))
    if status == "planned" and not _non_empty_string(value.get("flow_kind")):
        findings.append(_error("GRAPH.PLANNED.MISSING_FLOW_KIND", f"{prefix}.flow_kind is required for planned nodes", f"{prefix}.flow_kind"))
    if _non_empty_string(value.get("flow_kind")) and value.get("flow_kind") not in FLOW_KINDS:
        findings.append(_error("NODE.FLOW_KIND.INVALID", f"{prefix}.flow_kind must be one of {sorted(FLOW_KINDS)}", f"{prefix}.flow_kind"))
    if status == "implemented" and _non_empty_string(value.get("flow_kind")):
        findings.append(_error("GRAPH.PLANNED.IMPLEMENTED_HAS_CONFIG_FLOW_KIND", f"{prefix}.flow_kind is only allowed for planned nodes", f"{prefix}.flow_kind"))
    type_used = str(value.get("type_used", "")).strip()
    if type_used.startswith("nodeset."):
        findings.append(_error("CONFIG.SCHEMA.NODE_LEGACY_NODESET_TYPE", f"{prefix}.type_used must use the nodeset type_key directly, not nodeset.<name>", f"{prefix}.type_used"))
    if status != "planned" and not _non_empty_string(value.get("type_used")):
        findings.append(
            _error(
                "CONFIG.SCHEMA.NODE_MISSING_TYPE",
                f"{prefix} must define non-empty string field 'type_used'",
                f"{prefix}.type_used",
            )
        )

def _validate_node_contract_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "requires" in value:
        _validate_requirement_list(value["requires"], f"{prefix}.requires", findings, "CONFIG.SCHEMA.NODE_REQUIRES_LIST")
    if "provides" in value:
        _validate_provider_list(value["provides"], f"{prefix}.provides", findings, "CONFIG.SCHEMA.NODE_PROVIDES_LIST")

def _validate_node_config_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "config" in value and not isinstance(value["config"], Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_CONFIG_OBJECT", f"{prefix}.config must be an object", f"{prefix}.config"))
    if "node_configs" in value:
        _validate_node_configs(value["node_configs"], f"{prefix}.node_configs", findings)
    for field in ("allow_config_override", "override_child_config"):
        if field in value and not isinstance(value[field], bool):
            findings.append(_error("CONFIG.SCHEMA.CONFIG_OVERRIDE_FLAG", f"{prefix}.{field} must be a boolean", f"{prefix}.{field}"))

def _validate_node_visual_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    for removed in ("category", "version"):
        if removed in value:
            findings.append(_error("CONFIG.SCHEMA.NODE_METADATA_REMOVED", f"{prefix}.{removed} is removed; use display_name and description", f"{prefix}.{removed}"))
    for field in ("display_name", "description"):
        if field in value and not isinstance(value[field], str):
            findings.append(_error("CONFIG.SCHEMA.NODE_METADATA_STRING", f"{prefix}.{field} must be a string", f"{prefix}.{field}"))
    if "style" not in value:
        return
    style = value["style"]
    if not isinstance(style, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_STYLE_OBJECT", f"{prefix}.style must be an object", f"{prefix}.style"))
        return
    unknown = sorted(set(str(key) for key in style) - set(NODE_STYLE_FIELDS))
    if unknown:
        findings.append(_error("CONFIG.SCHEMA.NODE_STYLE_FIELD", f"{prefix}.style contains unknown keys: {unknown}", f"{prefix}.style"))
    for field in NODE_STYLE_FIELDS:
        if field not in style:
            continue
        color = style[field]
        if not is_hex_color(color):
            findings.append(_error("CONFIG.SCHEMA.NODE_STYLE_COLOR", f"{prefix}.style.{field} must be a #RRGGBB color", f"{prefix}.style.{field}"))
            continue
        normalized = normalize_hex_color(str(color))
        if is_reserved_system_color(normalized):
            findings.append(
                _error(
                    "CONFIG.SCHEMA.NODE_STYLE_RESERVED_COLOR",
                    f"{prefix}.style.{field} uses reserved VibeFlow system color: {normalized}",
                    f"{prefix}.style.{field}",
                )
            )

def _validate_node_similarity(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "similar_to" not in value:
        return
    similar_to = value["similar_to"]
    if not isinstance(similar_to, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}.similar_to must be an object", f"{prefix}.similar_to"))
        return
    unknown = sorted(set(str(key) for key in similar_to) - {"node", "relationship", "reason"})
    if unknown:
        findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}.similar_to contains unknown keys: {unknown}", f"{prefix}.similar_to"))
    target = similar_to.get("node")
    relationship = similar_to.get("relationship")
    reason = similar_to.get("reason")
    if not _non_empty_string(target):
        findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}.similar_to.node must be a non-empty string", f"{prefix}.similar_to.node"))
    if relationship not in SIMILAR_TO_RELATIONSHIPS:
        findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}.similar_to.relationship must be variant or copy", f"{prefix}.similar_to.relationship"))
    if not _non_empty_string(reason):
        findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}.similar_to.reason must be a non-empty string", f"{prefix}.similar_to.reason"))

def _validate_node_similarity_targets(nodes: list[Any], prefix: str, findings: list[HealthFinding]) -> None:
    ids = {str(node.get("id", "")).strip() for node in nodes if isinstance(node, Mapping) and _non_empty_string(node.get("id"))}
    for index, node in enumerate(nodes):
        if not isinstance(node, Mapping):
            continue
        similar_to = node.get("similar_to")
        if not isinstance(similar_to, Mapping):
            continue
        node_id = str(node.get("id", "")).strip()
        target = str(similar_to.get("node", "")).strip()
        if not node_id or not target:
            continue
        if target == node_id:
            findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}[{index}].similar_to.node cannot reference itself", f"{prefix}[{index}].similar_to.node"))
        elif target not in ids:
            findings.append(_error("CONFIG.SCHEMA.NODE_SIMILAR_TO_INVALID", f"{prefix}[{index}].similar_to.node references unknown node: {target}", f"{prefix}[{index}].similar_to.node"))

def _validate_node_async_fields(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    mode = value.get("async", "")
    if mode not in {"", "detached", "result_key"}:
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC", f"{prefix}.async must be 'detached' or 'result_key'", f"{prefix}.async"))
    result_key = value.get("result_key", "")
    if mode == "result_key" and not _non_empty_string(result_key):
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY", f"{prefix}.result_key is required when async is 'result_key'", f"{prefix}.result_key"))
    if mode == "result_key" and _non_empty_string(result_key) and str(result_key).strip() not in _provider_keys(value.get("provides", [])):
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY", f"{prefix}.result_key must be declared in provides", f"{prefix}.result_key"))
    if mode != "result_key" and result_key:
        findings.append(_error("CONFIG.SCHEMA.NODE_ASYNC_RESULT_KEY", f"{prefix}.result_key requires async='result_key'", f"{prefix}.result_key"))

def _validate_node_join_policy(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    if "join_policy" not in value:
        return
    if value["join_policy"] not in JOIN_POLICIES:
        findings.append(_error("CONFIG.SCHEMA.NODE_JOIN_POLICY", f"{prefix}.join_policy must be one of {sorted(JOIN_POLICIES)}", f"{prefix}.join_policy"))

def _validate_node_loop(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding]) -> None:
    node_type = str(value.get("type_used", "")).strip()
    if node_type not in LOOP_NODE_TYPES:
        if "loop" in value:
            findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop is only allowed on VibeFlow loop nodes", f"{prefix}.loop"))
        return
    loop = value.get("loop")
    if not isinstance(loop, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop must be an object", f"{prefix}.loop"))
        return
    if not _non_empty_string(loop.get("body")):
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop.body must be a non-empty nodeset name", f"{prefix}.loop.body"))
    elif str(loop.get("body", "")).strip().startswith("nodeset."):
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop.body must use the nodeset type_key directly, not nodeset.<name>", f"{prefix}.loop.body"))
    unknown = sorted(set(str(key) for key in loop) - {"body", "max_iterations", "stop_after", "stop_when", "carry", "collect", "outputs"})
    if unknown:
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop contains unsupported loop keys: {unknown}", f"{prefix}.loop"))
    if "max_iterations" in loop:
        _validate_positive_int(loop["max_iterations"], f"{prefix}.loop.max_iterations", findings, "CONFIG.SCHEMA.NODE_LOOP_INVALID")
    if node_type == LOOP_WHILE_TYPE:
        has_stop_after = "stop_after" in loop
        has_stop_when = "stop_when" in loop
        if has_stop_after == has_stop_when:
            findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop must declare exactly one of stop_after or stop_when", f"{prefix}.loop"))
        if has_stop_after:
            _validate_positive_int(loop.get("stop_after"), f"{prefix}.loop.stop_after", findings, "CONFIG.SCHEMA.NODE_LOOP_INVALID")
            max_iterations = loop.get("max_iterations", 1000)
            if isinstance(loop.get("stop_after"), int) and not isinstance(loop.get("stop_after"), bool) and isinstance(max_iterations, int) and not isinstance(max_iterations, bool):
                if loop["stop_after"] > max_iterations:
                    findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop.stop_after must be <= max_iterations", f"{prefix}.loop.stop_after"))
        if has_stop_when:
            _validate_loop_mapping(loop.get("stop_when"), f"{prefix}.loop.stop_when", findings, required_fields=("from",))
            if isinstance(loop.get("stop_when"), Mapping) and "equals" in loop["stop_when"] and not isinstance(loop["stop_when"]["equals"], bool):
                findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.loop.stop_when.equals must be a boolean", f"{prefix}.loop.stop_when.equals"))
    for field, required in (("carry", ("from", "as", "update")), ("collect", ("from", "as")), ("outputs", ("from", "as"))):
        if field in loop:
            _validate_loop_list(loop[field], f"{prefix}.loop.{field}", findings, required_fields=required)

def _validate_loop_mapping(value: Any, prefix: str, findings: list[HealthFinding], *, required_fields: tuple[str, ...]) -> None:
    if not isinstance(value, Mapping):
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix} must be an object", prefix))
        return
    for field in required_fields:
        if not _non_empty_string(value.get(field)):
            findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}.{field} must be a non-empty string", f"{prefix}.{field}"))

def _validate_loop_list(value: Any, prefix: str, findings: list[HealthFinding], *, required_fields: tuple[str, ...]) -> None:
    if not isinstance(value, list):
        findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix} must be a list", prefix))
        return
    for index, item in enumerate(value):
        _validate_loop_mapping(item, f"{prefix}[{index}]", findings, required_fields=required_fields)
        if isinstance(item, Mapping) and "mode" in item and item["mode"] != "all":
            findings.append(_error("CONFIG.SCHEMA.NODE_LOOP_INVALID", f"{prefix}[{index}].mode must be 'all'", f"{prefix}[{index}].mode"))

def _validate_planned_behavior(value: Mapping[str, Any], prefix: str, findings: list[HealthFinding], *, status: str) -> None:
    if "planned_behavior" not in value:
        return
    if status != "planned":
        findings.append(_error("GRAPH.PLANNED.BEHAVIOR_IMPLEMENTED", f"{prefix}.planned_behavior is only allowed for planned nodes/nodesets", f"{prefix}.planned_behavior"))
        return
    behavior = value["planned_behavior"]
    if isinstance(behavior, str):
        if behavior not in {PLANNED_BEHAVIOR_BLOCKING, PLANNED_BEHAVIOR_TRANSPARENT}:
            findings.append(_error("GRAPH.PLANNED.BEHAVIOR_INVALID", f"{prefix}.planned_behavior must be blocking, transparent, or a python_stub object", f"{prefix}.planned_behavior"))
        return
    if not isinstance(behavior, Mapping):
        findings.append(_error("GRAPH.PLANNED.BEHAVIOR_INVALID", f"{prefix}.planned_behavior must be a string or object", f"{prefix}.planned_behavior"))
        return
    kind = str(behavior.get("kind", "")).strip()
    if kind != PLANNED_BEHAVIOR_PYTHON_STUB:
        findings.append(_error("GRAPH.PLANNED.BEHAVIOR_INVALID", f"{prefix}.planned_behavior.kind must be python_stub", f"{prefix}.planned_behavior.kind"))
        return
    stub_module = behavior.get("stub_module")
    if not _non_empty_string(stub_module):
        findings.append(_error("GRAPH.PLANNED.STUB_MODULE", f"{prefix}.planned_behavior.stub_module is required", f"{prefix}.planned_behavior.stub_module"))
        return
    path_error = validate_stub_module_ref(str(stub_module))
    if path_error:
        findings.append(_error("GRAPH.PLANNED.STUB_MODULE", f"{prefix}.planned_behavior.stub_module {path_error}", f"{prefix}.planned_behavior.stub_module"))
