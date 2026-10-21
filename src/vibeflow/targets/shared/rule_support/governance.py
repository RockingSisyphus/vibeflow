"""Default project/root policy over supplied inventory facts; no filesystem IO."""

from vibeflow.core.findings import HealthFinding
from dataclasses import replace
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleRelation, RuleResult, RulesetDescriptor


RESOURCE_DIRECTORIES = {"node": "nodes", "base_lib": "base_lib",
    **dict.fromkeys(("node_type", "rule", "ruleset", "data_schema", "capability", "plugin"), "plugins")}


def governance_resources(source_rules=()):
    rules = (
        RuleDescriptor("vibeflow.project.layout", level="project",
            params_schema={"directories": {"type": "array"}}, params_defaults={"directories": []}),
        RuleDescriptor("vibeflow.project.shared_resources", level="project"),
        RuleDescriptor("vibeflow.root.resources", level="root",
            params_schema={"allow_cross_root_imports":{"type":"boolean"}},
            params_defaults={"allow_cross_root_imports":False}),
        RuleDescriptor("vibeflow.root.layout", level="root",
            params_schema={"directories": {"type": "array"}}, params_defaults={"directories": []}),
        RuleDescriptor("vibeflow.project.structure", level="project"),
        RuleDescriptor("vibeflow.project.packages", level="project"),
        RuleDescriptor("vibeflow.project.dependencies", level="project",
            params_schema={"allow_cross_root_imports":{"type":"boolean"}},
            params_defaults={"allow_cross_root_imports":False}),
        RuleDescriptor("vibeflow.root.nodesets", level="root"),
        RuleDescriptor("vibeflow.root.packages", level="root"),
    )
    quality = tuple(replace(rule, id=rule.id.replace("vibeflow.quality.", "vibeflow.root."), level="root")
                    for rule in source_rules if rule.id.startswith("vibeflow.quality."))
    graph_quality = tuple(replace(rule, id=rule.id.replace("vibeflow.quality.", "vibeflow.graph.source."), level="graph")
                          for rule in source_rules if rule.id.startswith("vibeflow.quality."))
    quality_calls = tuple(RuleCall(rule.id.rsplit(".", 1)[1], rule_id=rule.id) for rule in quality)
    rulesets = (
        RulesetDescriptor("vibeflow.project.default", calls=(
            RuleCall("layout", rule_id=rules[0].id), RuleCall("shared", rule_id=rules[1].id),
            *(RuleCall(name, rule_id="vibeflow.project." + name) for name in ("structure", "packages", "dependencies")))),
        RulesetDescriptor("vibeflow.root.default", calls=(RuleCall("layout", rule_id=rules[3].id), RuleCall("resources", rule_id=rules[2].id),
            RuleCall("nodesets", rule_id="vibeflow.root.nodesets"), RuleCall("packages", rule_id="vibeflow.root.packages"), *quality_calls),
            relations=(RuleRelation("structure", "dependencies", "requires", {"graph": "graph", "import_sites": "import_sites"}),)
                      if quality_calls else ()),
    )
    return (*rules, *quality, *graph_quality), rulesets


def _finding(context, code, message, path, **details):
    return HealthFinding(rule_id=code, severity="error", object_type=context.scope["level"],
        object_id=context.subject["id"], message=message, source_location={"path": path},
        failure_layer="rule", details=details)


from vibeflow.core.project_layout import DIRECTORY_PURPOSES, ROOT_DIRECTORY_PURPOSES


def _layout(context, params, *, level, purposes):
    facts = context.facts[level]
    from pathlib import PurePosixPath
    allowed = set(purposes)
    containers = {""}
    if level == "project":
        for root in facts["roots"]:
            parts = PurePosixPath(root["path"]).parts
            allowed.update("/".join(parts[:count]) for count in range(1,len(parts)+1))
            containers.update("/".join(parts[:count]) for count in range(1,len(parts)))
    for item in params["directories"]:
        if not hasattr(item, "get"):
            raise ValueError("directories entries must contain path and purpose")
        path, purpose = item.get("path"), item.get("purpose")
        if not isinstance(path,str) or not path or "\\" in path or PurePosixPath(path).is_absolute() or any(part in {".",".."} for part in path.split("/")):
            raise ValueError("directories.path must name a relative directory")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError("directories.purpose must explain the directory's use")
        allowed.add(path)
        parts = PurePosixPath(path).parts
        allowed.update("/".join(parts[:count]) for count in range(1,len(parts)))
        containers.update("/".join(parts[:count]) for count in range(1,len(parts)))
    candidates = set(facts["directories"])
    candidates.update(item["path"] for item in facts.get("entries", ()) if item["kind"] == "directory"
                      and ("" if str(PurePosixPath(item["path"]).parent) == "." else str(PurePosixPath(item["path"]).parent)) in containers)
    findings = tuple(_finding(context, level.upper() + ".DIRECTORY.UNDECLARED",
        f"directory '{name}' has no declared purpose; configure the {level} layout Rule", facts["path"] + "/" + name)
        for name in sorted(candidates) if name not in allowed)
    return RuleResult(findings=findings)


def project_layout(context, inputs, params):
    return _layout(context, params, level="project", purposes=DIRECTORY_PURPOSES)


def root_layout(context, inputs, params):
    return _layout(context, params, level="root", purposes=ROOT_DIRECTORY_PURPOSES)


def shared_resources(context, inputs, params):
    facts = context.facts["project"]
    if not facts["inventory_complete"]:
        return RuleResult(findings=(_finding(context, "PROJECT.USAGE.INCOMPLETE",
            "workflow inventory is incomplete; shared resource usage cannot be determined", facts["path"]),),
            state="unavailable")
    findings = []
    for resource in facts["resources"]:
        expected = RESOURCE_DIRECTORIES.get(resource["kind"])
        if resource["owner"]["kind"] == "project" and expected and resource["relative_path"].split("/")[0] != expected:
            findings.append(_finding(context, "PROJECT.RESOURCE.LOCATION",
                f"{resource['kind']} '{resource['id']}' must be declared under {expected}/", resource["path"]))
    if not facts.get("usage_complete", True):
        return RuleResult(findings=tuple(findings))
    for resource in facts["resources"]:
        if resource["owner"]["kind"] != "project" or resource["kind"] not in {"node", "base_lib", "plugin_declaration"}:
            continue
        if resource.get("governance"):
            continue
        roots = sorted(set(resource["used_by_roots"]))
        if len(roots) < 2:
            findings.append(_finding(context, "PROJECT.RESOURCE.NOT_SHARED",
                f"project resource '{resource['id']}' is used by {len(roots)} roots; place it in its owning root",
                resource["path"], resource_id=resource["id"], used_by_roots=roots))
    return RuleResult(findings=tuple(findings))


def root_resources(context, inputs, params):
    facts = context.facts["root"]
    from vibeflow.targets.shared.rule_support.resource_governance import resource_boundaries
    findings = resource_boundaries(context, facts, params)
    if not params["allow_cross_root_imports"]:
        for item in facts.get("private_root_imports", ()):
            if item.get("shared"):
                continue
            importer = "project shared code" if item.get("shared") else f"root '{facts['id']}'"
            findings.append(_finding(context, "ROOT.RESOURCE.PRIVATE_IMPORT",
                f"{importer} imports private code from root '{item['root']}'",
                item["path"], imported_path=item["imported_path"], imported_root=item["root"], line=item["line"]))
    for resource in facts["resources"]:
        if resource["owner"]["kind"] != "root":
            continue
        expected = RESOURCE_DIRECTORIES.get(resource["kind"])
        if expected and resource["relative_path"].split("/")[0] != expected:
            findings.append(_finding(context, "ROOT.RESOURCE.LOCATION",
                f"{resource['kind']} '{resource['id']}' must be declared under {expected}/",
                resource["path"], resource_id=resource["id"]))
    return RuleResult(findings=tuple(findings))


def governance_handlers():
    from vibeflow.targets.shared.rule_support.source_quality import _files, _dependencies, _structure, _duplicates
    def root_quality(handler):
        def check(context, inputs, params):
            facts = context.facts["root"]
            result = handler(replace(context, facts={**context.facts, "source_quality": facts["source_quality"],
                "source_import_scopes":facts.get("source_import_scopes", ())}), inputs, params)
            from pathlib import Path
            def annotate(finding):
                location = dict(finding.source_location)
                path = location.get("path", "")
                if path and not Path(path).is_absolute():
                    location["path"] = str(Path(facts["path"]) / path)
                return replace(finding, root_id=facts["id"], root_path=facts["path"],
                    source_location=location, source_path=location.get("path", ""))
            return replace(result, findings=tuple(map(annotate, result.findings)))
        return check
    from vibeflow.targets.shared.rule_support.resource_governance import project_structure, packages, nodesets, shared_dependencies
    return {"vibeflow.project.structure": project_structure, "vibeflow.project.packages": packages,
            "vibeflow.project.dependencies": shared_dependencies,
            "vibeflow.root.nodesets": nodesets, "vibeflow.root.packages": packages,
            "vibeflow.project.layout": project_layout,
            "vibeflow.project.shared_resources": shared_resources,
            "vibeflow.root.resources": root_resources, "vibeflow.root.layout": root_layout,
            **{"vibeflow.graph.source." + name: handler for name, handler in
               (("files", _files), ("dependencies", _dependencies), ("structure", _structure), ("duplicates", _duplicates))},
            **{"vibeflow.root." + name: root_quality(handler) for name, handler in
               (("files", _files), ("dependencies", _dependencies), ("structure", _structure), ("duplicates", _duplicates))}}
