"""Plugin contribution ownership policy, shared by project and root Rules."""
from pathlib import PurePath
from vibeflow.core.rules import RuleResult
from vibeflow.targets.shared.rule_support.governance import _finding


def ownership(context, inputs, params):
    findings = []
    for package in context.facts[context.scope["level"]].get("packages", ()):
        base = PurePath(package["path"])
        for resource in package["resources"]:
            for path in (resource["path"], *resource["implementation_paths"]):
                if not PurePath(path).is_relative_to(base):
                    findings.append(_finding(context, "PLUGIN.PACKAGE.OWNERSHIP",
                        f"Plugin '{package['id']}' contribution is outside its package: {path}", path))
        for path in package["source_paths"]:
            value = PurePath(path)
            if value.is_relative_to(package["project_path"]) and not value.is_relative_to(base) and "node_modules" not in value.parts:
                findings.append(_finding(context, "PLUGIN.PACKAGE.IMPORT",
                    f"Plugin '{package['id']}' imports project code outside its package: {path}", path))
    return RuleResult(findings=tuple(findings))
