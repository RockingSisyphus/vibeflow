"""Remaining public schema branches, including warning and valid counterparts."""

from copy import deepcopy
from pathlib import Path


NODE = {"id": "work", "type_used": "parity.work", "display_name": "Work", "description": "One work unit."}
REQUIREMENT = {"type": "parity.input", "cardinality": "exactly_one", "display_name": "Input"}
PROVIDER = {"key": "value", "type": "parity.output", "display_name": "Output"}


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    from vibeflow.tooling.project.config_schema import collect_config_schema_findings

    rows = []

    def emit(name, data, codes=(), *, severity="error", message="", classification="preserved", baseline_codes=None):
        expected_codes = baseline_codes if variant == "baseline" and baseline_codes is not None else codes
        if variant == "current" and (name.startswith("async.") or name=="io.async"):
            expected_codes=("GRAPH.ASYNC.MIGRATION",)
            classification="approved_change"
        if variant == "current" and name.startswith("io."):
            expected_codes, classification = ("GRAPH.IO.MIGRATION",), "approved_change"
        try:
            findings = collect_config_schema_findings(data)
            actual = {"status": "FAIL" if any(f.severity == "error" for f in findings) else "CONCERNS" if findings else "PASS",
                      "codes": [{"code": f.rule_id, "severity": f.severity} for f in findings],
                      "positions": [dict(f.source_location) for f in findings], "metrics": {},
                      "message": "; ".join(f.message for f in findings)}
        except Exception as error:
            actual = {"status": "ERROR", "codes": [], "positions": [], "metrics": {}, "message": repr(error)}
        rows.append({"id": "tooling.variant." + name, "title": name, "family": "config.schema.variants", "classification": classification,
                     "expected": {"should_accept": not expected_codes or severity != "error", "exact_codes": True,
                                  "codes": [{"code": code, "severity": severity} for code in expected_codes],
                                  **({"message_contains": message} if message else {})}, "actual": actual,
                     "evidence": "Public collect_config_schema_findings; baseline/current config_schema.py and schema_node.py",
                     "notes": "Valid controls and isolated invalid branches; warnings must remain observable."})

    def pipeline(**fields):
        return {"pipeline": {"nodes": [deepcopy(NODE)], "edges": [], **fields}}

    def node(**fields):
        return pipeline(nodes=[{**NODE, **fields}])

    def schema(name, data, suffix, **kwargs):
        emit(name, data, ("CONFIG.SCHEMA." + suffix,), **kwargs)

    for field in ("node_configs",):
        schema(field + ".key", node(**{field: {"": {}}}), "NODE_CONFIGS_KEY")
        schema(field + ".item", node(**{field: {"child": []}}), "NODE_CONFIG_OBJECT")
        emit(field + ".normal", node(**{field: {"child": {"scale": 2}}}))
    schema("override_child_config", node(override_child_config=1), "CONFIG_OVERRIDE_FLAG")
    schema("legacy.registry_key", node(registry_key="old"), "NODE_LEGACY_TYPE")
    schema("node.lock.reserved", node(execution_lock={"key": "vibeflow.node"}), "EXECUTION_LOCK_RESERVED")
    emit("node.lock.normal", node(execution_lock={"key": "parity.node"}))
    for field in ("category", "version"):
        schema("removed.node." + field, node(**{field: "legacy"}), "NODE_METADATA_REMOVED")
    for field in ("fill", "stroke", "text"):
        schema("style." + field + ".reserved", node(style={field: "#DC2626"}), "NODE_STYLE_RESERVED_COLOR")
        emit("style." + field + ".hex", node(style={field: "#abcdef"}))
    similar = {"node": "other", "relationship": "variant", "reason": "Different threshold."}
    for field, value in (("relationship", "derived"), ("reason", ""), ("node", "")):
        schema("similar." + field, node(similar_to={**similar, field: value}), "NODE_SIMILAR_TO_INVALID")
    schema("similar.unknown_field", node(similar_to={**similar, "extra": True}), "NODE_SIMILAR_TO_INVALID")
    schema("similar.self", node(similar_to={**similar, "node": "work"}), "NODE_SIMILAR_TO_INVALID")
    emit("similar.normal", pipeline(nodes=[{**NODE, "similar_to": similar}, {**NODE, "id": "other"}]))
    for mode in ("detached", "result_key"):
        emit("async.normal." + mode, node(**{"async": mode, **({"result_key": "result"} if mode == "result_key" else {})}))
    schema("async.invalid", node(**{"async": "background"}), "NODE_ASYNC")
    schema("async.result_missing", node(**{"async": "result_key"}), "NODE_ASYNC_RESULT_KEY")
    schema("async.result_without_mode", node(result_key="result"), "NODE_ASYNC_RESULT_KEY")
    planned = {**NODE, "status": "planned", "flow_kind": "process", "requires": [REQUIREMENT], "provides": [PROVIDER]}
    schema("async.result_not_provided", pipeline(nodes=[{**planned, "async": "result_key", "result_key": "other"}]), "NODE_ASYNC_RESULT_KEY")
    emit("async.result_provided", pipeline(nodes=[{**planned, "async": "result_key", "result_key": "value"}]))
    for field, item, code in (("requires", REQUIREMENT, "NODE_REQUIRES_LIST"), ("provides", PROVIDER, "NODE_PROVIDES_LIST")):
        for label, value in (("non_object", [1]), ("unknown", [{**item, "extra": True}]), ("duplicate", [item, item])):
            schema("contract." + field + "." + label, pipeline(nodes=[{**planned, field: value}]), code)
        for key in item:
            schema("contract." + field + ".missing_" + key, pipeline(nodes=[{**planned, field: [{k: v for k, v in item.items() if k != key}]}]), code)
    for cardinality in ("optional_one", "all"):
        emit("contract.cardinality." + cardinality, pipeline(nodes=[{**planned, "requires": [{**REQUIREMENT, "cardinality": cardinality}]}]))
    for field in ("requires", "provides"):
        schema("contract.planned.missing_" + field, pipeline(nodes=[{k: v for k, v in planned.items() if k != field}]), "NODE_CONTRACT_REQUIRED")
    for behavior in ("blocking", "transparent"):
        emit("planned.behavior." + behavior, pipeline(nodes=[{**planned, "planned_behavior": behavior}]))
    for label, behavior, code in (("invalid_string", "noop", "BEHAVIOR_INVALID"), ("invalid_object", [], "BEHAVIOR_INVALID"),
                                  ("invalid_kind", {"kind": "javascript_stub"}, "BEHAVIOR_INVALID"),
                                  ("stub_missing", {"kind": "python_stub"}, "STUB_MODULE"),
                                  ("stub_escape", {"kind": "python_stub", "stub_module": "../escape.py"}, "STUB_MODULE")):
        emit("planned." + label, pipeline(nodes=[{**planned, "planned_behavior": behavior}]), ("GRAPH.PLANNED." + code,))
    emit("planned.behavior.implemented", node(planned_behavior="blocking"), ("GRAPH.PLANNED.BEHAVIOR_IMPLEMENTED",))
    emit("planned.stub.normal", pipeline(nodes=[{**planned, "planned_behavior": {"kind": "python_stub", "stub_module": "stubs/work.py"}}]))
    for label, path in (("absolute", "/stubs/work.py"), ("drive", "C:/stubs/work.py"),
                        ("hidden", "stubs/.work.py"), ("directory", "nodes/work.py"), ("suffix", "stubs/work.js")):
        emit("planned.stub." + label, pipeline(nodes=[{**planned, "planned_behavior": {"kind": "python_stub", "stub_module": path}}]), ("GRAPH.PLANNED.STUB_MODULE",))
    for field in ("max", "max_executions", "loop"):
        emit("edge.removed." + field, pipeline(edges=[{"from": "work", "to": "work", field: 1}]),
             ("CONFIG.LOOPS.REMOVED" if field == "loop" else "CONFIG.LOOP_LIMITS.REMOVED",))
    emit("edge.alias.normal", pipeline(edges=[{"source": "work", "target": "work"}]))
    emit("max_steps.one", pipeline(max_steps=1))
    loop = {**NODE, "type_used": "vibeflow.loop.while", "requires": [], "provides": [], "loop": {"body": "parity.body", "max_iterations": 2}}
    for label, value in (("object", []), ("body", {"body": ""}), ("legacy_body", {"body": "nodeset.old"}),
                         ("unknown", {"body": "parity.body", "extra": 1}),
                         ("max_bool", {"body": "parity.body", "max_iterations": True}),
                         ("stop_after", {"body": "parity.body", "stop_after": 0}),
                         ("stop_when", {"body": "parity.body", "stop_when": {"from": "value", "equals": 1}})):
        schema("loop." + label, pipeline(nodes=[{**loop, "loop": value}]), "NODE_LOOP_INVALID")
    emit("loop.normal", pipeline(nodes=[loop]))
    emit("loop.permanent", pipeline(nodes=[{**loop, "loop": {"body": "parity.body", "max_iterations": None}}]), ("CONFIG.LOOP.PERMANENT",), severity="warning")
    emit("loop.unreachable_stop", pipeline(nodes=[{**loop, "loop": {**loop["loop"], "stop_after": 3}}]), ("CONFIG.LOOP.STOP_AFTER_UNREACHABLE",), severity="warning")
    for field, mapping in (("carry", {"from": "value", "as": "state", "update": "next"}),
                           ("collect", {"from": "value", "as": "items"}), ("outputs", {"from": "value", "as": "result"})):
        emit("loop." + field + ".normal", pipeline(nodes=[{**loop, "loop": {**loop["loop"], field: [mapping]}}]))
        for label, value in (("list", {}), ("item", [1]), ("mode", [{**mapping, "mode": "last"}])):
            schema("loop." + field + "." + label, pipeline(nodes=[{**loop, "loop": {**loop["loop"], field: value}}]), "NODE_LOOP_INVALID")
        for key in mapping:
            schema("loop." + field + ".missing_" + key, pipeline(nodes=[{**loop, "loop": {**loop["loop"], field: [{k: v for k, v in mapping.items() if k != key}]}}]), "NODE_LOOP_INVALID")
    schema("io.on_process", node(io={"operation":"receive"}), "NODE_IO_INVALID")
    nodeset = {"type_key": "parity.child", "display_name": "Child", "description": "An imported child.",
               "requires": [], "provides": [], "pipeline": pipeline()["pipeline"]}
    emit("nodeset.normal", nodeset)
    schema("nodeset.expanded_list", {**pipeline(), "__vibeflow_expanded_nodesets__": True, "nodesets": {}}, "NODESETS_LIST")
    schema("nodeset.expanded_item", {**pipeline(), "__vibeflow_expanded_nodesets__": True, "nodesets": [1]}, "NODESET_OBJECT")
    for field in ("name", "category", "version", "purity", "exports"):
        schema("nodeset.removed." + field, {**nodeset, field: "old"}, "NODESET_FIELD_REMOVED")
    schema("nodeset.type_empty", {**nodeset, "type_key": ""}, "NODESET_MISSING_TYPE_KEY")
    for field in ("display_name", "description"):
        schema("nodeset.metadata." + field, {**nodeset, field: ""}, "NODESET_METADATA")
    for field in ("requires", "provides"):
        schema("nodeset.missing_" + field, {k: v for k, v in nodeset.items() if k != field}, "NODESET_CONTRACT")
        schema("nodeset.invalid_" + field, {**nodeset, field: {}}, "NODESET_CONTRACT_LIST")
    schema("nodeset.pipeline", {**nodeset, "pipeline": []}, "NODESET_PIPELINE")
    emit("nodeset.planned_no_pipeline", {k: v for k, v in {**nodeset, "status": "planned"}.items() if k != "pipeline"})
    for label, value, suffix in (("list", {}, "NODESET_IMPORTS_LIST"), ("empty_path", [""], "NODESET_IMPORT_PATH"),
                                ("object", [1], "NODESET_IMPORT_OBJECT"), ("missing_path", [{}], "NODESET_IMPORT_PATH"),
                                ("names", [{"path": "child.jsonc", "names": ["child"]}], "NODESET_IMPORT_NAMES_REMOVED")):
        schema("nodeset_imports." + label, {**pipeline(), "nodeset_imports": value}, suffix)
    emit("nodeset_imports.normal", {**pipeline(), "nodeset_imports": ["a.jsonc", {"path": "b.jsonc"}]})
    for field in ("config", "values"):
        schema("global." + field, {**pipeline(), "global_config": {field: []}}, "GLOBAL_CONFIG_VALUES")
    for field in ("allow_config_override", "override_child_config"):
        schema("global." + field, {**pipeline(), "global_config": {field: "yes"}}, "CONFIG_OVERRIDE_FLAG")
    for kind, key in (("plugin", "plugins"), ("host", "host_extensions"), ("base", "base_lib")):
        def resource(item):
            if kind == "plugin" and variant == "current":
                item = {"status":"planned", **item}
            return {**pipeline(), key: {"modules": [item]} if kind == "base" else [item]}
        schema("resource." + kind + ".status", resource({"id": "parity.resource", "status": "unfinished", **({"source":{"kind":"file","ref":"plugin.py"}} if kind == "plugin" and variant == "current" else {})}), "RESOURCE_STATUS")
        for field in ("display_name", "category", "description", "version"):
            if kind == "plugin" and variant == "current" and field == "category":
                emit("resource.plugin.metadata_category",resource({"id":"parity.resource","category":1}),("PLUGIN.SELECTION.MIGRATION",),classification="approved_change")
            else:
                schema("resource." + kind + ".metadata_" + field, resource({"id": "parity.resource", field: 1}), "RESOURCE_METADATA_STRING",classification="approved_change" if kind == "plugin" and variant == "current" else "preserved")
        emit("resource." + kind + ".planned", resource({"id": "parity.resource", "status": "planned"}))
    for label, item, suffix in (("empty", {}, "PLUGIN_MODULE"), ("planned_id", {"status": "planned"}, "PLUGIN_PLANNED_ID"),
                               ("class", {"id": "p", "class": ""}, "PLUGIN_CLASS"), ("type", {"id": "p", "type": "other"}, "PLUGIN_TYPE"),
                               ("priority", {"id": "p", "priority": True}, "PLUGIN_PRIORITY"),
                               ("conflict", {"id": "p", "conflict": "merge"}, "PLUGIN_CONFLICT"),
                               ("config", {"id": "p", "config": []}, "PLUGIN_CONFIG"), ("settings", {"id": "p", "settings": []}, "PLUGIN_CONFIG")):
        if variant == "current" and label != "planned_id":
            source = {"kind":"file","ref":"plugin.py"}
            if label == "class": source["export"] = ""
            elif label == "type": source["kind"] = "other"
            elif label == "empty": source = None
            item = {"source":source, **({"config":[]} if label == "config" else {})}
            if label == "priority": item = {"id":"p","status":"planned","priority":True}
            elif label in {"settings","conflict"}: item[label] = [] if label == "settings" else "merge"
            code = "CONFIG.SCHEMA.PLUGIN_CONFIG" if label == "config" else "PLUGIN.SELECTION.PRIORITY" if label == "priority" else "PLUGIN.SELECTION.MIGRATION" if label in {"settings","conflict"} else "PLUGIN.SELECTION.SOURCE"
            emit("plugin."+label,{**pipeline(),"plugins":[item]},(code,),classification="approved_change")
        else:
            schema("plugin." + label, {**pipeline(), "plugins": [item]}, suffix)
    for field in ("config", "settings"):
        schema("host." + field, {**pipeline(), "host_extensions": [{"id": "h", field: []}]}, "HOST_EXTENSION_CONFIG")
    for field in ("targets", "provides", "dependencies"):
        schema("host." + field, {**pipeline(), "host_extensions": [{"id": "h", field: [""]}]}, "HOST_EXTENSION_STRING_LIST")
    emit("host.disabled_duplicate", {**pipeline(), "host_extensions": ["h", {"id": "h", "enabled": False}]})
    emit("host.disabled_then_active", {**pipeline(), "host_extensions": [{"id": "h", "enabled": False}, "h"]})
    schema("policy.root", {**pipeline(), "policy": []}, "POLICY_ROOT")
    integer_sections = {"node_source": ("max_lines", "max_bytes", "warn_lines", "warn_bytes"),
                        "complexity": ("max_functions", "max_branches", "max_nesting_depth", "max_params", "max_contract_keys"),
                        "maintainability": ("warn_call_chain_length", "max_call_chain_length", "warn_dependency_chain_length", "max_dependency_chain_length")}
    for section, fields in integer_sections.items():
        schema("policy." + section + ".object", {**pipeline(), "policy": {section: []}}, "POLICY_SECTION")
        for field in fields:
            schema("policy." + section + "." + field, {**pipeline(), "policy": {section: {field: True}}}, "POLICY_POSITIVE_INT")
        emit("policy." + section + ".one", {**pipeline(), "policy": {section: {field: 1 for field in fields}}})
    emit("policy.complexity.disabled", {**pipeline(), "policy": {"complexity": {field: None for field in integer_sections["complexity"]}}})
    schema("policy.source.null", {**pipeline(), "policy": {"node_source": {"max_lines": None}}}, "POLICY_POSITIVE_INT")
    schema("policy.source.zero", {**pipeline(), "policy": {"node_source": {"max_lines": 0}}}, "POLICY_POSITIVE_INT")
    for section, fields in (("imports", ("allowed_roots", "banned_roots", "allowed_modules", "banned_modules")),
                            ("base_lib", ("allowed_paths", "allowed_modules", "banned_modules"))):
        if section == "base_lib" and variant == "current":
            removed = ("CONFIG.POLICY.BASE_LIB.REMOVED",)
            emit("policy.base_lib.object", {**pipeline(),"policy":{"base_lib":[]}}, removed, classification="approved_change")
            for field in fields:
                emit("policy.base_lib."+field,{**pipeline(),"policy":{"base_lib":{field:[""]}}},removed,classification="approved_change")
            emit("policy.base_lib.normal",{**pipeline(),"policy":{"base_lib":{field:["support"] for field in fields}}},removed,classification="approved_change")
        else:
            schema("policy." + section + ".object", {**pipeline(), "policy": {section: []}}, "POLICY_SECTION")
            for field in fields:
                schema("policy." + section + "." + field, {**pipeline(), "policy": {section: {field: [""]}}}, "POLICY_STRING_LIST")
            emit("policy." + section + ".normal", {**pipeline(), "policy": {section: {field: ["support"] for field in fields}}})
    legacy_entry = {"rule_id": "NODE.SOURCE.TOO_LONG", "to": "warning", "reason": "A documented migration case.", "expires": "2099-01-01"}
    removed = ("CONFIG.POLICY.RULES.REMOVED",)
    def legacy(name, value, baseline_codes=()):
        emit("policy.removed." + name, {**pipeline(), "policy": {"rules": value}}, removed,
             classification="approved_change", baseline_codes=baseline_codes)
    legacy("normal", {"downgrades": [legacy_entry]})
    legacy("object", [], ("CONFIG.SCHEMA.POLICY_SECTION",))
    legacy("list", {"downgrades": {}}, ("CONFIG.SCHEMA.POLICY_RULES_LIST",))
    legacy("item", {"downgrades": [1]}, ("CONFIG.SCHEMA.POLICY_RULE_OBJECT",))
    for field, code in (("rule_id", "ID"), ("reason", "REASON"), ("expires", "EXPIRES")):
        legacy("missing_" + field, {"downgrades": [{k: v for k, v in legacy_entry.items() if k != field}]}, ("CONFIG.SCHEMA.POLICY_RULE_" + code,))
    legacy("to", {"downgrades": [{**legacy_entry, "to": "error"}]}, ("CONFIG.SCHEMA.POLICY_RULE_TO",))
    legacy("scope", {"downgrades": [{**legacy_entry, "scope": []}]}, ("CONFIG.SCHEMA.POLICY_RULE_SCOPE",))
    legacy("exemption", {"exemptions": [{k: v for k, v in legacy_entry.items() if k != "to"}]})
    return rows
