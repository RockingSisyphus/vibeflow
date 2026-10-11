"""Project review facts restricted to the existing source snapshot."""

from dataclasses import replace
import os
from pathlib import PurePath

from vibeflow.targets.shared.quality_support import ImportSite, ProjectQualityFacts, QualityPolicy, QualityThresholds
from vibeflow.targets.python.quality.source import PythonSource, analyze_python_source_tree, _syntax_error


def source_context_quality_facts(source_context):
    """Reuse parsed files; reading a Rule selection never discovers more files."""
    paths = tuple(PurePath(item.path) for item in source_context.files)
    root = PurePath(os.path.commonpath(tuple(str(path.parent) for path in paths))) if paths else PurePath(".")
    files, findings = [], []
    by_path = {item.path:item.module for item in source_context.files}
    for item in source_context.files:
        relative = PurePath(item.path).relative_to(root).as_posix()
        source = PythonSource(item.module, relative, item.path, item.text)
        if item._tree is None:
            error = SyntaxError(item.parse_error,(item.path,item.parse_line,item.parse_column,""))
            result = _syntax_error(source,len(item.text.splitlines()),len(item.text.encode("utf-8")),error)
        else:
            result = analyze_python_source_tree(source,item._tree)
        sites = tuple(ImportSite(item.module,by_path.get(import_.resolved_path,import_.module),item.text.splitlines()[import_.line-1].strip(),
            relative,import_.line,import_.column) for import_ in source_context.imports if import_.path == item.path)
        files.append(replace(result.file,imports=tuple(sorted({site.imported for site in sites})),import_sites=sites))
        findings.extend(result.findings)
    return ProjectQualityFacts(str(root),tuple(files),tuple(findings))


def source_quality_policy(purity_policy=None):
    """Use the current source defaults as explicit project Rule defaults."""
    if purity_policy is None:
        return QualityPolicy()
    values = {"max_file_lines":purity_policy.max_source_lines,"max_file_bytes":purity_policy.max_source_bytes,
        "warn_dependency_chain":purity_policy.warn_dependency_chain_length,"max_dependency_chain":purity_policy.max_dependency_chain_length}
    for source,target in (("warn_source_lines","warn_file_lines"),("max_functions","max_functions_per_file"),
        ("max_branches","max_file_branches"),("max_nesting_depth","max_function_nesting"),("max_params","max_function_params")):
        value = getattr(purity_policy,source)
        if value is not None:
            values[target] = value
    return QualityPolicy(thresholds=replace(QualityThresholds(),**values))


def project_rule_facts(plan,source_context,cache, *, handlers):
    from inspect import unwrap
    from vibeflow.targets.python.rules.project import project_quality_handlers
    native = tuple(project_quality_handlers().values())
    def needs_facts(invocation):
        handler = handlers.get(invocation.rule.handler or invocation.rule.id, handlers.get(invocation.rule.id))
        return callable(handler) and any(unwrap(handler) is check for check in native)
    if source_context is None or not any(needs_facts(item) for item in plan.invocations):
        return {}
    from vibeflow.targets.shared.facts import fact_key
    key = fact_key(tuple((item.path, item.text) for item in source_context.files))
    if key not in cache:
        cache[key] = source_context_quality_facts(source_context)
    return {"project_facts":cache[key]}


__all__ = ["source_context_quality_facts","source_quality_policy"]
