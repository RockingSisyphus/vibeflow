"""Project-review rule resources over Target-extracted quality facts."""

from vibeflow.core.rules.models import RuleCall, RuleDescriptor, RuleRecord, RuleRelation, RuleResult, RulesetDescriptor


def _files(context, inputs, params):
    from vibeflow.core.quality.evaluator import _file_findings, _finding_belongs_to_file
    facts, policy = context.require("project_facts"), context.require("quality_policy")
    findings = []
    for file in facts.files:
        syntax_failed = any(item.rule_id.startswith("QUALITY.SYNTAX.") and _finding_belongs_to_file(item, file) for item in facts.findings)
        if not syntax_failed:
            findings.extend(_file_findings(file, facts.root, policy))
    return RuleResult(findings=tuple(findings))


def _dependencies(context, inputs, params):
    from vibeflow.core.quality.dependencies import dependency_findings
    from vibeflow.core.quality.evaluator import _build_dependency_graph, _import_sites_by_edge
    facts, policy = context.require("project_facts"), context.require("quality_policy")
    modules = {file.module for file in facts.files}
    graph = _build_dependency_graph(facts.files, modules)
    sites = _import_sites_by_edge(facts.files, modules)
    findings, chain = dependency_findings(graph, sites, policy.thresholds)
    return RuleResult({"graph": RuleRecord("vibeflow.module_graph.v1", graph),
                       "import_sites": RuleRecord("vibeflow.import_sites.v1", sites),
                       "chain": RuleRecord("vibeflow.module_chain.v1", chain)}, tuple(findings))


def _structure(context, inputs, params):
    from vibeflow.core.quality.root_structure import analyze_root_structure
    from vibeflow.core.quality.structure import analyze_directory_structure
    facts, policy = context.require("project_facts"), context.require("quality_policy")
    graph, sites = inputs["graph"].value, inputs["import_sites"].value
    directories, clusters, summary, findings = analyze_directory_structure(
        facts.files, graph, sites, policy.thresholds, policy.structure_conventions)
    root_summary, root_findings = analyze_root_structure(facts.files, graph, sites, policy.structure_limits,
        roles=policy.structure_roles, conventions=policy.structure_conventions)
    summary.update(root_summary)
    return RuleResult({"directories": RuleRecord("vibeflow.directories.v1", directories),
                       "clusters": RuleRecord("vibeflow.clusters.v1", clusters),
                       "summary": RuleRecord("vibeflow.structure_summary.v1", summary)}, tuple((*findings, *root_findings)))


def _duplicates(context, inputs, params):
    from vibeflow.core.quality.duplicates import duplicate_function_findings
    return RuleResult(findings=tuple(duplicate_function_findings(context.require("project_facts").files)))


def project_quality_resources():
    rules = (
        RuleDescriptor("vibeflow.quality.files"),
        RuleDescriptor("vibeflow.quality.dependencies", outputs={"graph": "vibeflow.module_graph.v1", "import_sites": "vibeflow.import_sites.v1", "chain": "vibeflow.module_chain.v1"}),
        RuleDescriptor("vibeflow.quality.structure", inputs={"graph": "vibeflow.module_graph.v1", "import_sites": "vibeflow.import_sites.v1"},
                       outputs={"directories": "vibeflow.directories.v1", "clusters": "vibeflow.clusters.v1", "summary": "vibeflow.structure_summary.v1"}),
        RuleDescriptor("vibeflow.quality.duplicates"),
    )
    ruleset = RulesetDescriptor("vibeflow.quality.project", tuple(RuleCall(item.id.rsplit(".", 1)[-1], item.id) for item in rules),
        (RuleRelation("structure", "dependencies", "requires", bindings={"graph": "graph", "import_sites": "import_sites"}),))
    return rules, ruleset


def project_quality_handlers():
    return {"vibeflow.quality.files": _files, "vibeflow.quality.dependencies": _dependencies,
            "vibeflow.quality.structure": _structure, "vibeflow.quality.duplicates": _duplicates}


__all__ = ["project_quality_handlers", "project_quality_resources"]
