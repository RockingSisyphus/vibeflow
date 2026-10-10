"""Execute a resolved rule graph over supplied facts and typed records."""

from __future__ import annotations

import inspect
from copy import copy
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, MutableMapping

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.rules.graph import RuleInvocation, RulePlan
from vibeflow.core.rules.models import RuleContext, RuleRecord, RuleResult, plain, readonly
from vibeflow.core.rules.fingerprint import cacheable_record_value as _cacheable_record_value, record_inputs_fingerprint, value_fingerprint


RuleHandler = Callable[[RuleContext, Mapping[str, RuleRecord], Mapping[str, Any]], RuleResult]


@dataclass(frozen=True)
class RuleExecutionResult:
    plan: RulePlan
    results: Mapping[str, RuleResult]
    findings: tuple[Finding, ...] = ()
    executed: tuple[str, ...] = ()
    aliases: Mapping[str, str] = field(default_factory=dict)
    selection: Mapping[str, Any] = field(default_factory=dict)
    scope: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "results", readonly(self.results))
        object.__setattr__(self, "aliases", readonly(self.aliases))
        object.__setattr__(self, "selection", readonly(self.selection))
        object.__setattr__(self, "scope", readonly(self.scope))

    @property
    def status(self) -> str:
        if any(item.state != "completed" for item in self.results.values()):
            return "ERROR"
        findings = (*self.findings, *(item for result in self.results.values() for item in result.findings))
        if any(item.severity == "error" for item in findings):
            return "FAIL"
        return "CONCERNS" if any(item.severity == "warning" for item in findings) else "PASS"

    @property
    def records(self) -> Mapping[str, Mapping[str, RuleRecord]]:
        return readonly({key: value.records for key, value in self.results.items()})

    def to_dict(self) -> dict[str, object]:
        return {"status": self.status, "plan": self.plan.to_dict(),
                "results": {key: value.to_dict() for key, value in self.results.items()},
                "findings": [item.to_dict() for item in self.findings],
                "executed": list(self.executed), "aliases": plain(self.aliases),
                "selection": plain(self.selection), "scope": plain(self.scope)}


def _finding(invocation: RuleInvocation, code: str, message: str, **details: Any) -> HealthFinding:
    return HealthFinding(rule_id=code, severity="error", object_type="rule", object_id=invocation.id,
                         message=message, failure_layer="rule", rule_source=f"rule:{invocation.rule.id}",
                         details={"ruleset_path": list(invocation.origins), **details})


def _coerce_finding(value: Any, rule_id: str) -> Finding:
    if isinstance(value, Finding):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("rule findings must contain Finding or diagnostic objects")
    location = value.get("source_location", {})
    if not location and value.get("file"):
        location = {"path": value["file"], "line": value.get("line", 1), "column": value.get("column", 1)}
    definition_id = str(value.get("definition_id", value.get("rule_id", rule_id) if "code" in value else rule_id))
    return HealthFinding(rule_id=str(value.get("code", value.get("rule_id", rule_id))),
                         severity=value.get("severity", "error"),
                         object_type=str(value.get("object_type", value.get("subject_type", "rule"))),
                         object_id=str(value.get("object_id", value.get("subject_id", value.get("owner", rule_id)))),
                         message=str(value.get("message", "")), source_location=location,
                         rule_source=str(value.get("rule_source", f"rule:{rule_id}")),
                         failure_layer=str(value.get("failure_layer", "implementation")),
                         suggested_fix_type=str(value.get("suggested_fix_type", value.get("suggested_fix", ""))),
                         details=value.get("details", {}), root_id=str(value.get("root_id", "")),
                         root_path=str(value.get("root_path", "")), source_path=str(value.get("source_path", "")),
                         definition_id=definition_id)


def coerce_rule_result(value: Any, rule: Any) -> RuleResult:
    """Normalize Target wire results without treating findings as success flags."""
    if isinstance(value, RuleResult):
        result = value
    else:
        if not isinstance(value, Mapping):
            raise TypeError("rule handler must return RuleResult or a result object")
        records = {}
        raw_records = value.get("records", {})
        if not isinstance(raw_records, Mapping):
            raise TypeError("rule result records must be an object")
        for name, record in raw_records.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("output port names must be non-empty strings")
            if isinstance(record, RuleRecord):
                records[name] = record
            elif isinstance(record, Mapping) and "type_id" in record and "value" in record:
                records[name] = RuleRecord(record["type_id"], record["value"])
            else:
                record_type = rule.outputs.get(name)
                if record_type is None:
                    raise ValueError(f"undeclared output record '{name}'")
                records[name] = RuleRecord(record_type, record)
        result = RuleResult(records, tuple(_coerce_finding(item, rule.id) for item in value.get("findings", ())),
                            value.get("state", "completed"))
    for finding in result.findings:
        if not isinstance(finding.severity, str) or finding.severity not in {"error", "warning", "info"}:
            raise ValueError("finding severity must be error, warning or info")
    unknown = set(result.records) - set(rule.outputs)
    if unknown:
        raise ValueError(f"undeclared output records: {sorted(unknown)}")
    if result.state == "completed":
        missing = set(rule.outputs) - set(result.records)
        if missing:
            raise ValueError(f"missing output records: {sorted(missing)}")
    for name, record in result.records.items():
        if record.type_id != rule.outputs[name]:
            raise ValueError(f"output '{name}' has type '{record.type_id}', expected '{rule.outputs[name]}'")
    return result


def _key(invocation: RuleInvocation, inputs: Mapping[str, RuleRecord], context: RuleContext) -> str | None:
    identity = context.subject.get("source_cache_identities", {}).get(invocation.rule.id,
        context.subject.get("source_identity"))
    if invocation.rule.scope != "source" or identity is None:
        return None
    inputs_key = record_inputs_fingerprint(inputs)
    if inputs_key is None:
        return None
    return value_fingerprint((identity, context.target, context.phase, invocation.rule.id, invocation.params, inputs_key))


class _Execution:
    def __init__(self, plan: RulePlan, context: RuleContext, handlers: Mapping[str, RuleHandler], source_cache=None):
        self.plan, self.context, self.handlers = plan, context, handlers
        self.results: dict[str, RuleResult] = {}
        self.findings: list[Finding] = []
        self.executed: list[str] = []
        self.aliases: dict[str, str] = {}
        self.cache: dict[str, str] = {}
        self.source_cache = source_cache

    def prepare(self, invocation: RuleInvocation) -> tuple[Any, Mapping[str, RuleRecord], str | None] | None:
        unavailable = [key for key in invocation.dependencies if self.results[key].state != "completed"]
        if unavailable:
            self.accept(invocation, RuleResult(findings=(_finding(invocation, "RULE.INPUT.UNAVAILABLE",
                        f"providers did not produce available results: {', '.join(unavailable)}", providers=unavailable),), state="unavailable"))
            return None
        inputs = {name: self.results[provider].records[output] for name, (provider, output) in invocation.inputs.items()}
        cache_key = _key(invocation, inputs, self.context)
        if cache_key is not None and cache_key in self.cache:
            original = self.cache[cache_key]
            self.results[invocation.id] = self.results[original]
            self.aliases[invocation.id] = original
            return None
        if cache_key is not None and self.source_cache is not None and cache_key in self.source_cache:
            origin, result = self.source_cache[cache_key]
            self.results[invocation.id] = result
            self.aliases[invocation.id] = "session:" + origin
            self.cache[cache_key] = invocation.id
            return None
        handler = self.handlers.get(invocation.rule.handler or invocation.rule.id)
        if handler is None:
            handler = self.handlers.get(invocation.rule.id)
        if not callable(handler):
            self.accept(invocation, RuleResult(findings=(_finding(invocation, "RULE.HANDLER.UNAVAILABLE",
                        f"no handler supplied for '{invocation.rule.id}'"),), state="unavailable"))
            return None
        return handler, readonly(inputs), cache_key

    def context_for(self, invocation: RuleInvocation) -> RuleContext:
        if invocation.rule.scope == "source":
            # Shared source results must not depend on the current call.
            subject = {key: value for key, value in self.context.subject.items()
                       if key not in {"owner", "call_id", "call_spec", "call_path", "rule_call_id", "source_cache_identities", "source_call_paths"}}
            subject.pop("call_paths", None)
            return replace(self.context, facts={key: value for key, value in self.context.facts.items() if key != "call"},
                           subject=subject, scope={key: value for key, value in self.context.scope.items() if key != "workflow"})
        return replace(self.context, subject={**{key:value for key,value in self.context.subject.items()
            if key != "source_cache_identities"}, "rule_call_id": invocation.id})

    def accept(self, invocation: RuleInvocation, result: RuleResult, cache_key: str | None = None, *, executed: bool = False) -> None:
        diagnostics = []
        for diagnostic in result.findings:
            annotated = copy(diagnostic)
            object.__setattr__(annotated, "definition_id", invocation.rule.id)
            diagnostics.append(annotated)
        result = replace(result, findings=tuple(diagnostics))
        self.results[invocation.id] = result
        self.findings.extend(result.findings)
        if executed:
            self.executed.append(invocation.id)
        if cache_key is not None:
            self.cache[cache_key] = invocation.id
            if self.source_cache is not None and result.state == "completed":
                self.source_cache[cache_key] = (self.plan.ruleset_id + "/" + invocation.id, result)

    def fail(self, invocation: RuleInvocation, exc: Exception, cache_key: str | None) -> None:
        self.accept(invocation, RuleResult(findings=(_finding(invocation, "RULE.EXECUTION",
                    f"rule '{invocation.rule.id}' failed: {exc}"),), state="failed"), cache_key, executed=True)

    def finish(self) -> RuleExecutionResult:
        return RuleExecutionResult(self.plan, self.results, tuple(self.findings), tuple(self.executed), self.aliases)


def execute_rule_plan(plan: RulePlan, context: RuleContext, *, handlers: Mapping[str, RuleHandler],
                      source_cache: MutableMapping[str, tuple[str, RuleResult]] | None = None) -> RuleExecutionResult:
    """Run checks; an optional cache belongs to one explicit check session.

    Source identity must include the snapshot and configuration facts consumed
    by the handler. Without that supplied identity, no source result is reused.
    Call-scoped handlers never use the source cache.
    """
    execution = _Execution(plan, context, handlers, source_cache)
    for invocation in plan.invocations:
        prepared = execution.prepare(invocation)
        if prepared is None:
            continue
        handler, inputs, cache_key = prepared
        try:
            value = handler(execution.context_for(invocation), inputs, invocation.params)
            if inspect.isawaitable(value):
                if inspect.iscoroutine(value):
                    value.close()
                raise TypeError("async rule handler requires execute_rule_plan_async")
            execution.accept(invocation, coerce_rule_result(value, invocation.rule), cache_key, executed=True)
        except Exception as exc:
            execution.fail(invocation, exc, cache_key)
    return execution.finish()


async def execute_rule_plan_async(plan: RulePlan, context: RuleContext, *, handlers: Mapping[str, RuleHandler],
                                  source_cache: MutableMapping[str, tuple[str, RuleResult]] | None = None) -> RuleExecutionResult:
    execution = _Execution(plan, context, handlers, source_cache)
    for invocation in plan.invocations:
        prepared = execution.prepare(invocation)
        if prepared is None:
            continue
        handler, inputs, cache_key = prepared
        try:
            value = handler(execution.context_for(invocation), inputs, invocation.params)
            if inspect.isawaitable(value):
                value = await value
            execution.accept(invocation, coerce_rule_result(value, invocation.rule), cache_key, executed=True)
        except Exception as exc:
            execution.fail(invocation, exc, cache_key)
    return execution.finish()


__all__ = ["RuleExecutionResult", "RuleHandler", "coerce_rule_result", "execute_rule_plan", "execute_rule_plan_async"]
