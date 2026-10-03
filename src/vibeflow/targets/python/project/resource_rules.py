"""Review explicitly selected Python extension sources before native binding."""

from pathlib import Path
from types import SimpleNamespace

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleContext, RuleGraphError, compile_ruleset, execute_rule_plan
from vibeflow.targets.python.project.source_closure import collect_python_source_facts, resolve_local_module_path
from vibeflow.targets.python.quality.rule_adapter import graph_error_finding, rule_resources
from vibeflow.targets.python.quality.rules import python_rule_handlers
from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context


def review_python_resource(resource, *, base_path, registry=None, phase="import"):
    """Use a declaration/source subject, never a fabricated Node invocation."""
    if not resource.rulesets:
        return ()
    registry = registry or SimpleNamespace(rule_catalogs=())
    root = Path(base_path).resolve()
    reference = resource.module
    path = Path(reference) if Path(reference).is_absolute() else (root / reference).resolve()
    if not path.is_file():
        path = resolve_local_module_path(reference, project_root=root)
    if path is None or not path.is_file():
        return (HealthFinding(rule_id="RESOURCE.SOURCE.UNAVAILABLE", severity="error", object_type="plugin",
            object_id=resource.id, message=f"declared Python source is unavailable: {reference}",
            source_location={"path":resource.source_path or str(root), "line":1, "column":1}),)
    files = []
    for fact in collect_python_source_facts(path, project_root=root, source_roots=getattr(registry, "source_roots", (root,))):
        if fact.load_error:
            return (HealthFinding(rule_id="RESOURCE.SOURCE.UNAVAILABLE",severity="error",object_type="plugin",
                object_id=resource.id,message=fact.load_error,source_location={"path":fact.path,"line":1}),)
        owner = Path(fact.root_path) if fact.root_path else root
        module = ".".join(Path(fact.path).relative_to(owner).with_suffix("").parts).removesuffix(".__init__")
        files.append(PythonSourceFile(fact.path, module, fact.source, resource.root_id, fact._tree,
                                     fact.parse_error, fact.parse_line, fact.parse_column))
    sources = build_python_source_context((), files)
    facts = {"source_context":sources, "resource_source_file":sources.file(str(path)),
             "resource_symbol":resource.class_name, "resource":resource.to_dict()}
    findings, cache = [], {}
    try:
        rules, rulesets = rule_resources(registry)
        handlers = python_rule_handlers()
        for selected in resource.rulesets:
            plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
            custom = getattr(registry, "rule_handler_loader", None)
            if callable(custom):
                handlers.update(custom(plan))
            from vibeflow.targets.python.quality.project_context import project_rule_facts
            context = RuleContext(facts={**facts, **project_rule_facts(plan, sources, cache)},
                subject={"kind":"plugin", "id":resource.id, "descriptor":resource.to_dict(),
                         "source_identity":("python",str(path),resource.class_name,tuple((item.path,item.text) for item in files))},
                scope={"files":tuple(item.path for item in files)}, phase=phase, target="python")
            result = execute_rule_plan(plan, context, handlers=handlers)
            findings.extend(result.findings)
            for invocation_id, value in result.results.items():
                if value.state != "completed" and not any(item.severity == "error" for item in value.findings):
                    findings.append(HealthFinding(rule_id="RULE.EXECUTION.UNAVAILABLE",severity="error",object_type="plugin",
                        object_id=resource.id,message=f"rule '{invocation_id}' did not complete ({value.state})",
                        source_location={"path":str(path),"line":1},details={"state":value.state,"phase":phase}))
    except RuleGraphError as error:
        findings.append(graph_error_finding(registry,error,object_type="plugin",object_id=resource.id,
                                            fallback_path=resource.source_path or str(path)))
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


def review_reached_base_libs(registry, sources, *, rules, rulesets, handlers, phase, purity_policy=None):
    """Select only declared libraries in the actual Node import closure."""
    from dataclasses import replace
    from vibeflow.targets.python.quality.project_context import project_rule_facts
    findings, executions = [], []
    for descriptor, source, origin in reached_base_lib_sources(registry, sources):
        library_sources = build_python_source_context((), sources.import_closure(source.path))
        cache = {}
        for selected in descriptor.rulesets:
            try:
                plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
                custom = getattr(registry,"rule_handler_loader",None)
                if callable(custom):
                    handlers.update(custom(plan))
                context = RuleContext(facts={"source_context":library_sources,"base_lib_file":source,
                    "purity_policy":purity_policy, **project_rule_facts(plan,library_sources,cache)},
                    subject={"kind":"base_lib","id":descriptor.id,"descriptor":descriptor.to_dict(),
                        "source_identity":("python",source.path,tuple((file.path,file.text) for file in sources.import_closure(source.path)))},
                    scope={"files":tuple(file.path for file in sources.import_closure(source.path))}, phase=phase,target="python")
                result = execute_rule_plan(plan,context,handlers=handlers)
                executions.append(result)
                findings.extend(replace(item,root_id=item.root_id or source.root_id,source_path=item.source_path or source.path)
                                for item in result.findings)
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
