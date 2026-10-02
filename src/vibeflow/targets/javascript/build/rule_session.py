"""JavaScript Rule implementations hosted beside the language-neutral engine."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
import json
import hashlib
from typing import Any, Mapping

from vibeflow.core.descriptors.categories import selected_node_rulesets
from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules import (
    RuleContext, RuleRecord, RuleResult, compile_ruleset, execute_rule_plan,
    EFFECT_POLICY_TYPE,
)
from vibeflow.core.rules.models import plain
from vibeflow.core.rules.builtin.workflow import workflow_rule_checks, workflow_topic_handlers
from vibeflow.core.rules.builtin import project_quality_rule_defaults
from vibeflow.core.rules.builtin.project_quality import project_quality_handlers
from vibeflow.core.quality import ProjectQualityFacts, QualityPolicy
from vibeflow.core.flow import LOOP_NODE_TYPES, STATUS_PLANNED
from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession
from vibeflow.targets.javascript.build.toolchain import run_rule_check_driver, run_quality_facts_driver
from vibeflow.targets.javascript.build.project_resources import driver_import_policy
from vibeflow.targets.javascript.build.quality_source import javascript_quality_policy, _file_fact, _finding_fact


@dataclass(frozen=True)
class JavascriptRuleReport:
    results: Mapping[str, tuple[Any, ...]] = field(default_factory=dict)
    findings: tuple[Finding, ...] = ()
    policies: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    facts: Mapping[str, Any] = field(default_factory=dict)
    call_effect_scopes: Mapping[tuple[str, ...], str] = field(default_factory=dict)
    call_effect_policies: Mapping[tuple[str, ...], tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    source_scopes: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {"subjects": {key: [item.to_dict() for item in value] for key, value in self.results.items()},
                "findings": [item.common_dict() for item in self.findings],
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
    def visit(block: Any, prefix: tuple[str, ...], active: tuple[str, ...]) -> None:
        for node in block.nodes:
            if node.status == STATUS_PLANNED:
                continue
            node_path = (*prefix, node.id)
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            nodeset = block.nodesets.get(target)
            if nodeset is not None:
                if nodeset.status != STATUS_PLANNED and target not in active:
                    visit(nodeset.graph, node_path, (*active, target))
            else:
                result.setdefault(node.type_used, []).append(node_path)
    visit(graph, (), ())
    return result


def _call_specs(graph: Any) -> dict[tuple[str, ...], Any]:
    result: dict[tuple[str, ...], Any] = {}
    def visit(block: Any, prefix: tuple[str, ...], active: tuple[str, ...]) -> None:
        for node in block.nodes:
            path = (*prefix, node.id)
            result[path] = plain(node)
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            nodeset = block.nodesets.get(target)
            if node.status != STATUS_PLANNED and nodeset is not None and nodeset.status != STATUS_PLANNED and target not in active:
                visit(nodeset.graph, path, (*active, target))
    visit(graph, (), ())
    return result


def _workflow_blocks(graph: Any):
    """Yield the root and actual Nodeset/Loop calls without loading unused blocks."""
    def visit(block: Any, path: tuple[str, ...], active: tuple[str, ...]):
        yield block, path
        for node in block.nodes:
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            nodeset = block.nodesets.get(target)
            if node.status != STATUS_PLANNED and nodeset is not None and nodeset.status != STATUS_PLANNED and target not in active:
                yield from visit(nodeset.graph, (*path, node.id), (*active, target))
    yield from visit(graph, (), ())


def _rule_wire_facts(facts: Mapping[str, Any]) -> Mapping[str, Any]:
    """Encode the native shared Nodeset registry as finite declarations and refs."""
    portable = {key: plain(value) for key, value in facts.items()
                if key not in {"graph", "catalogs", "prefetched_quality", "analysis_cache"}}
    graph = facts.get("graph")
    if graph is not None:
        def body(block):
            return {item.name: plain(getattr(block, item.name)) for item in fields(block) if item.name != "nodesets"}
        portable["graph"] = body(graph)
        portable["graph"]["nodesets"] = {
            key: {**{item.name: plain(getattr(nodeset, item.name)) for item in fields(nodeset) if item.name != "graph"},
                  "graph": {**body(nodeset.graph), "nodeset_refs": list(nodeset.graph.nodesets)}}
            for key, nodeset in graph.nodesets.items()
        }
    return portable


def _closure_import_policy(policy: Mapping[str, Any], catalogs: Any, sources: list[Mapping[str, Any]], *, project_root: Path, target: str) -> Mapping[str, Any]:
    """Classify reached sources from declarations without inspecting unused code."""
    reached = {str(Path(item["path"]).resolve()) for item in sources}
    owners = [dict(item) for item in policy.get("owners", ())]
    node_base_libs = dict(policy.get("node_base_libs", {}))
    base_dependencies = dict(policy.get("base_lib_dependencies", {}))
    for kind, resources in (("node", catalogs.nodes), ("base_lib", catalogs.base_libs),
                            ("host_extension", catalogs.host_extensions), ("plugin", catalogs.plugins)):
        for descriptor in resources:
            for implementation in descriptor.implementations:
                if implementation.language not in {"javascript", "typescript"} or implementation.source.kind != "file":
                    continue
                if target != "javascript" and target not in implementation.targets:
                    continue
                path = str((project_root / implementation.source.ref).resolve())
                if path not in reached:
                    continue
                resource_id = descriptor.type_key if kind == "node" else descriptor.id
                owner = {"path": path, "kind": kind, "id": resource_id,
                         "export": implementation.source.export or ("run" if kind == "node" else ""),
                         "completion": implementation.completion}
                if not any(item["path"] == path and item["kind"] == kind and item["id"] == resource_id for item in owners):
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
    details.update({"rule_id": rule_id, "node_type": context.subject.get("type_key", ""),
                    "call_paths": plain(call_paths)})
    default_subject = "node_type" if "type_key" in context.subject else "workflow"
    subject_id = context.subject.get("type_key", context.subject.get("workflow", ""))
    return HealthFinding(
        code=str(raw.get("code", raw.get("rule_id", rule_id))),
        severity=str(raw.get("severity", "error")),
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
        extracted = self.source_check({"typecheckFiles": roots, "ruleTopics": [], "sourceSnapshots": plain(facts.get("sources", ()))},
                                      package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")))
        sources = plain(extracted.sources)
        parsed = self.quality_facts({"qualityRoot": facts["project_root"], "qualityFiles": sorted(item["path"] for item in sources), "sourceSnapshots": sources},
                                    package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")))
        return ProjectQualityFacts(root=str(facts["project_root"]), files=tuple(_file_fact(item) for item in parsed.files),
                                   findings=tuple(_finding_fact(item) for item in parsed.findings))


def _source_check(context: RuleContext, topics: tuple[str, ...], rule_id: str) -> tuple[Finding, ...]:
    facts = context.facts
    if not topics or not facts.get("evaluate_sources", True):
        return ()
    result = facts["analysis_cache"].source_check(
        {"typecheckFiles": list(facts.get("source_files", ())), "ruleTopics": list(topics),
         "importPolicy": plain(facts.get("import_policy", {})), "sourceSnapshots": plain(facts.get("sources", ())),
         "ruleSubjectKind": "node", "ruleSubjectId": context.subject.get("type_key", "")},
        package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")),
    )
    return tuple(_finding(item, rule_id, context) for item in result.findings)


def builtin_javascript_handlers() -> Mapping[str, Any]:
    def project_handler(checker):
        def check(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
            if not context.facts.get("evaluate_sources", True):
                return RuleResult(state="unavailable")
            return checker(context, inputs, params)
        return check
    def effects(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        scope = str(params.get("effect_scope", "none"))
        topics = (() if scope == "global_state" else ("module_state",))
        if scope not in {"python_io", "terminal", "trusted"}:
            topics = (*topics, "host_io")
        findings = _source_check(context, topics, "vibeflow.no_side_effects")
        allowed = {"none": [], "terminal": ["terminal"], "python_io": ["python_io"], "global_state": ["global_state"], "trusted": ["trusted"]}.get(scope, [])
        return RuleResult(records={"effect_policy": RuleRecord("vibeflow.effect_policy.v1", {"effect_scope": scope, "allowed_effects": allowed})}, findings=findings)
    def interface(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        return RuleResult(findings=_source_check(context, ("completion",), "vibeflow.node_interface"))
    def imports(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        return RuleResult(findings=_source_check(context, ("purity", "imports", "ownership"), "vibeflow.import_side_effects"))
    def maintainability(context: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any]) -> RuleResult:
        from vibeflow.targets.javascript.quality.implementation import registered_implementation_requests, evaluate_registered_facts
        facts = context.facts
        if not facts.get("evaluate_sources", True):
            return RuleResult(state="unavailable")
        descriptor = facts["catalogs"].nodes.require(context.subject["type_key"])
        base_ids: set[str] = set()
        def visit(resource_id: str) -> None:
            if resource_id in base_ids:
                return
            base_ids.add(resource_id)
            resource = facts["catalogs"].base_libs.get(resource_id)
            if resource is not None:
                for dependency in resource.dependencies:
                    visit(dependency)
        for resource_id in descriptor.base_libs:
            visit(resource_id)
        selected_files = set(facts["source_files"])
        for source in facts.get("source_owners", ()):
            if source.get("kind") == "base_lib" and source.get("id") in base_ids:
                selected_files.add(source["path"])
        ownership, descriptors = registered_implementation_requests(facts["catalogs"], project_root=Path(facts["project_root"]), selected_files=tuple(selected_files))
        selected_ids = {context.subject["type_key"], *base_ids}
        ownership = [item for item in ownership if item["type_key"] in selected_ids]
        descriptors = {key: value for key, value in descriptors.items() if key[0] in selected_ids}
        extracted = facts.get("prefetched_quality") or facts["analysis_cache"].quality_facts({"qualityRoot": facts["project_root"], "qualityFiles": sorted({item["path"] for item in ownership}), "qualityImplementations": ownership}, package_root=facts["package_root"], node_command=str(facts.get("node_command", "node")))
        found = evaluate_registered_facts(extracted, ownership, descriptors, project_root=Path(facts["project_root"]), policy_data=plain(params.get("policy", {})))
        relative_files = {Path(item["path"]).relative_to(facts["project_root"]).as_posix() for item in ownership}
        metrics = {"files": [plain(item) for item in extracted.files if item["path"] in relative_files],
                   "implementations": [plain(item) for item in extracted.implementations if item["type_key"] in selected_ids]}
        return RuleResult(records={"metrics": RuleRecord("vibeflow.node_metrics.v1", metrics)}, findings=tuple(_finding(item.to_dict(), "vibeflow.maintainability", context) for item in found))
    return {"vibeflow.no_side_effects": effects, "vibeflow.node_interface": interface,
            "vibeflow.import_side_effects": imports, "vibeflow.maintainability": maintainability,
            "vibeflow.workflow": workflow_rule_checks, **workflow_topic_handlers(),
            **{key: project_handler(checker) for key, checker in project_quality_handlers().items()}}


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

    def execute(self, selected: tuple[str, ...], context: RuleContext, *, before_import: bool = False) -> tuple[Any, ...]:
        results = []
        phases = ("import", context.phase) if before_import and context.phase != "import" else (context.phase,)
        for phase in phases:
            active_context = RuleContext(facts=context.facts, subject=context.subject, scope=context.scope, phase=phase, target=context.target)
            for ruleset_id in selected:
                rules = {rule.id: rule for rule in self.catalogs.rules}
                for rule_id, defaults in context.facts.get("rule_defaults", {}).items():
                    if rule_id in rules:
                        rules[rule_id] = replace(rules[rule_id], params_defaults={**rules[rule_id].params_defaults, **defaults})
                plan = compile_ruleset(ruleset_id, rules=rules, rulesets=self.catalogs.rulesets, entrypoint=phase)
                project_handlers = project_quality_handlers()
                if active_context.facts.get("evaluate_sources", True) and any(
                    {item.rule.id, item.rule.handler, item.original_rule_id} & project_handlers.keys()
                    for item in plan.invocations
                ):
                    active_context = replace(active_context, facts={**active_context.facts,
                        "project_facts": self.analysis_cache.project_facts(active_context.facts)})
                handlers = dict(builtin_javascript_handlers())
                for invocation in plan.invocations:
                    rule = invocation.rule
                    if rule.id in handlers or rule.handler in handlers:
                        continue
                    def handler(ctx: RuleContext, inputs: Mapping[str, RuleRecord], params: Mapping[str, Any], *, rule=rule) -> RuleResult:
                        if not ctx.facts.get("evaluate_sources", True):
                            return RuleResult(state="unavailable")
                        implementations = [item for item in rule.implementations if item.language in {"javascript", "typescript"} and (self.target == "javascript" or self.target in item.targets)]
                        if len(implementations) != 1:
                            raise ValueError(f"Rule '{rule.id}' requires exactly one compatible JavaScript/TypeScript implementation")
                        if self.worker is None:
                            self.worker = self.stack.enter_context(JavascriptPluginSession(node_command=self.node_command))
                        if rule.id not in self.sessions:
                            source = implementations[0].source
                            session_id = f"rule:{rule.id}"
                            self.worker.open_rule(session_id, rule={"id": rule.id, "module": str((self.project_root / source.ref).resolve()), "export": source.export or "check"}, package_root=self.package_root, target=self.target)
                            self.sessions[rule.id] = session_id
                        returned = self.worker.evaluate_rule(self.sessions[rule.id], context={"facts": _rule_wire_facts(ctx.facts), "subject": plain(ctx.subject), "scope": plain(ctx.scope), "phase": ctx.phase, "target": ctx.target}, params=plain(params), inputs={key: item.to_dict() for key, item in inputs.items()})
                        if not isinstance(returned, Mapping):
                            raise ValueError(f"Rule '{rule.id}' returned a non-object result")
                        return RuleResult(records=returned.get("records", {}), findings=tuple(_finding(item, rule.id, ctx) for item in returned.get("findings", ())), state=str(returned.get("state", "completed")))
                    handlers[rule.id] = handler
                result = execute_rule_plan(plan, active_context, handlers=handlers, source_cache=self.source_cache)
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


def run_javascript_rules(
    graph: Any, catalogs: Any, *, project_root: Path, package_root: Path,
    phase: str = "static", target: str = "javascript", import_policy: Mapping[str, Any] | None = None,
    node_command: str = "node", evaluate_sources: bool = True, include_registered: bool = False, prefetched_quality: Any = None,
    quality_policy: QualityPolicy | None = None,
) -> JavascriptRuleReport:
    """Evaluate descriptor selections; an empty selection remains unconstrained."""
    used = node_type_calls(graph)
    call_specs = _call_specs(graph)
    if include_registered:
        used.update({item.type_key: used.get(item.type_key, []) for item in catalogs.nodes})
    snapshot = {key: catalogs.nodes.require(key).to_dict() for key in sorted(used) if catalogs.nodes.get(key) is not None}
    report_facts = {"node_types": snapshot, "categories": catalogs.categories.to_dict(), "import_policy": plain(import_policy or {})}
    results: dict[str, tuple[Any, ...]] = {}
    findings: list[Finding] = []
    policies: dict[str, Mapping[str, Any]] = {}
    policy_records: dict[str, list[Mapping[str, Any]]] = {}
    call_records: dict[tuple[str, ...], list[Mapping[str, Any]]] = {}
    source_scopes: dict[str, Mapping[str, Any]] = {}
    rule_defaults = project_quality_rule_defaults(quality_policy or javascript_quality_policy())
    workflow_import_sources = evaluate_sources and any(
        compile_ruleset(ruleset_id, rules=catalogs.rules, rulesets=catalogs.rulesets, entrypoint="import").invocations
        for block, _ in _workflow_blocks(graph) for ruleset_id in block.rulesets
    )
    with ExitStack() as stack:
        session = _RuleSession(stack, catalogs=catalogs, project_root=project_root, package_root=package_root, node_command=node_command, target=target)
        for type_key, calls in sorted(used.items()):
            descriptor = catalogs.nodes.get(type_key)
            if descriptor is None:
                continue
            sources = []
            for implementation in descriptor.implementations:
                source = implementation.source
                if implementation.language in {"javascript", "typescript"} and source.kind == "file" and (target == "javascript" or target in implementation.targets):
                    file = (project_root / source.ref).resolve()
                    if file.is_file():
                        sources.append({"path": str(file), "text": file.read_text(encoding="utf-8"), "export": source.export or "run", "owner": type_key})
            source_files = [item["path"] for item in sources]
            selected = selected_node_rulesets(descriptor, catalogs.categories)
            if evaluate_sources and source_files and (selected or workflow_import_sources):
                # Freeze the real import closure before any trusted Rule executes.
                # Fact extraction with no selected topics performs no review judgement.
                extracted = session.analysis_cache.source_check({"typecheckFiles": source_files, "ruleTopics": []}, package_root=str(package_root), node_command=node_command)
                known = {item["path"] for item in sources}
                sources.extend(plain(item) for item in extracted.sources if item["path"] not in known)
            # Ownership is catalog metadata; only the reached source closure is read.
            source_policy = _closure_import_policy(import_policy or {}, catalogs, sources, project_root=project_root, target=target)
            facts = {"node_types": snapshot, "sources": sources, "source_files": source_files,
                     "source_owners": plain(source_policy.get("owners", ())),
                     "package_root": str(package_root), "project_root": str(project_root), "node_command": node_command,
                     "rule_defaults": rule_defaults,
                     "import_policy": driver_import_policy(source_policy), "catalogs": catalogs, "evaluate_sources": evaluate_sources, "prefetched_quality": prefetched_quality, "analysis_cache": session.analysis_cache}
            source_scopes[type_key] = {key: plain(facts[key]) for key in ("sources", "source_files", "source_owners")}
            subject_results = []
            # Call rules keep callpoint identity; source rules receive the exact target,
            # source path and export identity for the engine's optional source cache.
            identities = [(str(target), item["path"], item.get("export", "run")) for item in sources if item["path"] in source_files]
            contexts = [(call, identity) for call in (calls or [()]) for identity in (identities or [(str(target), "", "")])]
            for call, identity in contexts:
                local_facts = {**facts, "source_files": [identity[1]] if identity[1] else source_files}
                context = RuleContext(facts=local_facts, subject={"type_key": type_key, "descriptor": descriptor.to_dict(), "call_path": call, "call_paths": [call] if calls else [], "source_call_paths": calls, "call_spec": call_specs.get(call), "source_identity": (*identity, hashlib.sha256(json.dumps({"sources": sources, "descriptor": descriptor.to_dict(), "node_types": snapshot, "owners": plain(source_policy.get("owners", ()))}, sort_keys=True).encode("utf-8")).hexdigest())}, scope={"workflow": str(graph.source_path or ""), "root": str(project_root)}, phase=phase, target=target)
                executions = session.execute(selected, context, before_import=evaluate_sources)
                subject_results.extend(executions)
                for result in executions:
                    findings.extend(result.findings)
                    invocations = {item.id: item for item in result.plan.invocations}
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
    call_scopes = {path: str(_summarize_policies(records)["effect_scope"]) for path, records in call_records.items()}
    return JavascriptRuleReport(results, tuple(findings), policies, report_facts, call_scopes,
                                {path: tuple(records) for path, records in call_records.items()}, source_scopes)


def run_javascript_workflow_rules(graph: Any, catalogs: Any, *, compiled_by_path: Mapping[tuple[str, ...], Any], node_report: JavascriptRuleReport, project_root: Path, package_root: Path, target: str = "javascript", node_command: str = "node", evaluate_sources: bool = True, rule_defaults: Mapping[str, Mapping[str, Any]] | None = None, quality_policy: QualityPolicy | None = None, phase: str = "static") -> JavascriptRuleReport:
    """Evaluate actual workflow calls with only the facts available at this phase."""
    results = dict(node_report.results)
    findings = list(node_report.findings)
    metrics = {key: plain(record.value) for key, executions in node_report.results.items() for execution in executions for returned in execution.results.values() for record in returned.records.values() if record.type_id == "vibeflow.node_metrics.v1"}
    workflow_blocks = tuple(_workflow_blocks(graph))
    source_call_paths: dict[int, list[tuple[str, ...]]] = {}
    for block, path in workflow_blocks:
        source_call_paths.setdefault(id(block), []).append(path)
    with ExitStack() as stack:
        session = _RuleSession(stack, catalogs=catalogs, project_root=project_root, package_root=package_root, node_command=node_command, target=target)
        for block, path in workflow_blocks:
            compiled = compiled_by_path.get(path)
            if phase == "import" or compiled is not None:
                selected_scopes = [node_report.source_scopes[key] for key in node_type_calls(block) if key in node_report.source_scopes]
                sources = {source["path"]: source for scope in selected_scopes for source in scope["sources"]}
                source_files = sorted({file for scope in selected_scopes for file in scope["source_files"]})
                source_paths = {str(Path(source["path"]).resolve()) for source in sources.values()}
                owners = {json.dumps(owner, sort_keys=True): owner for scope in selected_scopes for owner in scope["source_owners"] if str(Path(owner["path"]).resolve()) in source_paths}
                import_policy = {**node_report.facts.get("import_policy", {}), "owners": list(owners.values())}
                defaults = {**project_quality_rule_defaults(quality_policy or javascript_quality_policy()), **(rule_defaults or {})}
                facts = {"graph": block, "node_types": node_report.facts.get("node_types", {}), "node_metrics": metrics, "sources": list(sources.values()), "source_files": source_files, "source_owners": list(owners.values()), "import_policy": driver_import_policy(import_policy), "catalogs": catalogs,
                    "project_root": str(project_root), "package_root": str(package_root), "node_command": node_command, "evaluate_sources": evaluate_sources, "rule_defaults": defaults, "analysis_cache": session.analysis_cache}
                if compiled is not None:
                    facts["compiled"] = compiled
                context = RuleContext(facts=facts, subject={"workflow": str(block.source_path or ""), "call_paths": [path], "source_call_paths": source_call_paths[id(block)]}, scope={"root": str(project_root)}, phase=phase, target=target)
                executions = session.execute(tuple(block.rulesets), context)
                key = "workflow:" + "/".join(path)
                results[key] = (*results.get(key, ()), *executions)
                findings.extend(item for result in executions for item in result.findings)
                if phase == "import" and any(item.severity == "error" for result in executions for item in result.findings):
                    break
    return JavascriptRuleReport(results, tuple(findings), node_report.policies, node_report.facts,
                                node_report.call_effect_scopes, node_report.call_effect_policies, node_report.source_scopes)


__all__ = ["JavascriptRuleReport", "run_javascript_rules", "run_javascript_workflow_rules", "node_type_calls", "builtin_javascript_handlers"]
