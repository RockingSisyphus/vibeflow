"""Project topology and resource boundaries, evaluated by ordinary Rules."""
from pathlib import PurePath
from vibeflow.core.rules import RuleResult


def _finding(context, code, message, path, **details):
    from vibeflow.targets.shared.rule_support.governance import _finding as finding
    return finding(context, code, message, path, **details)


def project_structure(context, inputs, params):
    facts = context.facts["project"]
    base, findings = PurePath(facts["path"]), []
    roots = facts["roots"]
    for index, root in enumerate(roots):
        path = PurePath(root["absolute_path"])
        if path == base or not path.is_relative_to(base):
            findings.append(_finding(context, "WORKSPACE.ROOT.SEPARATE_DIRECTORY",
                "each root must be in its own subdirectory of the project", str(path)))
        if not PurePath(root["config_path"]).is_relative_to(path):
            findings.append(_finding(context, "WORKSPACE.PROJECT_CONFIG.PATH",
                "root configuration must be inside its root directory", root["config_path"]))
        for other in roots[:index]:
            previous = PurePath(other["absolute_path"])
            if path.is_relative_to(previous) or previous.is_relative_to(path):
                findings.append(_finding(context, "WORKSPACE.ROOT.OVERLAP",
                    f"roots '{root['id']}' and '{other['id']}' must have separate directories", str(path)))
    return RuleResult(findings=tuple(findings))


def nodesets(context, inputs, params):
    findings = []
    for item in context.facts["root"].get("nodeset_imports", ()):
        source, target = item["source_target"], item["import_target"]
        if source and target and source != target:
            findings.append(_finding(context, "WORKSPACE.NODESET.TARGET_MISMATCH",
                f"NodesetType import crosses project targets: {source!r} -> {target!r}", item["importer"],
                import_path=item["path"], field=item["field"]))
    return RuleResult(findings=tuple(findings))


def packages(context, inputs, params):
    level = context.scope["level"]
    facts, findings = context.facts[level], []
    for package in facts.get("packages", ()):
        base, owner = PurePath(package["path"]), PurePath(package["owner_path"])
        source = PurePath(package["source"])
        if package["source_kind"] == "file" and (not source.is_relative_to(owner/"plugins")
                or len(source.relative_to(owner/"plugins").parts) < 2):
            findings.append(_finding(context, "PLUGIN.PACKAGE.LOCATION",
                "file Plugins require their own package directory under plugins/", str(source)))
        for resource in package["resources"]:
            if resource["kind"] == "node":
                findings.append(_finding(context, "PLUGIN.PACKAGE.BUSINESS_NODE",
                    "Plugins contribute NodeTypes; business Nodes belong in project/root nodes/", resource["path"]))
            for path in (resource["path"], *resource["implementation_paths"]):
                if not PurePath(path).is_relative_to(base):
                    findings.append(_finding(context, "PLUGIN.PACKAGE.OWNERSHIP",
                        f"Plugin '{package['id']}' contribution is outside its package: {path}", path))
        for path in package["source_paths"]:
            value = PurePath(path)
            if value.is_relative_to(package["project_path"]) and not value.is_relative_to(base) and "node_modules" not in value.parts:
                findings.append(_finding(context, "PLUGIN.PACKAGE.IMPORT",
                    f"Plugin '{package['id']}' imports project code outside its package: {path}", path))
    for item in facts.get("nodeset_imports", ()) if level == "root" else ():
        # The directory convention describes unselected packages too.
        if any(PurePath(item["path"]).is_relative_to(directory) for directory in facts.get("plugin_directories", ())):
            findings.append(_finding(context, "WORKSPACE.NODESET.PLUGIN_PRIVATE",
                "Plugin private files cannot be selected independently with nodeset_imports", item["importer"],
                import_path=item["path"]))
    return RuleResult(findings=tuple(findings))


def resource_boundaries(context, facts, params):
    findings = []
    if params.get("allow_cross_root_imports", False):
        return findings
    for item in facts.get("resource_dependencies", ()):
        foreign = item["root"] and item["root"] != item["source_root"]
        if item["kind"] == "nodeset" and not item["root"]:
            code, message = "WORKSPACE.NODESET.OUTSIDE_ROOT", "NodesetType definitions must belong to the importing root"
        elif item["kind"] == "nodeset" and foreign:
            code, message = "WORKSPACE.NODESET.PRIVATE", "another root's private NodesetType cannot be imported"
        elif foreign or not item["in_project"]:
            code, message = "ROOT.RESOURCE.PRIVATE_IMPORT", "resource dependency crosses its project/root boundary"
        else:
            continue
        findings.append(_finding(context, code, message, item["path"], imported_path=item["imported_path"], kind=item["kind"]))
    return findings


def shared_dependencies(context, inputs, params):
    facts = context.facts["project"]
    findings = []
    if not params["allow_cross_root_imports"]:
        for item in (*facts.get("shared_imports", ()), *facts.get("resource_dependencies", ())):
            if item.get("shared") and item.get("root"):
                findings.append(_finding(context, "PROJECT.RESOURCE.PRIVATE_IMPORT",
                    "project shared code cannot depend on root private code", item["path"],
                    imported_path=item["imported_path"], imported_root=item["root"]))
    return RuleResult(findings=tuple(findings))
