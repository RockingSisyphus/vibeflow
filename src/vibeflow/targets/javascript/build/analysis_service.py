"""Command-owned JavaScript analysis services, independent of rule scheduling."""
from dataclasses import replace
from pathlib import Path
import json
from typing import Any, Mapping
from vibeflow.core.findings import Finding
from vibeflow.core.rules import RuleContext, RuleResult
from vibeflow.core.rules.models import plain
from vibeflow.core.quality import ProjectQualityFacts
from vibeflow.targets.javascript.build.toolchain import run_rule_check_driver, run_quality_facts_driver
from vibeflow.targets.javascript.build.quality_source import _file_fact, _finding_fact
from vibeflow.targets.javascript.quality.diagnostics import rule_finding


class JavascriptAnalysis:
    """Reuse facts in one audit without sharing decisions across subjects."""
    def __init__(self):
        self.checks: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}

    def clear(self):
        self.checks.clear()
        self.metrics.clear()

    def source_check(self, request: Mapping[str, Any], *, package_root: str, node_command: str):
        key = json.dumps([str(package_root),node_command,plain(request)], sort_keys=True)
        if key not in self.checks:
            self.checks[key] = run_rule_check_driver(request, package_root=package_root, node_command=node_command)
        return self.checks[key]

    def quality_facts(self, request: Mapping[str, Any], *, package_root: str, node_command: str):
        key = json.dumps([str(package_root),node_command,plain(request)], sort_keys=True)
        if key not in self.metrics:
            self.metrics[key] = run_quality_facts_driver(request, package_root=package_root, node_command=node_command)
        return self.metrics[key]

    def project_facts(self, facts: Mapping[str, Any]) -> ProjectQualityFacts:
        roots = list(facts.get("source_files", ()))
        if not roots:
            return ProjectQualityFacts(root=str(facts["project_root"]))
        sources = plain(facts.get("sources", ()))
        parsed = self.quality_facts({"qualityRoot": facts["project_root"], "qualityFiles": sorted(item["path"] for item in sources), "sourceSnapshots": sources},
                                    package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")))
        return ProjectQualityFacts(root=str(facts["project_root"]), files=tuple(_file_fact(item) for item in parsed.files),
                                   findings=tuple(_finding_fact(item) for item in parsed.findings))


def source_check(context: RuleContext, topics: tuple[str, ...], rule_id: str, *, params: Mapping[str, Any] | None = None) -> tuple[Finding, ...]:
    facts = context.facts
    if not topics or not facts.get("evaluate_sources", True):
        return ()
    result = facts["analysis_cache"].source_check(
        {"typecheckFiles": list(facts.get("source_files", ())), "ruleTopics": list(topics),
         "ruleParams": plain(params or {}),
         "importPolicy": plain(facts.get("import_policy", {})), "sourceSnapshots": plain(facts.get("sources", ())),
         "ruleSubjectKind": context.subject.get("kind", "node"), "ruleSubjectId": context.subject.get("type_key", context.subject.get("id", ""))},
        package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")),
    )
    return tuple(rule_finding(item, rule_id, context) for item in result.findings)



def measure_builtin_resource(context: RuleContext, params: Mapping[str, Any], *, topic="all"):
    from vibeflow.targets.javascript.quality.implementation import registered_implementation_requests, evaluate_registered_facts
    from vibeflow.core.descriptors.source_bundle import source_resources
    from vibeflow.core.rules.models import plain
    facts = context.facts
    if not facts.get("evaluate_sources", True):
        return RuleResult(state="unavailable")
    kind = context.subject.get("kind", "node")
    resource_id = context.subject.get("type_key", context.subject.get("id", ""))
    descriptor = next(item for owner,item in source_resources(facts["catalogs"]) if owner == kind and item.id == resource_id)
    base_ids: set[str] = set()
    def visit(resource_id: str) -> None:
        if resource_id in base_ids:
            return
        base_ids.add(resource_id)
        resource = facts["catalogs"].base_libs.get(resource_id)
        if resource is not None:
            for dependency in resource.dependencies:
                visit(dependency)
    for resource_id in getattr(descriptor, "base_libs", getattr(descriptor, "dependencies", ())) :
        visit(resource_id)
    selected_files = {item["path"] for item in facts.get("sources", ())}
    for source in facts.get("source_owners", ()):
        if source.get("kind") == "base_lib" and source.get("id") in base_ids:
            selected_files.add(source["path"])
    ownership, descriptors = registered_implementation_requests(facts["catalogs"], project_root=Path(facts["project_root"]), selected_files=tuple(selected_files))
    selected_ids = {context.subject.get("type_key", context.subject.get("id", "")), *base_ids}
    ownership = [item for item in ownership if item["type_key"] in selected_ids]
    descriptors = {key: value for key, value in descriptors.items() if key[0] in selected_ids}
    # Project scans have file facts but no descriptor/export implementation facts.
    # Native implementation limits inspect the owned files, including BaseLibs;
    # the reduced public Node view remains the input to project-defined Rules.
    extracted = facts["analysis_cache"].quality_facts({"qualityRoot": facts["project_root"],
        "qualityFiles": sorted({item["path"] for item in ownership}), "qualityImplementations": ownership,
        "sourceSnapshots": plain(facts.get("sources", ()))},
        package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")))
    if kind == "node" and facts.get("local_quality") is not None:
        from dataclasses import replace
        local = {item["path"]: item for item in facts["local_quality"]["files"]}
        # Analyze this Node's symbols/references while retaining the physical
        # source size, including comments and padding, for file size limits.
        # Keep BaseLib measurements and implementation binding facts intact.
        extracted = replace(extracted, files=tuple(
            {**local[item["path"]], "lines":item["lines"], "bytes":item["bytes"]}
            if item["path"] in local else item for item in extracted.files))
    found = evaluate_registered_facts(extracted, ownership, descriptors, project_root=Path(facts["project_root"]), policy_data=plain(params.get("policy", {})), topic=topic)
    from vibeflow.targets.javascript.quality.implementation import relative_source_path
    relative_files = {relative_source_path(item["path"], facts["project_root"]) for item in ownership}
    metrics = {"files": [plain(item) for item in extracted.files if item["path"] in relative_files],
               "implementations": [plain(item) for item in extracted.implementations if item["type_key"] in selected_ids]}
    return found, metrics
