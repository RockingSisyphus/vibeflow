"""Actual public configuration diagnostics in both kernels; no implementation import."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path


NODE = {"id": "work", "type_used": "parity.work", "display_name": "Work", "description": "One unit of work."}


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    from vibeflow.tooling.project.config_schema import collect_config_schema_findings

    observations = []

    def emit(name, data, codes=(), *, family="config.schema", classification="preserved", message=""):
        try:
            findings = collect_config_schema_findings(data)
            actual = {"status": "FAIL" if any(row.severity == "error" for row in findings) else "CONCERNS" if findings else "PASS",
                      "codes": [{"code": row.rule_id, "severity": row.severity} for row in findings],
                      "positions": [dict(row.source_location) for row in findings], "metrics": {},
                      "message": "; ".join(row.message for row in findings)}
        except Exception as error:
            actual = {"status": "ERROR", "codes": [], "positions": [], "metrics": {}, "message": repr(error)}
        observations.append({"id": "tooling." + name, "title": name, "family": family,
            "classification": classification, "expected": {"should_accept": not codes,
                "codes": [{"code": code, "severity": "error"} for code in codes], "exact_codes": True,
                **({"message_contains": message} if message else {})}, "actual": actual,
            "evidence": "public collect_config_schema_findings; tooling/project/{config_schema,schema_node,schema_common}.py",
            "notes": "Observe the public configuration checker, independently of Rule selection and actual compilation."})

    def pipeline(**updates):
        return {"pipeline": {"nodes": [deepcopy(NODE)], "edges": [], **updates}}

    def changed_node(**updates):
        return pipeline(nodes=[{**NODE, **updates}])

    emit("normal", pipeline())
    for name, config, code in [
        ("pipeline_object", {"pipeline": []}, "PIPELINE_OBJECT"),
        ("nodes_list", pipeline(nodes={}), "NODES_LIST"),
        ("nodes_empty", pipeline(nodes=[]), "NODES_NON_EMPTY"),
        ("node_object", pipeline(nodes=[None]), "NODE_OBJECT"),
        ("node_id", changed_node(id=""), "NODE_MISSING_ID"),
        ("node_type", changed_node(type_used=""), "NODE_MISSING_TYPE"),
        ("legacy_name", changed_node(name="old"), "NODE_LEGACY_NAME"),
        ("legacy_type", changed_node(type="old"), "NODE_LEGACY_TYPE"),
        ("legacy_nodeset_type", changed_node(type_used="nodeset.old"), "NODE_LEGACY_NODESET_TYPE"),
        ("node_title", changed_node(display_name=""), "NODE_METADATA_REQUIRED"),
        ("node_description", changed_node(description=""), "NODE_METADATA_REQUIRED"),
        ("node_config", changed_node(config=[]), "NODE_CONFIG_OBJECT"),
        ("node_configs", changed_node(node_configs=[]), "NODE_CONFIGS_OBJECT"),
        ("config_override", changed_node(allow_config_override="yes"), "CONFIG_OVERRIDE_FLAG"),
        ("duplicate_contract", changed_node(requires=[]), "NODE_CONTRACT_DUPLICATE"),
        ("style_object", changed_node(style="blue"), "NODE_STYLE_OBJECT"),
        ("style_color", changed_node(style={"fill": "blue"}), "NODE_STYLE_COLOR"),
        ("style_unknown", changed_node(style={"unknown": "#123456"}), "NODE_STYLE_FIELD"),
        ("similar_invalid", changed_node(similar_to=[]), "NODE_SIMILAR_TO_INVALID"),
        ("similar_unknown", changed_node(similar_to={"node": "missing", "relationship": "copy", "reason": "Shared algorithm."}), "NODE_SIMILAR_TO_INVALID"),
        ("join_policy", changed_node(join_policy="sometimes"), "NODE_JOIN_POLICY"),
        ("loop_on_process", changed_node(loop={}), "NODE_LOOP_INVALID"),
        ("edges_list", pipeline(edges={}), "EDGES_LIST"),
        ("edge_object", pipeline(edges=[1]), "EDGE_OBJECT"),
        ("edge_pair", pipeline(edges=[["work"]]), "EDGE_PAIR"),
        ("edge_source", pipeline(edges=[{"to": "work"}]), "EDGE_FROM"),
        ("edge_target", pipeline(edges=[{"from": "work"}]), "EDGE_TO"),
        ("edge_condition", pipeline(edges=[{"from": "work", "to": "work", "when": 1}]), "EDGE_WHEN"),
        ("edge_schedule", pipeline(edges=[{"from": "work", "to": "work", "schedule": 1}]), "EDGE_SCHEDULE"),
        ("edge_transfer", pipeline(edges=[{"from": "work", "to": "work", "transfer": "yes"}]), "EDGE_TRANSFER"),
        ("edge_no_role", pipeline(edges=[{"from": "work", "to": "work", "schedule": False, "transfer": False}]), "EDGE_ROLES"),
        ("entry_mode", pipeline(entry_mode="parallel"), "ENTRY_MODE"),
        ("max_steps_bool", pipeline(max_steps=True), "MAX_STEPS"),
        ("max_steps_zero", pipeline(max_steps=0), "MAX_STEPS"),
    ]:
        emit(name, config, ("CONFIG.SCHEMA." + code,))
    for name, value, code in [("object", [], "OBJECT"), ("unknown", {"key": "resource", "ttl": 1}, "FIELD"),
                              ("missing", {}, "KEY"), ("reserved", {"key": "vibeflow.internal"}, "RESERVED")]:
        emit("lock." + name, pipeline(execution_lock=value), ("CONFIG.SCHEMA.EXECUTION_LOCK_" + code,))
    emit("lock.normal", pipeline(execution_lock={"key": "parity.resource"}))
    emit("roles.normal", pipeline(edges=[{"from": "work", "to": "work", "schedule": True, "transfer": False}]))
    for name, extra, code in [
        ("inline_nodesets", {"nodesets": []}, "CONFIG.NODESETS.INLINE_REMOVED"),
        ("removed_boundary", {"boundary": {}}, "CONFIG.BOUNDARY.REMOVED"),
        ("removed_loops", {"pipeline": {**pipeline()["pipeline"], "loops": []}}, "CONFIG.LOOPS.REMOVED"),
        ("base_object", {"base_lib": []}, "CONFIG.SCHEMA.BASE_LIB"),
        ("base_paths", {"base_lib": {"paths": [""]}}, "CONFIG.SCHEMA.BASE_LIB_PATHS"),
        ("base_modules", {"base_lib": {"modules": {}}}, "CONFIG.SCHEMA.BASE_LIB_MODULES"),
        ("base_module", {"base_lib": {"modules": [""]}}, "CONFIG.SCHEMA.BASE_LIB_MODULE"),
        ("global_object", {"global_config": []}, "CONFIG.SCHEMA.GLOBAL_CONFIG"),
        ("global_values", {"global_config": {"values": []}}, "CONFIG.SCHEMA.GLOBAL_CONFIG_VALUES"),
        ("plugin_list", {"plugins": {}}, "CONFIG.SCHEMA.PLUGINS_LIST"),
        ("plugin_object", {"plugins": [1]}, "CONFIG.SCHEMA.PLUGIN_OBJECT"),
        ("host_list", {"host_extensions": {}}, "CONFIG.SCHEMA.HOST_EXTENSIONS_LIST"),
        ("host_id", {"host_extensions": [""]}, "CONFIG.SCHEMA.HOST_EXTENSION_ID"),
        ("host_enabled", {"host_extensions": [{"id": "parity.host", "enabled": "yes"}]}, "CONFIG.SCHEMA.HOST_EXTENSION_ENABLED"),
        ("host_duplicate", {"host_extensions": ["parity.host", "parity.host"]}, "CONFIG.SCHEMA.HOST_EXTENSION_DUPLICATE"),
    ]:
        if variant == "current" and name == "plugin_object":
            code = "PLUGIN.SELECTION.MIGRATION"
        emit(name, {**pipeline(), **extra}, (code,), family="config.resources", classification="approved_change" if name == "plugin_object" and variant == "current" else "preserved")
    emit("resources.normal", {**pipeline(), "plugins": ([{"source":{"kind":"file","ref":"plugin.py"}}] if variant == "current" else ["parity.plugin"]), "host_extensions": ["parity.host"],
                             "base_lib": {"paths": ["support"], "modules": ["support.math"]}, "global_config": {"values": {"size": 1}}}, family="config.resources")
    io = {**NODE, "type_used": "vibeflow.io", "requires": [],
          "provides": [{"key": "value", "type": "parity.value", "display_name": "Value"}], "io": {"operation": "receive"}}
    emit("system_io.normal", pipeline(nodes=[io]), family="config.contract")
    for field, value, code in [("requires", {}, "NODE_REQUIRES_LIST"), ("provides", [{}], "NODE_PROVIDES_LIST")]:
        expected = ("CONFIG.SCHEMA." + code,)
        if field == "requires":
            expected += ("CONFIG.SCHEMA.NODE_IO_CONTRACT",)
        emit("system_io." + field, pipeline(nodes=[{**io, field: value}]), expected, family="config.contract")
    emit("system_io.receive_empty", pipeline(nodes=[{**io, "provides": []}]), ("CONFIG.SCHEMA.NODE_IO_CONTRACT",), family="config.contract")
    send = {**io, "io": {"operation": "send"}, "provides": [],
            "requires": [{"type": "parity.value", "cardinality": "exactly_one", "display_name": "Value"}]}
    emit("system_io.send_normal", pipeline(nodes=[send]), family="config.contract")
    emit("system_io.send_optional", pipeline(nodes=[{**send, "requires": [{**send["requires"][0], "cardinality": "optional_one"}]}]),
         ("CONFIG.SCHEMA.NODE_IO_CONTRACT",), family="config.contract")
    planned = {**NODE, "status": "planned", "flow_kind": "process", "requires": [], "provides": []}
    emit("planned.normal", pipeline(nodes=[planned]), family="config.planned")
    emit("planned.invalid_status", changed_node(status="unfinished"), ("GRAPH.PLANNED.STATUS_INVALID",), family="config.planned")
    missing_kind = {key: value for key, value in planned.items() if key != "flow_kind"}
    emit("planned.missing_kind", pipeline(nodes=[missing_kind]), ("GRAPH.PLANNED.MISSING_FLOW_KIND",), family="config.planned")
    emit("implemented.config_kind", changed_node(flow_kind="process"), ("GRAPH.PLANNED.IMPLEMENTED_HAS_CONFIG_FLOW_KIND",), family="config.planned")
    if variant == "current":
        emit("rulesets.invalid", {**pipeline(), "rulesets": "vibeflow.workflow"}, ("CONFIG.SCHEMA.RULESETS",), classification="new_feature")
        emit("rulesets.empty", {**pipeline(), "rulesets": []}, classification="new_feature")
    import importlib.util
    for filename in ("schema_variants.py", "descriptor_variants.py"):
        spec = importlib.util.spec_from_file_location("tooling_" + filename[:-3], Path(__file__).with_name(filename))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        observations.extend(module.run_cases(work_root, variant, toolchain_root))
    return observations
