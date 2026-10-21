"""VibeTrain workspace policy: roots may consume the framework, never each other."""
from pathlib import PurePath

from vibeflow.core import Finding
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.sdk import Plugin, rule, ruleset


def violation(code, path, message, details):
    return Finding(code=code, severity="error", subject_type="source", subject_id=str(path),
                   message=message, details=details)


def inside(path, parent):
    return bool(path and parent) and PurePath(path).is_relative_to(PurePath(parent))


def package_findings(facts):
    findings = []
    for package in facts.get("packages", ()):
        project = PurePath(package["project_path"])
        source = PurePath(package["source"])
        # These fixed exports intentionally publish the corresponding root's resources.
        framework = project / "vibetrain"
        if inside(str(source), str(framework / "plugins")):
            boundary = framework
        elif package.get("id") == "project.nodes" and source in (project / "project/plugins/node_resources.py", project / "project/task_nodes/resource_bundle.py"):
            boundary = project / "project"
        else:
            boundary = PurePath(package["path"])
            if boundary.parent.name != "plugins":
                findings.append(violation("VIBETRAIN.PACKAGE.LOCATION", source,
                    "Ordinary plugins must have an independent plugins/<package> directory.", {}))
            for resource in package.get("resources", ()):
                if resource.get("kind") == "node":
                    findings.append(violation("VIBETRAIN.PACKAGE.NODE", source,
                        "Only the framework and explicit task resource exports may contribute business Nodes.", {}))
        for path in package.get("source_paths", ()):
            if not inside(path, str(boundary)) and not (package.get("id") == "project.nodes" and inside(path, str(framework))):
                findings.append(violation("VIBETRAIN.PACKAGE.BOUNDARY", path,
                    "Plugin contribution escapes its authorized source boundary.",
                    {"plugin": package.get("id"), "boundary": str(boundary)}))
    return findings


@rule(id="vibetrain.root.framework_access", level="root")
def framework_access(context, inputs, params):
    facts = context.facts["root"]
    findings = []
    for dependency in (*facts.get("resource_dependencies", ()), *facts.get("private_root_imports", ())):
        owner = dependency.get("root", "")
        source = dependency.get("source_root", facts["id"])
        if owner and owner not in (source, "vibetrain"):
            findings.append(violation("VIBETRAIN.ROOT.PRIVATE_DEPENDENCY", dependency.get("path", ""),
                "Only vibetrain resources may be imported across roots.", dict(dependency)))
    return RuleResult(findings=tuple(findings))


@rule(id="vibetrain.root.packages", level="root")
def root_packages(context, inputs, params):
    return RuleResult(findings=tuple(package_findings(context.facts["root"])))


@rule(id="vibetrain.project.packages", level="project")
def project_packages(context, inputs, params):
    return RuleResult(findings=tuple(package_findings(context.facts["project"])))


root_checks = ruleset(id="vibetrain.root", calls=[
    {"id": "base", "ruleset_id": "vibeflow.root.default"},
    {"id": "framework_access", "rule_id": "vibetrain.root.framework_access"},
], relations=[
    {"source": "$self", "target": "base/resources", "kind": "overrides", "params": {"allow_cross_root_imports": True}},
    {"source": "$self", "target": "base/packages", "kind": "overrides", "replace_rule": "vibetrain.root.packages"},
])
project_checks = ruleset(id="vibetrain.project", calls=[
    {"id": "base", "ruleset_id": "vibeflow.project.default"},
], relations=[
    {"source": "$self", "target": "base/packages", "kind": "overrides", "replace_rule": "vibetrain.project.packages"},
])

plugin = Plugin(id="vibetrain.framework_access", resources=[
    framework_access, root_packages, project_packages, root_checks, project_checks,
], display_name="VibeTrain 框架共享授权", description="保留原生检查，仅授权框架 root 的资源共享与固定导出边界。", version="1.0.0")
