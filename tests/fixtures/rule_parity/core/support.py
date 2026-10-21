"""Observation formatting; never substitutes findings for a real API result."""

from __future__ import annotations
from dataclasses import replace


def plain(value):
    if hasattr(value, "items"):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [plain(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: plain(getattr(value, key)) for key in value.__dataclass_fields__}
    return value


def observe(operation):
    try:
        value = operation()
        if isinstance(value, dict):
            return value
        if hasattr(value, "errors") and hasattr(value, "warnings"):
            findings = (*value.errors, *value.warnings)
        elif hasattr(value, "findings"):
            findings = value.findings
        else:
            findings = tuple(value or ())
        diagnostics = tuple(item for item in findings if hasattr(item, "rule_id") or hasattr(item, "code"))
        codes = sorted({(str(getattr(item, "rule_id", getattr(item, "code", ""))),
            str(getattr(item, "severity", getattr(item, "details", {}).get("severity", "warning")))) for item in diagnostics})
        status = getattr(value, "status", None) or ("FAIL" if any(severity == "error" for _, severity in codes) else "CONCERNS" if codes else "PASS")
        metrics = {"finding_details": [{"code": getattr(item, "rule_id", getattr(item, "code", "")),
            "object_id": getattr(item, "object_id", ""), "details": plain(item.details)} for item in diagnostics],
            "finding_count": len(diagnostics)}
        if hasattr(value, "dependency_graph"):
            metrics.update(dependency_graph=plain(value.dependency_graph), longest_dependency_chain=plain(value.longest_dependency_chain),
                structure_summary=plain(value.structure_summary), prefix_clusters=plain(value.prefix_clusters))
        if hasattr(value, "compiled_graph"):
            compiled = value.compiled_graph
            metrics.update(order=list(compiled.order), schedule_edges=[list(edge.pair) for edge in compiled.resolved_schedule_edges],
                transfer_edges=[list(edge.pair) for edge in compiled.resolved_transfer_edges], flow_kinds=plain(compiled.flow_kinds))
        if hasattr(value, "info"):
            metrics["info"] = plain(value.info)
        return {"status": status, "codes": [{"code": code, "severity": severity} for code, severity in codes],
            "positions": [{"code": getattr(item, "rule_id", getattr(item, "code", "")), **plain(item.source_location)}
                for item in diagnostics if getattr(item, "source_location", {})],
            "metrics": metrics, "message": "; ".join(item.message for item in diagnostics)}
    except Exception as error:
        return {"status": "ERROR", "codes": [{"code": str((getattr(error, "rule_id", None) or getattr(error, "code", None) or type(error).__name__)), "severity": "error"}],
            "positions": [], "metrics": {"exception": type(error).__name__, "details": plain(getattr(error, "details", {}))}, "message": str(error)}


def expectation(*codes, **extra):
    return {"codes": [{"code": code, "severity": severity} for code, severity in codes], "exact_codes": True, **extra}


def append(rows, case_id, title, family, operation, expected, *, classification="preserved", notes="", evidence=""):
    rows.append({"id": "core.variant." + case_id, "title": title, "family": family,
        "expected": expected, "actual": observe(operation), "classification": classification, "notes": notes, "evidence": evidence})

def evaluate_standard_project_quality(facts, policy=None, **kwargs):
    from vibeflow.targets.python.rules.source_quality import bound_source_quality_defaults
    from vibeflow.targets.shared.quality_support import evaluate_source_quality
    from vibeflow.targets.shared.bindings import native_binding
    from vibeflow.tooling.project.resources import load_builtin_plugins
    catalog = load_builtin_plugins("python").catalogs
    handlers = {item.id:native_binding(catalog,"rule",item.id) for item in catalog.rules}
    handlers.update(kwargs.pop("handlers", {}) or {})
    declared = {item.id:item for item in catalog.rules}
    defaults = bound_source_quality_defaults(handlers, policy, rules=declared, origins=catalog.origins)
    rules = {item.id:replace(item,params_defaults={**item.params_defaults,**defaults.get(item.id,{})})
             for item in catalog.rules}
    extra = kwargs.pop("rules", ()) or ()
    rules.update(extra if hasattr(extra,"items") else {item.id:item for item in extra})
    rulesets = {item.id:item for item in catalog.rulesets}
    extra = kwargs.pop("ruleset_catalog", ()) or ()
    rulesets.update(extra if hasattr(extra,"items") else {item.id:item for item in extra})
    selected = kwargs.pop("rulesets", ("vibeflow.quality.source",))
    return evaluate_source_quality(facts,policy,rulesets=selected,rules=rules,
        ruleset_catalog=rulesets,handlers=handlers,**kwargs)


def boundary_registry(graph, registry):
    """Bind explicit terminal contracts in current formal fact probes.

    Historical baseline adapters still construct their old native boundaries;
    this helper is called only for the current kernel. No business IO executes.
    """
    from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
    class Boundary:
        def run_pure(self, inputs, params):
            return {}
    pending, visited, declared = [graph], set(), set(registry.available())
    while pending:
        current = pending.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        pending.extend(item.graph for item in current.nodeset_types.values())
        for call in current.nodes:
            if not (call.definition_id.startswith("probe.boundary.") or call.definition_id in {"probe.start", "probe.end"}) or call.definition_id in declared:
                continue
            declared.add(call.definition_id)
            registry.register(NodeDescriptor(call.definition_id, "Boundary", "Explicit fact-probe boundary.", "1.0.0", call.flow_kind or "terminal",
                contract=NodeContractDescriptor(requires=call.requires,provides=call.provides,
                    input_semantics={item.type:("Boundary input",) for item in call.requires},
                    output_semantics={item.key:("Boundary output",) for item in call.provides}),rulesets=(), node_type="vibeflow.node"), Boundary)
    return registry
