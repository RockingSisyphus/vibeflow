"""Language-neutral descriptor validation through the real public parser.

DESCRIPTOR.MODEL is a sandbox observation label for DescriptorModelError, not a
production diagnostic ID. Message assertions identify the rejected contract.
"""

from copy import deepcopy
from pathlib import Path


JS = {"language": "javascript", "targets": ["node"], "source": {"kind": "file", "ref": "nodes/work.js", "export": "run"}}
PYTHON = {"language": "python", "targets": ["python"], "source": {"kind": "module", "ref": "nodes.work", "export": "Work"}}
REQUIRES = {"type": "parity.input", "cardinality": "exactly_one", "display_name": "Input"}
PROVIDES = {"key": "value", "type": "parity.output", "display_name": "Output"}
CONTRACT = {"requires": [REQUIRES], "provides": [PROVIDES], "input_semantics": {"parity.input": ["Input meaning."]},
            "output_semantics": {"value": ["Output meaning."]}}
NODE = {'node_type': 'vibeflow.node', "kind": "node", 'id': "parity.work", "display_name": "Work", "description": "A work unit.",
        "version": "1.0", "flow_kind": "process", "contract": CONTRACT, "implementations": [JS]}
BASE = {"kind": "base_lib", "id": "parity.base", "display_name": "Base", "description": "A pure helper.", "implementations": [JS]}
DATA = {"kind": "data_schema", "type_key": "parity.value", "schema": {"type": "number"}}
CAPABILITY = {"kind": "capability", "id": "parity.cap", "targets": ["node"],
              "operations": {"read": {"input_type": "parity.input", "output_type": "parity.output"}}}
PLUGIN = {"kind": "plugin", "id": "parity.plugin", "type": "runtime", "targets": ["node"], "implementations": [JS]}


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    from vibeflow.core.descriptors.models import DescriptorModelError
    if variant == "baseline":
        from vibeflow.tooling.project.resources import parse_descriptor_manifest
    else:
        from vibeflow.core.descriptors.decode import decode_resource as parse_descriptor_manifest

    rows = []

    def emit(name, data, reason="", *, kind=None, metrics=None):
        try:
            descriptor = parse_descriptor_manifest(data, expected_kind=kind)
            payload = descriptor.to_dict()
            actual = {"status": "PASS", "codes": [], "positions": [], "metrics": payload, "message": "Parsed declaration without loading implementation."}
        except DescriptorModelError as error:
            actual = {"status": "ERROR", "codes": [{"code": "DESCRIPTOR.MODEL", "severity": "error"}], "positions": [], "metrics": {}, "message": str(error)}
        except Exception as error:
            actual = {"status": "ERROR", "codes": [], "positions": [], "metrics": {}, "message": repr(error)}
        rows.append({"id": "tooling.descriptor." + name, "title": name, "family": "descriptor.contract", "classification": "preserved",
                     "expected": {"should_accept": not reason, "exact_codes": True,
                                  "codes": [{"code": "DESCRIPTOR.MODEL", "severity": "error"}] if reason else [],
                                  **({"message_contains": reason} if reason else {}), **({"metrics": metrics} if metrics else {})}, "actual": actual,
                     "evidence": "Public parse_descriptor_manifest and immutable Descriptor model checks, baseline/current",
                     "notes": "DESCRIPTOR.MODEL labels the public model exception in this harness; implementation code is never imported."})

    for name, data in (("node", NODE), ("base", BASE), ("data", DATA), ("capability", CAPABILITY), ("plugin", PLUGIN)):
        emit(name + ".normal", deepcopy(data), kind=data["kind"])
        emit(name + ".unknown_field", {**data, "unexpected": True}, "unknown fields")
    emit("root", [], "single object")
    emit("kind.missing", {}, "kind")
    emit("kind.unknown", {"kind": "unknown"}, "kind must be one of")
    emit("kind.directory_mismatch", NODE, "does not match directory kind", kind="base_lib")
    for field in ("id", "display_name", "description", "version", "flow_kind", "contract"):
        emit("node.missing_" + field, {k: v for k, v in NODE.items() if k != field}, "node." + field)
    emit("node.invalid_flow", {**NODE, "flow_kind": "unknown"}, "flow_kind")
    emit("node.external_boolean", {**NODE, "external": 1}, "node.external must be a boolean")
    emit("node.author_type", {**NODE, "author": 1}, "node.author")
    emit("node.category_type", {**NODE, "category": 1}, "unknown fields" if variant == "current" else "optional string")
    for field in ("tags", "base_libs"):
        for label, value in (("list", "one"), ("empty", [""]), ("duplicate", ["a", "a"]), ("item", [1])):
            emit("node." + field + "." + label, {**NODE, field: value}, "node." + field)
    for field in ("params_schema", "params_defaults", "input_semantics", "output_semantics"):
        emit("contract." + field + ".object", {**NODE, "contract": {**CONTRACT, field: []}}, "node.contract." + field)
    emit("contract.unknown", {**NODE, "contract": {**CONTRACT, "extra": True}}, "unknown fields")
    for field, item in (("requires", REQUIRES), ("provides", PROVIDES)):
        for label, value, reason in (("list", "one", "list of objects"), ("item", [1], "must be an object"),
                                     ("unknown", [{**item, "extra": 1}], "unknown fields"),
                                     ("duplicate", [item, item], "duplicate")):
            emit("contract." + field + "." + label, {**NODE, "contract": {**CONTRACT, field: value}}, reason)
        for key in item:
            emit("contract." + field + ".missing_" + key, {**NODE, "contract": {**CONTRACT, field: [{k: v for k, v in item.items() if k != key}]}}, "." + key)
    emit("contract.cardinality", {**NODE, "contract": {**CONTRACT, "requires": [{**REQUIRES, "cardinality": "many"}]}}, "cardinality must be one of")
    for field, key in (("input_semantics", "parity.input"), ("output_semantics", "value")):
        emit("contract." + field + ".missing", {**NODE, "contract": {**CONTRACT, field: {}}}, "must cover exactly")
        emit("contract." + field + ".extra", {**NODE, "contract": {**CONTRACT, field: {key: ["Meaning"], "extra": ["Extra"]}}}, "must cover exactly")
        emit("contract." + field + ".values", {**NODE, "contract": {**CONTRACT, field: {key: "Meaning"}}}, "list of strings")
    emit("contract.examples.list", {**NODE, "contract": {**CONTRACT, "examples": "example"}}, "list of objects")
    emit("contract.examples.item", {**NODE, "contract": {**CONTRACT, "examples": [1]}}, "must be an object")
    emit("contract.examples.outputs_baseline_valid", {**NODE, "contract": {**CONTRACT, "examples": [{"outputs": {}}]}})
    emit("contract.examples.normal", {**NODE, "contract": {**CONTRACT, "examples": [{"inputs": {}, "params": {}}]}})
    for label, value, reason in (("list", "source", "list of objects"), ("item", [1], "must be an object"),
                                 ("unknown", [{**JS, "extra": 1}], "unknown fields"),
                                 ("duplicate_target", [JS, JS], "target")):
        emit("implementation." + label, {**NODE, "implementations": value}, reason)
    for field in ("language", "targets", "source"):
        emit("implementation.missing_" + field, {**NODE, "implementations": [{k: v for k, v in JS.items() if k != field}]}, field)
    for label, fields, reason in (("language", {"language": "ruby"}, "implementation.language"),
                                 ("targets_empty", {"targets": []}, "cannot be empty"),
                                 ("targets_unknown", {"targets": ["ios"]}, "unsupported targets"),
                                 ("targets_duplicate", {"targets": ["node", "node"]}, "duplicate values"),
                                 ("js_python", {"targets": ["python"]}, "cannot target 'python'"),
                                 ("completion", {"completion": "eventual"}, "implementation.completion")):
        emit("implementation." + label, {**NODE, "implementations": [{**JS, **fields}]}, reason)
    emit("implementation.python_target", {**NODE, "implementations": [{**PYTHON, "targets": ["node"]}]}, "must target only 'python'")
    emit("implementation.python_suspend", {**NODE, "implementations": [{**PYTHON, "completion": "suspend"}]}, "only immediate completion")
    emit("implementation.js_alias", {**NODE, "implementations": [{**JS, "language": "js"}]}, metrics={"implementations": [{**JS, "completion": "immediate"}]})
    emit("implementation.ts_alias", {**NODE, "implementations": [{**JS, "language": "ts", "completion": "suspend"}]}, metrics={"implementations": [{**JS, "language": "typescript", "completion": "suspend"}]})
    for field in ("kind", "ref"):
        emit("source.missing_" + field, {**NODE, "implementations": [{**JS, "source": {k: v for k, v in JS["source"].items() if k != field}}]}, "source." + field)
    for label, fields, reason in (("kind", {"kind": "http"}, "source.kind"), ("ref", {"ref": ""}, "source.ref"),
                                 ("export", {"export": 1}, "source.export"), ("unknown", {"extra": True}, "unknown fields")):
        emit("source." + label, {**NODE, "implementations": [{**JS, "source": {**JS["source"], **fields}}]}, reason)
    for label, value, reason in (("list", "cap", "list of objects"), ("item", [1], "must be an object"),
                                 ("id", [{}], ".id"), ("operations", [{"id": "cap", "operations": "read"}], "list of strings"),
                                 ("unknown", [{"id": "cap", "operations": [], "extra": 1}], "unknown fields")):
        emit("node.capabilities." + label, {**NODE, "capabilities": value}, reason)
    for name, data in (("base", BASE), ("plugin", PLUGIN)):
        emit(name + ".implementations_empty", {**data, "implementations": []}, "implementations cannot be empty")
        emit(name + ".dependencies_self", {**data, "dependencies": [data["id"]]}, "cannot depend on itself")
        for field in ("dependencies", "external_packages"):
            emit(name + "." + field + ".duplicate", {**data, field: ["dep", "dep"]}, "duplicate values")
            emit(name + "." + field + ".list", {**data, field: "dep"}, "list of strings")
    for name, data in (("capability", CAPABILITY), ("plugin", PLUGIN)):
        emit(name + ".targets_empty", {**data, "targets": []}, "targets cannot be empty")
        emit(name + ".targets_unknown", {**data, "targets": ["ios"]}, "unsupported targets")
    emit("plugin.target_coverage", {**PLUGIN, "targets": ["browser"]}, "exactly match implementation target coverage")
    emit("plugin.priority_bool", {**PLUGIN, "priority": True}, "must be an integer")
    emit("plugin.priority_float", {**PLUGIN, "priority": 1.5}, "must be an integer")
    emit("plugin.type", {**PLUGIN, "type": "unknown"}, "plugin.type")
    for label, config, reason in (("object", [], "must be an object"), ("unknown", {"extra": True}, "unknown fields"),
                                  ("schema", {"schema": []}, "plugin.config.schema"), ("defaults", {"defaults": []}, "plugin.config.defaults"),
                                  ("finite", {"defaults": {"x": float("inf")}}, "finite JSON numbers")):
        emit("plugin.config." + label, {**PLUGIN, "config": config}, reason)
    without_export = {**JS, "source": {k: v for k, v in JS["source"].items() if k != "export"}}
    emit("plugin.default_factory", {**PLUGIN, "implementations": [without_export]}, metrics={"implementations": [{**JS, "source": {**JS["source"], "export": "createPlugin"}, "completion": "immediate"}]})
    for label, fields, reason in (("id_disagrees", {"id": "other"}, "cannot disagree"), ("representation", {"representation": "binary"}, "must be 'json'"),
                                 ("schema_object", {"schema": []}, "must be an object"),
                                 ("dialect", {"schema": {"$schema": "old"}}, "draft 2020-12"),
                                 ("finite", {"schema": {"maximum": float("nan")}}, "finite JSON numbers")):
        emit("data." + label, {**DATA, **fields}, reason)
    emit("data.id_alias", {"kind": "data_schema", "id": "parity.value", "schema": {}}, metrics={"type_key": "parity.value"})
    for label, operations, reason in (("object", [], "must be an object"), ("empty", {}, "non-empty object"),
                                      ("item", {"read": []}, "must be an object"),
                                      ("unknown", {"read": {**CAPABILITY["operations"]["read"], "extra": 1}}, "unknown fields"),
                                      ("completion", {"read": {**CAPABILITY["operations"]["read"], "completion": "later"}}, "immediate or suspend")):
        emit("capability.operations." + label, {**CAPABILITY, "operations": operations}, reason)
    for field in ("input_type", "output_type"):
        emit("capability.operation.missing_" + field, {**CAPABILITY, "operations": {"read": {k: v for k, v in CAPABILITY["operations"]["read"].items() if k != field}}}, "." + field)
    return rows
