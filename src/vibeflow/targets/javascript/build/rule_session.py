"""JavaScript Rule implementations hosted beside the language-neutral engine."""
from __future__ import annotations

from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.core.descriptors.source_bundle import source_resources, implementation_sources

from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from pathlib import Path
import json
import hashlib
from typing import Any, Mapping

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules import (
    RuleContext, RuleRecord, RuleResult, compile_ruleset, execute_rule_plan,
    EFFECT_POLICY_TYPE, RuleGraphError, rule_graph_error_finding,
)
from vibeflow.core.rules.models import plain
from vibeflow.core.rules.selection import resolve_node_selection
from vibeflow.core.rules.planning import graph_rule_subjects, graph_rule_tasks, scoped_graph
from vibeflow.builtin.project_quality import bound_project_quality_defaults
from vibeflow.core.quality import ProjectQualityFacts, QualityPolicy
from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError
from vibeflow.targets.javascript.frontend.plugin_descriptors import JavascriptPluginError
from vibeflow.targets.javascript.build.toolchain import run_rule_check_driver, run_quality_facts_driver
from vibeflow.targets.javascript.build.project_resources import driver_import_policy
from vibeflow.targets.javascript.build.graph_wire import graph_wire
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy, _file_fact, _finding_fact
from vibeflow.targets.shared.bindings import native_binding


def _compile_rule_plan(ruleset_id: str, *, catalogs: Any, entrypoint: str, rules: Any = None,
                       context: RuleContext | None = None, selection_source: str = ""):
    try:
        return compile_ruleset(ruleset_id, rules=catalogs.rules if rules is None else rules,
                               rulesets=catalogs.rulesets, entrypoint=entrypoint)
    except RuleGraphError as error:
        subject = context.subject if context is not None else {}
        owner = str(subject.get("type_key", subject.get("id", subject.get("workflow", ""))))
        finding = rule_graph_error_finding(error, rulesets=catalogs.rulesets,
            object_type="node_type" if "type_key" in subject else str(subject.get("kind", "ruleset")), object_id=owner)
        if context is not None:
            association = {name: plain(subject[name]) for name in ("type_key", "call_paths") if name in subject}
            finding = replace(finding, details={**finding.details, **association})
            if "type_key" in subject:
                selection_source = catalogs.nodes.source_for(owner)
            elif subject.get("kind") in {"base_lib", "plugin", "host_extension"}:
                catalog = {"base_lib": catalogs.base_libs, "plugin": catalogs.plugins,
                           "host_extension": catalogs.host_extensions}[subject["kind"]]
                selection_source = catalog.source_for(owner) or selection_source
            else:
                selection_source = str(subject.get("workflow", context.scope.get("workflow", ""))) or selection_source
        if not finding.source_location and selection_source:
            finding = replace(finding, source_location={"path": selection_source, "line": 1, "column": 1}, source_path=selection_source)
        raise ProjectBuildError(error.code, error.message, diagnostics=(finding.to_dict(),)) from error


@dataclass(frozen=True)
class JavascriptRuleReport:
    results: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    policies: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)
    call_effect_scopes: Mapping[tuple[str, ...], str] = field(default_factory=dict)
    call_effect_policies: Mapping[tuple[str, ...], tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    source_scopes: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    selections: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"subjects": {key: [item.to_dict() for item in value] for key, value in self.results.items()},
                "findings": [item.common_dict() for item in self.findings], "selections":plain(self.selections),
                "effect_policies": plain(self.policies),
                "call_effect_policies": [{"node_type": path[0], "call_path": list(path[1:]), "effect_scope": self.call_effect_scopes[path], "records": plain(records)} for path, records in sorted(self.call_effect_policies.items())],
                "unconstrained": [key for key, executions in self.results.items() if not key.startswith("workflow:") and not any(item.plan.invocations for item in executions)],
                "unconstrained_effects": [key for key in self.results if not key.startswith("workflow:") and key not in self.policies], "facts": plain(self.facts)}


def _policy_scope(policy: Mapping[str, Any]) -> str:
    if policy.get("effect_scope"):
        return str(policy["effect_scope"])
    scopes = {"terminal" if item == "io" else str(item) for item in policy.get("allowed_effects", ())}
    return next(iter(scopes)) if len(scopes) == 1 else "mixed" if scopes else "none"


def _summarize_policies(records: list[Mapping[str, Any]], *, type_wide: bool = False) -> Mapping[str, Any]:
    # Multiple Rules are simultaneous constraints. Their records remain separate;
    # a summary is only a display fact, never a union of permission grants.
    values = [record["value"] for record in records]
    scopes = {_policy_scope(value) for value in values}
    scope = next(iter(scopes)) if len(scopes) == 1 else "mixed"
    if type_wide and any(record["scope"] == "call" for record in records):
        scope = "mixed"
    same = all(value == values[0] for value in values)
    return {**(values[0] if same else {}), "effect_scope": scope, "records": records}


def node_type_calls(graph: Any) -> dict[str, list[tuple[str, ...]]]:
    result: dict[str, list[tuple[str, ...]]] = {}
    for subject in graph_rule_subjects(graph):
        if subject.declaration_only or subject.definition is not None and subject.definition.status == STATUS_PLANNED:
            continue
        for node in subject.graph.nodes:
            if node.status == STATUS_PLANNED:
                continue
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            if target not in subject.available_nodesets:
                result.setdefault(node.type_used, []).append((*subject.call_path, node.id))
    return result


def _call_specs(graph: Any) -> dict[tuple[str, ...], Any]:
    return {(*subject.call_path, node.id):node for subject in graph_rule_subjects(graph)
        if not subject.declaration_only for node in subject.graph.nodes}


def _workflow_blocks(graph: Any, *, include_declarations: bool = False):
    for item in graph_rule_subjects(graph):
        if include_declarations or not item.declaration_only:
            yield item.graph, None if item.declaration_only else item.call_path


def _rule_wire_facts(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Encode the native shared Nodeset registry as finite declarations and refs."""
    def encode(key, value):
        if key in {"graph", "global_graph", "declaration_graph"} and value is not None:
            return graph_wire(value, plain)
        if key == "definition" and value is not None:
            finite = replace(value, graph=replace(value.graph, nodesets={}))
            return {**plain(finite), "graph": graph_wire(value.graph, plain)}
        return plain(value)
    portable = {key: plain(value) for key, value in facts.items()
                if key not in {"graph", "global_graph", "declaration_graph", "definition", "graphs", "catalogs", "prefetched_quality", "analysis_cache"}}
    if "project_facts" not in portable and "analysis_cache" in facts:
        portable["project_facts"] = plain(facts["analysis_cache"].project_facts(facts))
    for key in ("graph", "global_graph", "declaration_graph", "definition"):
        if facts.get(key) is not None:
            portable[key] = encode(key, facts[key])
    if "graphs" in facts:
        portable["graphs"] = [{key: encode(key, value)
            for key, value in item.items()} for item in facts["graphs"]]
    return portable


def _closure_import_policy(policy: Mapping[str, Any], catalogs: Any, sources: list[Mapping[str, Any]], *, project_root: Path, target: str) -> Mapping[str, Any]:
    """Classify reached sources from declarations without inspecting unused code."""
    reached = {str(Path(item["path"]).resolve()) for item in sources}
    owners = [dict(item) for item in policy.get("owners", ())]
    node_base_libs = dict(policy.get("node_base_libs", {}))
    base_dependencies = dict(policy.get("base_lib_dependencies", {}))
    for kind, descriptor in source_resources(catalogs):
        for implementation in descriptor.implementations:
            if implementation.language not in {"javascript", "typescript"} or implementation.source.kind != "file":
                continue
            if target != "javascript" and target not in implementation.targets:
                continue
            resource_id = descriptor.id
            for role, locator in implementation_sources(implementation):
                path = str((project_root / locator.ref).resolve())
                if path not in reached:
                    continue
                owner = {"path":path, "kind":kind, "id":resource_id, "role":role,
                         "export":(locator.export or ("run" if kind == "node" else "")) if role == "entry" else "",
                         "completion":implementation.completion}
                if owner not in owners:
                    owners.append(owner)
            if kind == "node":
                node_base_libs[resource_id] = list(descriptor.base_libs)
            elif kind == "base_lib":
                base_dependencies[resource_id] = list(descriptor.dependencies)
    return {**policy, "owners": owners, "node_base_libs": node_base_libs, "base_lib_dependencies": base_dependencies}


def _finding(raw: Mapping[str, Any], rule_id: str, context: RuleContext) -> Finding:
    location = raw.get("source_location")
    if not isinstance(location, Mapping):
        location = {name: raw[name] for name in ("path", "line", "column") if name in raw}
        if raw.get("file"):
            location = {**location, "path": raw["file"]}
    details = dict(raw.get("details", {}))
    if isinstance(raw.get("owner"), Mapping):
        details["source_owner"] = plain(raw["owner"])
    rule = context.facts.get("catalogs").rules.get(rule_id) if context.facts.get("catalogs") is not None else None
    call_paths = context.subject.get("source_call_paths", ()) if rule is not None and rule.scope == "source" else context.subject.get("call_paths", ())
    details["rule_id"] = rule_id
    if "type_key" in context.subject:
        details["node_type"] = context.subject["type_key"]
    if context.subject.get("kind") != "nodeset_definition":
        details.setdefault("call_paths", plain(call_paths))
    default_subject = "node_type" if "type_key" in context.subject else context.subject.get("kind", "workflow")
    subject_id = context.subject.get("type_key", context.subject.get("id", context.subject.get("workflow", "")))
    return HealthFinding(
        code=str(raw.get("code", raw.get("rule_id", rule_id))),
        severity=raw.get("severity", "error"),
        subject_type=str(raw.get("subject_type", raw.get("object_type", default_subject))),
        subject_id=str(raw.get("subject_id", raw.get("object_id", subject_id))),
        message=str(raw.get("message", "Rule rejected implementation")),
        source_location=location, details=details, rule_source="rule:" + rule_id, failure_layer="implementation",
    )


class _AnalysisCache:
    """Reuse facts in one audit without sharing decisions across subjects."""
    def __init__(self):
        self.checks: dict[str, Any] = {}
        self.metrics: dict[str, Any] = {}

    def source_check(self, request: Mapping[str, Any], *, package_root: str, node_command: str):
        key = json.dumps(plain(request), sort_keys=True)
        if key not in self.checks:
            self.checks[key] = run_rule_check_driver(request, package_root=package_root, node_command=node_command)
        return self.checks[key]

    def quality_facts(self, request: Mapping[str, Any], *, package_root: str, node_command: str):
        key = json.dumps(plain(request), sort_keys=True)
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


def _source_check(context: RuleContext, topics: tuple[str, ...], rule_id: str, *, params: Mapping[str, Any] | None = None) -> tuple[Finding, ...]:
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
    return tuple(_finding(item, rule_id, context) for item in result.findings)



class _RuleSession:
    """Own one worker and one source service for a formal check session."""

    def __init__(self, stack: ExitStack, *, catalogs: Any, project_root: Path, package_root: Path, node_command: str, target: str):
        self.stack, self.catalogs = stack, catalogs
        self.project_root, self.package_root = project_root, package_root
        self.node_command, self.target = node_command, target
        self.worker: JavascriptPluginSession | None = None
        self.sessions: dict[str, str] = {}
        self.analysis_cache = _AnalysisCache()
        self.source_cache: dict[str, Any] = {}

    def execute(self, selected: tuple[str, ...], context: RuleContext, *, before_import: bool = False, private_context=None, selection=None) -> tuple[Any, ...]:
        results = []
        phases = ("import", context.phase) if before_import and context.phase != "import" else (context.phase,)
        for phase in phases:
            active_context = replace(context, phase=phase)
            for ruleset_id in selected:
                rules = {rule.id: rule for rule in self.catalogs.rules}
                for rule_id, defaults in context.facts.get("rule_defaults", {}).items():
                    if rule_id in rules:
                        rules[rule_id] = replace(rules[rule_id], params_defaults={**rules[rule_id].params_defaults, **defaults})
                plan = _compile_rule_plan(ruleset_id, rules=rules, catalogs=self.catalogs, entrypoint=phase, context=active_context)
                if context.subject.get("kind") == "node" and plan.graph_scope == "effective_subtree":
                    raise ProjectBuildError("RULE.GRAPH_SCOPE.NODE", "Node selections cannot use an effective_subtree Ruleset")
                handlers = {}
                for invocation in plan.invocations:
                    rule = invocation.rule
                    bound = native_binding(self.catalogs, "rule", rule.id)
                    if bound is not None:
                        origin = self.catalogs.origins.get(("rules", rule.id))
                        if private_context is not None and getattr(origin, "plugin_id", "") == "vibeflow.core":
                            def analyze(ctx, inputs, params, *, bound=bound):
                                subject = {key: value for key, value in private_context.subject.items() if key not in {"source_call_paths"}}
                                if ctx.subject.get("call_path") is None:
                                    subject = {key: value for key, value in subject.items() if key not in {"call_spec", "call_path", "call_paths"}}
                                return bound(replace(private_context, phase=ctx.phase, subject=subject), inputs, params)
                            handlers[rule.id] = analyze
                        else:
                            handlers[rule.id] = bound
                        continue
                    def handler(ctx: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any], *, rule=rule) -> RuleResult:
                        if not ctx.facts.get("evaluate_sources", True):
                            return RuleResult(state="unavailable")
                        implementations = [item for item in rule.implementations if item.execution_family == "javascript"]
                        if len(implementations) != 1:
                            raise ValueError(f"Rule '{rule.id}' requires exactly one compatible JavaScript/TypeScript implementation")
                        from vibeflow.targets.javascript.sdk.loading import contribution_session
                        worker = contribution_session(self.catalogs, "rules", rule.id)
                        if worker is None:
                            if self.worker is None:
                                self.worker = self.stack.enter_context(JavascriptPluginSession(node_command=self.node_command))
                            worker = self.worker
                        source = implementations[0].source
                        module = str((self.project_root / source.ref).resolve())
                        try:
                            if rule.id not in self.sessions:
                                session_id = f"rule:{id(self)}:{rule.id}"
                                worker.open_rule(session_id, rule={"id": rule.id, "module": module, "export": source.export or "check"}, package_root=self.package_root, target="node")
                                self.stack.callback(worker.close, session_id)
                                self.sessions[rule.id] = session_id
                            returned = worker.evaluate_rule(self.sessions[rule.id], context={"facts": _rule_wire_facts(ctx.facts), "subject": plain(ctx.subject), "scope": plain(ctx.scope), "phase": ctx.phase, "target": ctx.target}, params=plain(params), inputs={key: item.to_dict() for key, item in inputs.items()})
                        except JavascriptPluginError as error:
                            declaration = self.catalogs.rules.source_for(rule.id)
                            # Resource provenance has no syntax span: identify the containing declaration.
                            finding = _finding({"code": "RULE.EXECUTION", "message": f"rule '{rule.id}' failed: {error}",
                                "source_location": self.catalogs.rules.location_for(rule.id) or {"path": declaration or module},
                                "details": {"implementation": {"path": module, "export": source.export or "check"},
                                            "cause_code": error.code, "cause_details": error.details}}, rule.id, ctx)
                            return RuleResult(findings=(finding,), state="failed")
                        if not isinstance(returned, Mapping):
                            raise ValueError(f"Rule '{rule.id}' returned a non-object result")
                        return {"records": returned.get("records", {}), "findings": tuple(_finding(item, rule.id, ctx) for item in returned.get("findings", ())), "state": returned.get("state", "completed")}
                    handlers[rule.id] = handler
                result = execute_rule_plan(plan, active_context, handlers=handlers, source_cache=self.source_cache)
                result = replace(result, selection=selection.to_dict() if selection is not None else {}, scope=context.scope)
                if active_context.facts.get("evaluate_sources", True):
                    incomplete = []
                    invocations = {item.id: item for item in plan.invocations}
                    for invocation_id, returned in result.results.items():
                        if returned.state == "completed" or any(item.severity == "error" for item in returned.findings):
                            continue
                        definition = invocations[invocation_id].rule.id
                        finding = _finding({"code": "RULE.RESULT." + returned.state.upper(),
                            "message": f"Rule '{definition}' did not complete the {phase} check ({returned.state})",
                            "details": {"rule_call_id": invocation_id, "state": returned.state, "phase": phase}}, definition, active_context)
                        incomplete.append(replace(finding, definition_id=definition))
                    if incomplete:
                        result = replace(result, findings=(*result.findings, *incomplete))
                results.append(result)
                # Import failures prevent the later entrance from loading implementations.
                if phase == "import" and any(item.severity == "error" for item in result.findings):
                    return tuple(results)
        return tuple(results)


def _check_session(stack, **options):
    from vibeflow.targets.javascript.build.driver_session import current_scope
    scope = current_scope()
    if scope is None:
        return _RuleSession(stack, **options)
    key = (id(options["catalogs"]), str(options["project_root"]), str(options["package_root"]),
           options["node_command"], options["target"])
    if key not in scope.rule_sessions:
        scope.rule_sessions[key] = _RuleSession(scope.stack, **options)
    return scope.rule_sessions[key]


def run_javascript_rules(
    graph: Any, catalogs: Any, *, project_root: Path, package_root: Path,
    phase: str = "static", target: str = "javascript", import_policy: Mapping[str, Any] | None = None,
    node_command: str = "node", evaluate_sources: bool = True, include_registered: bool = False, prefetched_quality: Any = None,
    quality_policy: QualityPolicy | None = None,
) -> JavascriptRuleReport:
    """Evaluate descriptor selections; an empty selection remains unconstrained."""
    used = node_type_calls(graph)
    call_specs = _call_specs(graph)
    for subject in graph_rule_subjects(graph):
        if subject.declaration_only:
            for key in node_type_calls(subject.graph):
                used.setdefault(key, [])
    if include_registered:
        used.update({item.type_key: used.get(item.type_key, []) for item in catalogs.nodes})
    snapshot = {key: catalogs.nodes.require(key).to_dict() for key in sorted(used) if catalogs.nodes.get(key) is not None}
    report_facts = {**contribution_facts(catalogs), "node_types": snapshot, "import_policy": plain(import_policy or {})}
    results: dict[str, tuple[Any, ...]] = {}
    findings: list[Finding] = []
    diagnostic_indexes = {}
    policies: dict[str, Mapping[str, Any]] = {}
    policy_records: dict[str, list[Mapping[str, Any]]] = {}
    call_records: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    source_scopes: dict[str, Mapping[str, Any]] = {}
    choices = []
    rule_defaults = bound_project_quality_defaults(
        {item.id: native_binding(catalogs, "rule", item.id) for item in catalogs.rules},
        quality_policy or javascript_quality_policy(),
        rules={item.id:item for item in catalogs.rules}, origins=catalogs.origins)
    with ExitStack() as stack:
        session = _check_session(stack, catalogs=catalogs, project_root=project_root, package_root=package_root, node_command=node_command, target=target)
        subjects = [("node", key, catalogs.nodes.get(key), calls) for key, calls in sorted(used.items())]
        selected_resources = {(owner.get("kind"), owner.get("id")) for owner in (import_policy or {}).get("owners", ())}
        subjects.extend((kind, kind + ":" + item.id, item, []) for kind,item in source_resources(catalogs)
                        if kind != "node" and (kind,item.id) in selected_resources)
        for kind, type_key, descriptor, calls in subjects:
            if descriptor is None:
                continue
            resource_id = descriptor.id
            sources = []
            for implementation in descriptor.implementations:
                source = implementation.source
                if implementation.language in {"javascript", "typescript"} and source.kind == "file" and (target == "javascript" or target in implementation.targets):
                    for role, locator in implementation_sources(implementation):
                        file = (project_root / locator.ref).resolve()
                        if file.is_file():
                            sources.append({"path":str(file), "text":file.read_text(encoding="utf-8"),
                                "export":(locator.export or "run") if role == "entry" else "", "role":role, "owner":type_key})
            source_files = [item["path"] for item in sources]
            selections = {call: resolve_node_selection(descriptor, call_specs.get(call)) for call in calls or [()]} if kind == "node" else {}
            selected = descriptor.rulesets if kind != "node" else tuple(ref for value in selections.values() for ref in value.references)
            local_sources = []
            local_quality = None
            if evaluate_sources and source_files:
                # Freeze the real import closure before any trusted Rule executes.
                # Fact extraction with no selected topics performs no review judgement.
                view_policy = _closure_import_policy(import_policy or {}, catalogs, sources, project_root=project_root, target=target)
                extracted = session.analysis_cache.source_check({"typecheckFiles": source_files, "ruleTopics": [],
                    "publicNodeView": kind == "node", "ruleSubjectId": resource_id, "ruleSubjectKind": kind,
                    "importPolicy": driver_import_policy(view_policy)}, package_root=str(package_root), node_command=node_command)
                local_sources = plain(extracted.local_sources)
                local_quality = extracted.local_quality
                for item in extracted.findings:
                    findings.append(HealthFinding(code=item["code"], severity=item.get("severity", "error"),
                        subject_type="file", subject_id=item.get("file", ""), message=item.get("message", ""),
                        source_location={"path":item.get("file", ""), "line":item.get("line", 1), "column":item.get("column", 1)},
                        failure_layer="implementation"))
                known = {item["path"] for item in sources}
                extracted_by_path = {item["path"]:plain(item) for item in extracted.sources}
                sources = [{**extracted_by_path.get(item["path"],{}), **item} for item in sources]
                sources.extend(plain(item) for item in extracted.sources if item["path"] not in known
                    and (Path(item["path"]).is_relative_to(project_root) or any(owner.get("path") == item["path"] for owner in view_policy.get("owners", ()))))
            # Ownership is catalog metadata; only the reached source closure is read.
            source_policy = _closure_import_policy(import_policy or {}, catalogs, sources, project_root=project_root, target=target)
            facts = {**contribution_facts(catalogs), "node_types": snapshot, "sources": sources, "source_files": source_files,
                     "source_owners": plain(source_policy.get("owners", ())),
                     "package_root": str(package_root), "project_root": str(project_root), "node_command": node_command,
                     "rule_defaults": rule_defaults,
                     "import_policy": driver_import_policy(source_policy), "catalogs": catalogs, "evaluate_sources": evaluate_sources, "prefetched_quality": prefetched_quality, "analysis_cache": session.analysis_cache}
            source_scopes[type_key] = {key: plain(facts[key]) for key in ("sources", "source_files", "source_owners")}
            subject_results = []
            # Call rules keep callpoint identity; source rules receive the exact target,
            # source path and export identity for the engine's optional source cache.
            identities = [(str(target), item["path"], item.get("export", "run")) for item in sources if item["path"] in source_files]
            contexts = calls or [()]
            identity = (str(target), tuple(identities), hashlib.sha256(json.dumps({"sources": sources,
                "descriptor": descriptor.to_dict(), "owners": plain(source_policy.get("owners", ()))},
                sort_keys=True).encode("utf-8")).hexdigest())
            if kind == "node":
                local_paths = {item["path"] for item in local_sources}
                local_owners = [owner for owner in facts["source_owners"] if owner["path"] in local_paths
                    and (owner["kind"] != "node" or owner["id"] == resource_id)]
                public_facts = {"sources": local_sources, "source_files": [file for file in source_files if file in local_paths],
                    "node_types": {resource_id: descriptor.to_dict()}, "source_owners": local_owners,
                    "evaluate_sources": evaluate_sources}
                if local_quality is not None:
                    public_facts["project_facts"] = ProjectQualityFacts(root=str(project_root), files=tuple(_file_fact(item) for item in local_quality["files"]), findings=tuple(_finding_fact(item) for item in local_quality["findings"]))
                identity = (str(target), tuple(identities), hashlib.sha256(json.dumps({"sources": local_sources,
                    "descriptor": descriptor.to_dict()}, sort_keys=True).encode()).hexdigest())
            else:
                public_facts = facts
            for call in contexts:
                selection = selections[call] if kind == "node" else None
                if selection is not None:
                    choices.append({"kind":"node", "type_key":type_key, "call_path":call, "selection":selection.to_dict()})
                if kind == "node":
                    call_records.setdefault((type_key, *call), [])
                context = RuleContext(facts=public_facts, subject={**({"type_key":type_key} if kind == "node" else {"id":resource_id}), "kind":kind, "descriptor": descriptor.to_dict(),
                    "call_path": call, "call_paths": [call] if calls else [],
                    "call_spec": plain(call_specs.get(call)), "source_identity": identity},
                    scope={"files": tuple(item["path"] for item in public_facts.get("sources", ()))}, phase=phase, target=target)
                native_identity = hashlib.sha256(json.dumps({"initialization": [(source["path"], source.get("initialization", source["text"])) for source in sources], "owners": plain(source_policy.get("owners", ()))}, sort_keys=True).encode()).hexdigest()
                context = replace(context, subject={**context.subject, "source_cache_identities": {rule.id:(identity, native_identity) for rule in catalogs.rules if getattr(catalogs.origins.get(("rules",rule.id)), "plugin_id", "") == "vibeflow.core"}})
                private = replace(context, facts={**facts, "local_sources":local_sources, "local_quality":local_quality})
                executions = session.execute(selection.references if selection is not None else selected, context,
                    before_import=evaluate_sources, private_context=private if kind == "node" else None, selection=selection)
                subject_results.extend(executions)
                for result in executions:
                    invocations = {item.id: item for item in result.plan.invocations}
                    for invocation_id, returned in result.results.items():
                        invocation = invocations[invocation_id]
                        for finding in returned.findings:
                            from vibeflow.core.rules.fingerprint import record_inputs_fingerprint, value_fingerprint
                            inputs = {name: result.results[provider].records[port]
                                for name, (provider, port) in invocation.inputs.items()
                                if port in result.results[provider].records}
                            key = (type_key, invocation.rule.id, value_fingerprint(invocation.params),
                                record_inputs_fingerprint(inputs), value_fingerprint(finding.common_dict()),
                                call if invocation.rule.scope == "call" else ())
                            paths = [list(call)] if calls else []
                            if key in diagnostic_indexes:
                                index = diagnostic_indexes[key]
                                old = findings[index]
                                paths = list(old.details.get("call_paths", ())) + [path for path in paths if path not in old.details.get("call_paths", ())]
                                findings[index] = replace(old, details={**old.details, "call_paths": paths})
                            else:
                                diagnostic_indexes[key] = len(findings)
                                findings.append(replace(finding, details={**finding.details, "call_paths": paths}))
                    findings.extend(replace(item, details={**item.details, "call_paths":[list(call)] if calls else []}) for item in result.findings
                        if item not in tuple(diagnostic for value in result.results.values() for diagnostic in value.findings))
                    for invocation_id, returned in result.results.items():
                        if returned.state != "completed":
                            continue
                        invocation = invocations[invocation_id]
                        for record in returned.records.values():
                            if record.type_id != EFFECT_POLICY_TYPE or not isinstance(record.value, Mapping):
                                continue
                            evidence = {"definition_id": invocation.rule.id, "rule_call_id": invocation_id,
                                        "scope": invocation.rule.scope, "value": plain(record.value),
                                        "call_path": list(call), "node_type": type_key,
                                        "cached": invocation_id not in result.executed}
                            policy_records.setdefault(type_key, []).append(evidence)
                            call_records.setdefault((type_key, *call), []).append(evidence)
            results[type_key] = tuple(subject_results)
    policies = {key: _summarize_policies(records, type_wide=True) for key, records in policy_records.items()}
    call_scopes = {path: str(_summarize_policies(records)["effect_scope"]) if records else "unconstrained" for path, records in call_records.items()}
    for key,policy in tuple(policies.items()):
        if len({scope for path,scope in call_scopes.items() if path[0] == key}) > 1:
            policies[key] = {**policy, "effect_scope":"mixed"}
    return JavascriptRuleReport(results, tuple(findings), policies, report_facts, call_scopes,
                                {path: tuple(records) for path, records in call_records.items()}, source_scopes, tuple(choices))


def run_javascript_workflow_rules(graph: Any, catalogs: Any, *, compiled_by_path: Mapping[tuple[str, ...], Any], node_report: JavascriptRuleReport, project_root: Path, package_root: Path, target: str = "javascript", node_command: str = "node", evaluate_sources: bool = True, rule_defaults: Mapping[str, Mapping[str, Any]] | None = None, quality_policy: QualityPolicy | None = None, phase: str = "static", compiled_nodesets: Mapping[str, Any] | None = None) -> JavascriptRuleReport:
    """Execute Core's range plan; native compilation remains independent."""
    results, findings = dict(node_report.results), list(node_report.findings)
    from vibeflow.core.rules.planning import graph_rule_selections
    choices = (*node_report.selections, *({"kind":"graph", "owner":subject.owner,
        "call_path":subject.call_path, "declaration_only":subject.declaration_only, "selection":choice.to_dict()}
        for subject,choice in graph_rule_selections(graph, {item.id:item for item in catalogs.rulesets})))
    metrics = {(key, tuple(execution.scope.get("call_path", ()))):plain(record.value)
        for key, executions in node_report.results.items() for execution in executions
        for returned in execution.results.values() for record in returned.records.values()
        if record.type_id == "vibeflow.node_metrics.v1"}
    def compiled_for(subject):
        return ((compiled_nodesets or {}).get(subject.owner.removeprefix("nodeset:"))
            if subject.declaration_only else compiled_by_path.get(subject.call_path))
    def graph_facts(task, subject):
        current = scoped_graph(task, subject)
        measured = {node.id:metrics[(node.type_used, (*subject.call_path, node.id))]
            for node in current.nodes if (node.type_used, (*subject.call_path, node.id)) in metrics}
        return {"graph": current, "owner": subject.owner, "call_path": subject.call_path,
            "node_types": {node.id: node.type_used for node in current.nodes},
            "definition": subject.definition, "declaration_graph":subject.graph,
            "node_metrics": measured,
            "fingerprints": {key: str(value["run_pure_fingerprint"]) for key, value in measured.items() if value.get("run_pure_fingerprint")},
            "node_similarities": {node.id: node.similar_to.to_dict() for node in current.nodes if node.similar_to.node},
            **({"compiled": compiled_for(subject)} if phase != "import" else {})}
    for choice in choices:
        if choice["kind"] == "graph":
            key = "definition:" + choice["owner"] if choice["declaration_only"] else "workflow:" + "/".join(choice["call_path"])
            results.setdefault(key, ())
    sources = {source["path"]: source for scope in node_report.source_scopes.values() for source in scope["sources"]}
    source_files = sorted({file for scope in node_report.source_scopes.values() for file in scope["source_files"]})
    owners = {json.dumps(owner, sort_keys=True): owner for scope in node_report.source_scopes.values() for owner in scope["source_owners"]}
    with ExitStack() as stack:
        session = _check_session(stack, catalogs=catalogs, project_root=project_root, package_root=package_root, node_command=node_command, target=target)
        for task in graph_rule_tasks(graph, {item.id: item for item in catalogs.rulesets}):
            subject = task.subject
            if phase != "import" and compiled_for(subject) is None:
                continue
            defaults = {**bound_project_quality_defaults(
                {item.id: native_binding(catalogs, "rule", item.id) for item in catalogs.rules},
                quality_policy or javascript_quality_policy(), rules={item.id: item for item in catalogs.rules},
                origins=catalogs.origins), **(rule_defaults or {})}
            responsible_types = {node.type_used for item in task.subjects for node in item.graph.nodes}
            local_scopes = [value for key,value in node_report.source_scopes.items() if key in responsible_types]
            local_sources = {source["path"]:source for value in local_scopes for source in value["sources"]}
            local_files = sorted({file for value in local_scopes for file in value["source_files"]})
            facts = {**contribution_facts(catalogs), **graph_facts(task, subject), "global_graph": graph,
                "graphs": tuple(graph_facts(task, item) for item in task.subjects),
                "sources": list(local_sources.values()), "source_files": local_files, "source_owners": list(owners.values()),
                "global_sources":list(sources.values()),
                "node_catalog": node_report.facts.get("node_types", {}),
                "import_policy": driver_import_policy(node_report.facts.get("import_policy", {})), "catalogs": catalogs,
                "project_root": str(project_root), "package_root": str(package_root), "node_command": node_command,
                "evaluate_sources": evaluate_sources, "rule_defaults": defaults, "analysis_cache": session.analysis_cache}
            context = RuleContext(facts=facts,
                subject={"kind": "nodeset_definition" if subject.declaration_only else "workflow",
                    "source_identity":hashlib.sha256(json.dumps({"graph_scope":task.graph_scope,"graph_paths":[item.call_path for item in task.subjects],"boundaries":task.boundaries,"facts":_rule_wire_facts({key:value for key,value in facts.items() if key not in {"analysis_cache","catalogs"}})},sort_keys=True).encode()).hexdigest(),
                    "id": subject.owner.removeprefix("nodeset:") if subject.declaration_only else str(subject.graph.source_path or subject.owner), "owner":subject.owner, "workflow": str(subject.graph.source_path or ""),
                    **({} if subject.declaration_only else {"call_path": subject.call_path, "call_paths": [subject.call_path]})},
                scope={"graph_scope": task.graph_scope, "graph_paths": tuple(item.call_path for item in task.subjects),
                    "call_path": subject.call_path, "boundaries": task.boundaries,
                    "files": tuple(sources)}, phase=phase, target=target)
            executions = session.execute((task.reference,), context, selection=task.selection)
            key = "definition:" + subject.owner if subject.declaration_only else "workflow:" + "/".join(subject.call_path)
            results[key] = (*results.get(key, ()), *executions)
            findings.extend(replace(item, details={**item.details, **({} if subject.declaration_only or item.details.get("call_paths") else {"call_paths":[list(subject.call_path)]})}) for result in executions for item in result.findings)
            if phase == "import" and any(item.severity == "error" for result in executions for item in result.findings):
                break
    return JavascriptRuleReport(results, tuple(findings), node_report.policies, node_report.facts,
        node_report.call_effect_scopes, node_report.call_effect_policies, node_report.source_scopes, choices)


__all__ = ["JavascriptRuleReport", "run_javascript_rules", "run_javascript_workflow_rules", "node_type_calls"]


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
