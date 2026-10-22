"""JavaScript declaration, source-fact and governance binding preparation."""
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from vibeflow.targets.javascript.build.resource_facts import resource_import_facts


def discover_resources(directory, *, root, workspace, node_command, syntax_cache, loading_context=None):
    from vibeflow.targets.javascript.sdk.loading import discover_resources as discover
    return discover(directory, project_config=root.project_config, package_root=root.path, node_command=node_command)


def normalize_resource(declaration, implementation, *, directory, root, workspace):
    return declaration.descriptor


def source_analysis(workspace, root, workflows, *, node_command, syntax_cache):
    from vibeflow.targets.javascript.build.quality_source import collect_javascript_quality_facts, _file_fact, _finding_fact
    from vibeflow.targets.shared.quality_support import SourceQualityFacts
    measured = collect_javascript_quality_facts(root.path,
        package_root=root.path / root.project_config.get("javascript",{}).get("package_root","."),
        node_command=node_command)
    facts = SourceQualityFacts(str(root.path), tuple(_file_fact(item) for item in measured.files),
                              tuple(_finding_fact(item) for item in measured.findings))
    from vibeflow.tooling.project.source_governance import private_root_imports
    imports = []
    for file in measured.files:
        path = root.path / file["path"]
        for site in file["import_sites"]:
            if site.get("resolved_path"):
                imports.append((path, Path(site["resolved_path"]), site["line"]))
    return facts, private_root_imports(workspace, root, imports)


def shared_imports(workspace, root, *, node_command, syntax_cache):
    from vibeflow.targets.javascript.build.quality_source import collect_javascript_quality_facts
    from vibeflow.tooling.project.source_governance import private_root_imports
    imports = []
    for name in ("nodes", "base_lib", "plugins"):
        directory = workspace.root / name
        if not directory.is_dir():
            continue
        shared = collect_javascript_quality_facts(directory, package_root=root.path,
            node_command=node_command)
        for file in shared.files:
            for site in file["import_sites"]:
                if site.get("resolved_path"):
                    imports.append((directory / file["path"], Path(site["resolved_path"]), site["line"]))
    return private_root_imports(workspace, root, imports)


def review_workflow(workspace, path, *, preparation, governance):
    from vibeflow.tooling.application.javascript.audit import audit_javascript_project, JavascriptAuditRequest
    result = audit_javascript_project(JavascriptAuditRequest(workspace, path,
        node_command=preparation.node_command, preparation=preparation, governance=governance))
    return {"status":"CONCERNS" if result.warnings else "PASS", "warnings":list(result.warnings),
        "rule_checks":result.rule_report.to_dict(), "diagnostics":[], "source_files":list(result.source_files)}


@contextmanager
def governance_handlers(catalogs, rules, *, target_root, node_command):
    from vibeflow.targets.javascript.sdk.loading import contribution_session
    from vibeflow.core.rules.models import plain
    handlers, opened = {}, []
    try:
        for rule in rules:
            source = next(item.source for item in rule.implementations if item.language in {"javascript","typescript"})
            session = contribution_session(catalogs,"rules",rule.id)
            if session is None:
                raise ValueError(f"governance Rule '{rule.id}' has no declaration session")
            identity = "governance:" + uuid4().hex
            session.open_rule(identity, rule={"id":rule.id,"module":source.ref,"export":source.export or "check"},
                package_root=Path(getattr(target_root,"path",target_root)),target="project")
            opened.append((session,identity))
            def evaluate(context, inputs, params, *, current=session, key=identity):
                return current.evaluate_rule(key, context={"facts":plain(context.facts),"subject":plain(context.subject),
                    "scope":plain(context.scope),"phase":context.phase,"target":context.target},
                    params=plain(params), inputs={name:value.to_dict() for name,value in inputs.items()})
            handlers[rule.id] = evaluate
        yield handlers
    finally:
        for session,identity in reversed(opened):
            session.close(identity)
