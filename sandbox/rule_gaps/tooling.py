"""Declaration failures and effective rule plans through actual public CLIs."""

from copy import deepcopy
import json
from pathlib import Path

from common import cli, command, copy_project, row, write


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _declaration_project(work, target, toolchain):
    root, project = copy_project(work, target, toolchain=toolchain)
    graph = _read(project / "configs/model.jsonc")
    graph["rulesets"] = []
    write(project / "configs/model.jsonc", graph)
    for path in (project / "bundle/nodes").glob("*.jsonc"):
        data = _read(path)
        data["rulesets"] = []
        write(path, data)
    marker = root / "handler-called"
    extension = "py" if target == "python" else "ts"
    implementation = lambda name: [{"language": "python" if target == "python" else "typescript",
        "source": {"kind": "file", "ref": f"rules/{name}.{extension}", "export": "check"}}]
    provider = {"kind": "rule", "id": "gap.provider", "outputs": {"value": "gap.value.v1"},
                "implementations": implementation("declaration_provider")}
    consumer = {"kind": "rule", "id": "gap.consumer", "inputs": {"input": "gap.value.v1"},
                "implementations": implementation("declaration_consumer")}
    resource = project / "bundle/rules/declaration-provider.jsonc"
    write(resource, provider)
    write(project / "bundle/rules/declaration-consumer.jsonc", consumer)
    write(project / "bundle/rulesets/declaration.jsonc", {
        "kind": "ruleset", "id": "gap.declaration", "calls": [
            {"id": "provider", "rule_id": "gap.provider"}, {"id": "consumer", "rule_id": "gap.consumer"}],
        "relations": [{"kind": "requires", "source": "consumer", "target": "provider",
                       "bindings": {"input": "value"}}],
        "entrypoints": {"import": ["consumer"], "static": ["consumer"], "run": []}})
    bundle_path = project / "bundles/domain.jsonc"
    bundle = _read(bundle_path)
    bundle["resources"]["rules"].extend(["../bundle/rules/declaration-provider.jsonc", "../bundle/rules/declaration-consumer.jsonc"])
    bundle["resources"]["rulesets"].append("../bundle/rulesets/declaration.jsonc")
    write(bundle_path, bundle)
    model = project / "bundle/nodes/model.jsonc"
    data = _read(model)
    data["rulesets"] = ["gap.declaration"]
    write(model, data)
    return project, marker, resource


def _handlers(project, target, marker, record_type):
    if target == "python":
        provider = ("from pathlib import Path\nfrom vibeflow.core.rules import RuleResult, RuleRecord\n"
            f"def check(context, inputs, params):\n    Path({str(marker)!r}).write_text('provider called')\n"
            f"    return RuleResult(records={{'value':RuleRecord({record_type!r}, 3)}})\n")
        consumer = "from vibeflow.core.rules import RuleResult\ndef check(context, inputs, params):\n    return RuleResult()\n"
        extension = "py"
    else:
        provider = ('import {writeFileSync} from "node:fs";\nexport function check(context, inputs, params) {\n' +
            f"  writeFileSync({json.dumps(str(marker))}, 'provider called');\n" +
            f"  return {{records:{{value:{{type_id:{json.dumps(record_type)},value:3}}}}}};\n}}\n")
        consumer = "export function check(context, inputs, params) { return {findings:[]}; }\n"
        extension = "ts"
    (project / f"rules/declaration_provider.{extension}").write_text(provider)
    (project / f"rules/declaration_consumer.{extension}").write_text(consumer)


def _resource_case(rows, work, target, label, group, value, toolchain):
    project, marker, provider_path = _declaration_project(work / label, target, toolchain)
    if group == "category":
        resource = project / "bundle/removed-category.jsonc"
        write(resource, {"kind":"node_category", "id":"model", "presentation":{"shape":value}})
        bundle_path = project / "bundles/domain.jsonc"
        bundle = _read(bundle_path)
        bundle["resources"]["nodes"].append("../bundle/removed-category.jsonc")
        write(bundle_path, bundle)
        record_type = "gap.value.v1"
    elif group == "node":
        resource = project / "bundle/nodes/model.jsonc"
        data = _read(resource)
        data["presentation"] = {"shape": value}
        write(resource, data)
        record_type = "gap.value.v1"
    else:
        resource = provider_path if group == "output" else project / "bundle/rules/declaration-consumer.jsonc"
        data = _read(resource)
        data["outputs" if group == "output" else "inputs"] = {"value" if group == "output" else "input": value}
        write(resource, data)
        # A valid counterpart and real output isolate the wrong declared type.
        record_type = str(value)
        counterpart = project / ("bundle/rules/declaration-consumer.jsonc" if group == "output" else "bundle/rules/declaration-provider.jsonc")
        other = _read(counterpart)
        other["inputs" if group == "output" else "outputs"] = {"input" if group == "output" else "value": record_type}
        write(counterpart, other)
    _handlers(project, target, marker, record_type)
    valid = group != "category" and isinstance(value, str) and bool(value)
    for entry in ("review-rules", "validate"):
        marker.unlink(missing_ok=True)
        observed = cli(project, entry, name=label + "-" + entry)
        declaration_source = project / ("code_plugin.py" if target == "python" else "code_plugin.ts")
        located = str(declaration_source) in json.dumps(observed["payload"], ensure_ascii=False) or str(declaration_source) in observed["message"]
        observed["metrics"].update(handler_called=marker.exists(), resource_located=located)
        metrics = {"exit_code": 0 if valid else 1, "json_output": True,
                   "handler_called": valid and entry == "validate"}
        expected = {"should_accept": valid, "metrics": metrics}
        if not valid:
            code = "DESCRIPTOR.INVALID"
            expected.update(codes=[code], message_contains=("category" if group == "category" else group if group == "node" else "outputs" if group == "output" else "inputs"))
            expected["metrics"]["resource_located"] = True
        rows.append(row(f"tooling.gaps.{target}.{label}.{entry}", "Declared " + group + " type via " + entry,
                        "declaration_contract", observed, expected))


def _sibling_project(work, toolchain, *, conflict=False):
    main_root, project = copy_project(work / "main", "python", toolchain=toolchain)
    sibling_root, sibling = copy_project(work / "sibling", "python", toolchain=toolchain)
    for path in (sibling / "bundle/nodes").glob("*.jsonc"):
        data = _read(path)
        data["type_key"] = "sibling." + data["type_key"]
        write(path, data)
    for folder in ("manifests/data", "manifests/data_schemas"):
        for path in (sibling / folder).glob("*.jsonc"):
            path.unlink()
    for path in (sibling / "bundle").rglob("*.jsonc"):
        data = _read(path)
        if data.get("kind") == "base_lib":
            data["id"] = "sibling." + data["id"]
            write(path,data)
        elif data.get("kind") == "node" and data.get("base_libs"):
            data["base_libs"] = ["sibling."+value for value in data["base_libs"]]
            write(path,data)
    config = project / "configs/model.jsonc"
    graph = _read(config)
    graph["pipeline"]["nodes"][1]["type_used"] = "sibling.example.model"
    write(config, graph)
    # The sibling Node must select one shared, explicitly enabled definition.
    # The non-conflict case contributes only sibling Nodes/helpers, referencing
    # main's rules. The conflict case intentionally contributes both definitions.
    if not conflict:
        for folder in ("rules", "rulesets"):
            for file in (sibling / "bundle" / folder).glob("*.jsonc"):
                file.unlink()
        bundle_path = sibling / "bundles/domain.jsonc"
        bundle = _read(bundle_path)
        bundle["resources"]["rules"] = []
        bundle["resources"]["rulesets"] = []
        write(bundle_path, bundle)
    if conflict:
        path = sibling / "bundle/rules/model-definition.jsonc"
        data = _read(path)
        data["description"] += " A conflicting sibling definition."
        write(path, data)
    workspace = work / "workspace.jsonc"
    write(workspace, {"roots": [{"id": "main", "path": str(project)}, {"id": "sibling", "path": str(sibling)}]})
    return project, sibling, config, workspace


def _workspace_cases(rows, work, toolchain):
    projects = {}
    for target in ("python", "javascript"):
        _, projects[target] = copy_project(work / "mixed", target, toolchain=toolchain)
    workspace = work / "mixed/workspace.jsonc"
    write(workspace, {"roots": [{"id": target, "path": str(project)} for target, project in projects.items()]})
    for target, project in projects.items():
        for entry in ("validate", "review-rules"):
            observed = command(project, [entry, "--workspace", workspace, "--config", project / "configs/model.jsonc", "--json"], name="mixed-" + entry)
            observed["metrics"]["model_selected"] = _model_selected(observed["payload"])
            rows.append(row(f"tooling.gaps.mixed.{target}.{entry}", "Same domain IDs in distinct language Targets",
                            "workspace_rule_scope", observed, {"metrics": {"exit_code": 0, "json_output": True, "model_selected": True}}))
    for conflict in (False, True):
        label = "conflict" if conflict else "reference"
        project, sibling, config, workspace = _sibling_project(work / label, toolchain, conflict=conflict)
        for entry in ("validate", "review-rules"):
            observed = command(project, [entry, "--workspace", workspace, "--config", config, "--json"], name=label + "-" + entry)
            expected = {"should_accept": not conflict, "metrics": {"exit_code": int(conflict), "json_output": True}}
            if conflict:
                observed["metrics"]["both_origins"] = all(str(path) in json.dumps(observed["payload"]) for path in
                    (project / "code_plugin.py", sibling / "code_plugin.py"))
                expected["metrics"]["both_origins"] = True
                expected["message_contains"] = "conflict"
                if entry == "validate":
                    expected["codes"] = ["RULE.RESOURCE.CONFLICT"]
                else:
                    expected["codes"] = ["RULE.RESOURCE.CONFLICT"]
            else:
                observed["metrics"]["model_selected"] = _model_selected(observed["payload"], type_key="sibling.example.model")
                expected["metrics"]["model_selected"] = True
            rows.append(row(f"tooling.gaps.sibling.{label}.{entry}", "Same Target sibling " + label,
                            "workspace_rule_scope", observed, expected))


def _model_selected(payload, *, type_key="example.model"):
    if isinstance(payload.get("nodes"), list):
        return any(item["type_key"] == type_key and "example.model_domain" in item["rulesets"] for item in payload["nodes"])
    if "rule_checks" in payload:
        return bool(payload["rule_checks"].get("subjects", {}).get(type_key))
    return any(execution.get("plan", {}).get("ruleset_id") == "example.model_domain"
               for execution in payload.get("info", {}).get("rule_executions", ()))


def run_cases(work_root: Path, variant="current", toolchain_root=None):
    if variant != "current":
        raise ValueError("new declaration APIs only exist in the current Target")
    rows = []
    for target in ("python", "javascript"):
        for group in ("category", "node"):
            for label, value in (("valid", "hex"), ("object", {}), ("list", [])):
                _resource_case(rows, work_root / "declarations", target, group + "_" + label, group, deepcopy(value), toolchain_root)
        for group in ("input", "output"):
            for label, value in (("valid", "gap.value.v1"), ("number", 42), ("object", {"bad": "type"})):
                _resource_case(rows, work_root / "declarations", target, group + "_" + label, group, deepcopy(value), toolchain_root)
    _workspace_cases(rows, work_root / "workspace", toolchain_root)
    return rows
