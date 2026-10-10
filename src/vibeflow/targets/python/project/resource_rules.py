"""Review explicitly selected Python extension sources before native binding."""

from pathlib import Path
from types import SimpleNamespace

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleGraphError, execute_rule_plan
from vibeflow.targets.python.project.source_closure import collect_python_source_facts, resolve_local_module_path
from vibeflow.targets.python.quality.rule_adapter import graph_error_finding, rule_resources
from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context
from vibeflow.targets.python.project.check_session import current_python_check, PythonCheckSession
from vibeflow.targets.python.quality.policy_parameters import complete_source_policy_plan


def review_python_resource(resource, *, base_path, registry=None, phase="import"):
    """Use a declaration/source subject, never a fabricated Node invocation."""
    if not resource.rulesets:
        return ()
    registry = registry or SimpleNamespace(rule_catalogs=())
    session = current_python_check(registry) or PythonCheckSession()
    root = Path(base_path).resolve()
    descriptor = resource.to_dict()
    kind = descriptor.get("kind", "plugin")
    implementation = next((item for item in getattr(resource, "implementations", ()) if item.language == "python"), None)
    reference = implementation.source.ref if implementation is not None else resource.module
    symbol_name = implementation.source.export or "" if implementation is not None else getattr(resource, "class_name", "")
    source_path = getattr(resource, "source_path", "")
    root_id = getattr(resource, "root_id", "")
    path = Path(reference) if Path(reference).is_absolute() else (root / reference).resolve()
    if not path.is_file():
        path = resolve_local_module_path(reference, project_root=root)
    if path is None or not path.is_file():
        return (HealthFinding(rule_id="RESOURCE.SOURCE.UNAVAILABLE", severity="error", object_type="plugin",
            object_id=resource.id, message=f"declared Python source is unavailable: {reference}",
            source_location={"path":source_path or str(root)}),)
    files = []
    from vibeflow.targets.python.project.source_membership import resource_paths
    entries = tuple(file for _,file,_ in resource_paths(resource, root, getattr(registry,"source_roots",(root,)))) if implementation else (path,)
    for fact in (fact for entry in entries for fact in collect_python_source_facts(entry, project_root=root, source_roots=getattr(registry, "source_roots", (root,)),_parsed=session.parsed_sources,_parse_cache=session.parse_cache)):
        if fact.load_error:
            return (HealthFinding(rule_id="RESOURCE.SOURCE.UNAVAILABLE",severity="error",object_type="plugin",
                object_id=resource.id,message=fact.load_error,source_location={"path":fact.path,"line":1}),)
        owner = Path(fact.root_path) if fact.root_path else root
        module = ".".join(Path(fact.path).relative_to(owner).with_suffix("").parts).removesuffix(".__init__")
        files.append(PythonSourceFile(fact.path, module, fact.source, root_id, fact._tree,
                                     fact.parse_error, fact.parse_line, fact.parse_column))
    files = list({file.path:file for file in files}.values())
    source_key = tuple((file.path,file.root_id,id(file._tree),file.text) for file in files)
    if source_key not in session.resource_sources:
        session.resource_sources[source_key] = build_python_source_context((), files)
    sources = session.resource_sources[source_key]
    _, contributions = session.declarations(registry)
    defaults = registry.rule_defaults() if hasattr(registry,"rule_defaults") else {}
    facts = {"resource_source_file":sources.file(str(path)),
             "resource_symbol":symbol_name, "resource":descriptor,
             "base_lib_file":sources.file(str(path)) if kind == "base_lib" else None}
    findings = []
    try:
        rules, rulesets = rule_resources(registry, **defaults)
        handlers = {}
        for selected in resource.rulesets:
            plan = session.plan(selected, rules, rulesets, phase)
            if not plan.invocations:
                continue
            custom = getattr(registry, "rule_handler_loader", None)
            if callable(custom):
                handlers.update(custom(plan))
            plan = complete_source_policy_plan(plan, defaults.get("purity_policy"), handlers=handlers)
            from vibeflow.targets.python.quality.project_context import project_rule_facts
            view = session.view(registry,sources,extra_facts=facts)
            from dataclasses import replace
            view = view.derive(project_rule_facts(plan,sources,session.project_facts_for(view),handlers=handlers))
            context = replace(view.context(phase),subject={"kind":kind,"id":resource.id,"descriptor":descriptor,
                "source_identity":("python",str(path),symbol_name,view.identity,
                    session.implementation_identity(plan,handlers))})
            result = execute_rule_plan(plan,context,handlers=handlers,source_cache=session.source_cache(phase))
            findings.extend(item for invocation,value in result.results.items()
                if invocation not in result.aliases or result.aliases[invocation].startswith("session:")
                for item in value.findings)
            for invocation_id, value in result.results.items():
                if value.state != "completed" and not any(item.severity == "error" for item in value.findings):
                    findings.append(HealthFinding(rule_id="RULE.EXECUTION.UNAVAILABLE",severity="error",object_type="plugin",
                        object_id=resource.id,message=f"rule '{invocation_id}' did not complete ({value.state})",
                        source_location={"path":str(path),"line":1},details={"state":value.state,"phase":phase}))
    except RuleGraphError as error:
        findings.append(graph_error_finding(registry,error,object_type="plugin",object_id=resource.id,
                                            fallback_path=source_path or str(path)))
    except Exception as error:
        if not getattr(error,"findings",()):
            raise
        findings.extend(error.findings)
    return tuple(findings)


def reached_base_lib_sources(registry, sources):
    """Return declared owners reached through the existing parsed import closure."""
    visited = set()
    for catalogs in registry.rule_catalogs or ():
        for descriptor in getattr(catalogs,"base_libs", ()):
            if descriptor.id in visited:
                continue
            origin = catalogs.base_libs.source_for(descriptor.id)
            owner = next((root for root in getattr(registry,"source_roots",()) if Path(origin).is_relative_to(root)), None)
            source = next((file for implementation in descriptor.implementations if implementation.language == "python"
                for file in sources.files if (implementation.source.kind == "module" and file.module == implementation.source.ref)
                or (implementation.source.kind == "file" and owner is not None
                    and Path(file.path) == (owner / implementation.source.ref).resolve())), None)
            if source is None:
                continue
            visited.add(descriptor.id)
            yield descriptor, source, origin


def review_reached_base_libs(registry, sources, *, rules, rulesets, handlers, phase, purity_policy=None, session=None, entry_paths=()):
    """Select only declared libraries in the actual Node import closure."""
    from dataclasses import replace
    from vibeflow.targets.python.quality.project_context import project_rule_facts
    findings, executions = [], []
    session = session or current_python_check(registry) or PythonCheckSession()
    _, contributions = session.declarations(registry)
    ownership = contributions.get("source_owners", ())
    reachable = {file.path for entry in entry_paths for file in sources.import_closure(entry)} if entry_paths else None
    for descriptor, source, origin in reached_base_lib_sources(registry, sources):
        if reachable is not None and source.path not in reachable:
            continue
        members = [item["path"] for item in ownership if item["kind"] == "base_lib" and item["id"] == descriptor.id]
        source_key = session.snapshot(sources), id(descriptor), tuple(members)
        if source_key not in session.library_sources:
            library_files = {file.path:file for entry in (members or [source.path]) for file in sources.import_closure(entry)}
            session.library_sources[source_key] = build_python_source_context((),library_files.values())
        library_sources = session.library_sources[source_key]
        symbol = next((item.source.export or "" for item in descriptor.implementations if item.language == "python"), "")
        for selected in descriptor.rulesets:
            try:
                plan = session.plan(selected, rules, rulesets, phase)
                if not plan.invocations:
                    continue
                custom = getattr(registry,"rule_handler_loader",None)
                if callable(custom):
                    handlers.update(custom(plan))
                plan = complete_source_policy_plan(plan, purity_policy, handlers=handlers)
                view = session.view(registry,library_sources,extra_facts={
                    "resource_source_file":source,"base_lib_file":source,"resource_symbol":symbol,
                    })
                view = view.derive(project_rule_facts(plan,library_sources,session.project_facts_for(view),handlers=handlers))
                context = replace(view.context(phase),subject={"kind":"base_lib","id":descriptor.id,"descriptor":descriptor.to_dict(),
                    "source_identity":("python",source.path,symbol,view.identity,
                        session.implementation_identity(plan,handlers))})
                result = execute_rule_plan(plan,context,handlers=handlers,source_cache=session.source_cache(phase))
                executions.append(result)
                findings.extend(replace(item,root_id=item.root_id or source.root_id,source_path=item.source_path or source.path)
                                for invocation,value in result.results.items()
                                if invocation not in result.aliases or result.aliases[invocation].startswith("session:")
                                for item in value.findings)
                for invocation_id, value in result.results.items():
                    if value.state != "completed" and not any(item.severity == "error" for item in value.findings):
                        findings.append(HealthFinding(rule_id="RULE.EXECUTION.UNAVAILABLE",severity="error",object_type="base_lib",
                            object_id=descriptor.id,message=f"rule '{invocation_id}' did not complete ({value.state})",
                            source_location={"path":source.path,"line":1},details={"state":value.state,"phase":phase}))
            except RuleGraphError as error:
                findings.append(graph_error_finding(registry,error,object_type="base_lib",object_id=descriptor.id,fallback_path=origin))
            except Exception as error:
                if not getattr(error,"findings",()):
                    raise
                findings.extend(error.findings)
    return tuple(findings), tuple(executions)
