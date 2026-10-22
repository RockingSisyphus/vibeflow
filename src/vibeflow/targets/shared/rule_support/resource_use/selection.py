"""Independent resource-selection Rules over workflow facts."""
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.core.descriptors.resource_use import RESOURCE_SET_TYPE, RESOURCE_USE_TYPE
from vibeflow.targets.shared.rule_support.governance import _finding


def workflows(context):
    return context.facts["root"].get("resource_workflows", ())


def result(values, findings=(), *, final=False):
    return RuleResult({"use" if final else "resources": RuleRecord(
        RESOURCE_USE_TYPE if final else RESOURCE_SET_TYPE, {"workflows": values})}, tuple(findings))


def visibility(context, inputs, params):
    values = {}
    for workflow in workflows(context):
        values[workflow["workflow"]] = [item for item in workflow["resources"]
            if item["owner"].get("kind") != "root" or item["owner"].get("id") == workflow["root_id"]]
    return result(values)


def independent(context, inputs, params):
    values, findings = {}, []
    for workflow in workflows(context):
        available = {item["id"]: item for item in workflow["resources"] if item["kind"] == "base_lib"}
        selected = []
        for spec in workflow["base_lib"]:
            if spec.get("status") == "planned":
                continue
            item = available.get(spec["id"])
            if item is None:
                findings.append(_finding(context, "CONFIG.RESOURCE.UNKNOWN_BASE_LIB",
                    f"unknown BaseLib ID: {spec['id']}", workflow["path"], resource_id=spec["id"], workflow=workflow["workflow"]))
            elif item["owner"].get("kind") != "plugin":
                selected.append({"kind": "base_lib", "id": item["id"], "reason": "explicit", "selection": spec})
        values[workflow["workflow"]] = selected
    return result(values, findings)


def plugins(context, inputs, params):
    values = {}
    for workflow in workflows(context):
        values[workflow["workflow"]] = [
            {"kind": item["kind"], "id": item["id"], "reason": "plugin:" + item["owner"]["id"]}
            for item in workflow["resources"] if item["owner"].get("kind") == "plugin"
            and item["owner"].get("id") in workflow["plugins"]]
    return result(values)


def duplicates(context, inputs, params):
    findings = []
    for workflow in workflows(context):
        owned = {item["id"]: item["owner"]["id"] for item in workflow["resources"]
                 if item["kind"] == "base_lib" and item["owner"].get("kind") == "plugin"}
        for spec in workflow["base_lib"]:
            if spec["id"] in owned:
                findings.append(_finding(context, "RESOURCE.BASE_LIB.PLUGIN_SELECTION",
                    f"BaseLib '{spec['id']}' is contributed by Plugin '{owned[spec['id']]}'; select the Plugin only",
                    workflow["path"], resource_id=spec["id"], plugin_id=owned[spec["id"]], workflow=workflow["workflow"]))
    return RuleResult(findings=tuple(findings))


def compose(context, inputs, params):
    values = {}
    visible = inputs["visible"].value["workflows"]
    for workflow in workflows(context):
        key = workflow["workflow"]
        candidates = {(item["kind"], item["id"]): item for item in visible[key]}
        selected = {(item["kind"], item["id"]): {"kind": item["kind"], "id": item["id"], "reason": "declaration"}
            for item in visible[key] if item["kind"] != "base_lib" and item["owner"].get("kind") != "plugin"}
        # Builtin declarations are framework contributions, not configured packages.
        selected.update({(item["kind"], item["id"]): {"kind": item["kind"], "id": item["id"], "reason": "builtin"}
            for item in visible[key] if item["owner"].get("kind") == "plugin"
            and item["owner"].get("id") not in workflow["plugins"]})
        for name in ("independent", "plugins"):
            selected.update({(item["kind"], item["id"]): dict(item) for item in inputs[name].value["workflows"][key]
                             if (item["kind"], item["id"]) in candidates})
        values[key] = {"workflow": key, "resources": list(selected.values()), "planned": workflow["planned"]}
    return result(values, final=True)
