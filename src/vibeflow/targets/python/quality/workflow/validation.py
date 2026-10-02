"""Build facts, then execute explicitly selected workflow and Node rules."""
from __future__ import annotations
from dataclasses import dataclass, field
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
from vibeflow.targets.python.quality.workflow.rule_phase import execute_workflow_rules, workflow_invocations
from vibeflow.targets.python.quality.workflow.report import _build_health_report

@dataclass
class _HealthValidationState:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    node_metrics: dict = field(default_factory=dict)
    node_effect_scopes: dict = field(default_factory=dict)
    node_types: dict = field(default_factory=dict)
    node_similarities: dict = field(default_factory=dict)
    nodeset_findings: dict = field(default_factory=dict)
    fingerprints: dict = field(default_factory=dict)
    mainline: dict = field(default_factory=dict)
    rule_executions: list = field(default_factory=list)
    call_effect_policies: list = field(default_factory=list)


def validate_graph_health(graph, *, registry=None, boundary_registry=None, plugin_registry=None,
    global_config=None, purity_policy=None, effective_policy=None, nodeset_max_depth=4,
    source_context=None, rule_phase="static", quality_policy=None):
    from vibeflow.targets.python.project.compiler import GraphCompiler, GraphCompileError
    state = _HealthValidationState()
    if registry is not None:
        registry.configure_rule_defaults(purity_policy=purity_policy,quality_policy=quality_policy)
    execute_workflow_rules(graph, state, registry=registry, source_context=source_context, phase="import",
        purity_policy=purity_policy, quality_policy=quality_policy, nodeset_max_depth=nodeset_max_depth, global_config=global_config)
    if state.errors:
        return _build_health_report(graph, None, plugin_registry, state, effective_policy=effective_policy, rule_phase="import")
    source_report = None
    if registry is not None and source_context is not None:
        source_report = execute_python_node_rules(registry, source_context, phase=rule_phase, purity_policy=purity_policy, quality_policy=quality_policy)
        _append_findings(state, source_report.findings)
        state.rule_executions.extend(source_report.executions)
        state.call_effect_policies.extend({"owner":owner,"node":call,"policies":policies,
            "effect_scope":source_report.call_effect_scopes.get((owner,call),"unconstrained")}
            for (owner,call),policies in source_report.call_effect_policies.items())
    if rule_phase == "import":
        return _build_health_report(graph, None, plugin_registry, state, effective_policy=effective_policy, rule_phase="import")
    try:
        compilation = GraphCompiler().compile_with_findings(graph, registry=registry, plugin_registry=plugin_registry)
    except GraphCompileError as exc:
        return HealthReport(status="FAIL", errors=(HealthFinding(rule_id=exc.rule_id, severity="error",
            object_type="pipeline", object_id="pipeline", failure_layer="topology", message=str(exc), details=dict(exc.details or {})),))
    graph, compiled = compilation.workflow.graph, compilation.compiled_graph
    if registry is not None and source_context is not None:
        for call in source_context.calls:
            key = (call.owner,call.node_id)
            state.node_types[call.node_id] = call.type_key
            state.node_effect_scopes[call.node_id] = source_report.call_effect_scopes.get(key,
                source_report.effect_scopes.get(call.type_key,"unconstrained"))
            if key in source_report.call_node_metrics:
                state.node_metrics[call.node_id] = dict(source_report.call_node_metrics[key])
    execute_workflow_rules(graph, state, registry=registry, source_context=source_context, phase=rule_phase,
        purity_policy=purity_policy, quality_policy=quality_policy, nodeset_max_depth=nodeset_max_depth,
        global_config=global_config, compiled=compiled, compilation_findings=compilation.findings, source_report=source_report)
    return _build_health_report(graph, compiled, plugin_registry, state, effective_policy=effective_policy)


def workflow_graphs(graph):
    """The current workflow and actual Nodeset/Loop invocation closure."""
    return tuple((item.owner, item.graph) for item in workflow_invocations(graph))


def _append_findings(state, findings):
    for finding in findings:
        if not isinstance(finding,HealthFinding):
            finding = HealthFinding(rule_id=finding.code,severity=finding.severity,object_type=finding.object_type,
                object_id=finding.object_id,message=finding.message,source_location=finding.source_location,
                suggested_fix_type=finding.suggested_fix_type,details=finding.details,definition_id=finding.definition_id,
                root_id=finding.root_id,root_path=finding.root_path,source_path=finding.source_path,
                rule_source=f"rule:{finding.definition_id}" if finding.definition_id else "kernel.default_policy",
                failure_layer="implementation")
        (state.warnings if finding.severity in {"warning", "info"} else state.errors).append(finding)
        if finding.object_type == "nodeset":
            state.nodeset_findings.setdefault(finding.object_id, []).append(finding.to_dict())

__all__ = ["validate_graph_health", "workflow_graphs"]
