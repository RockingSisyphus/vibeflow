"""Policy Record handlers and extraction shared by the two Rule adapters."""
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.core.rules.models import plain
from vibeflow.core.workflows.policies import POLICY_TYPE, fold_policies


def allow(context, inputs, params):
    path = context.subject.get("call_path")
    if not path:
        return RuleResult()
    actions = plain(params.get("actions", ()))
    if not actions and params["capability"] in {"vibeflow.workflow", "vibeflow.port"}:
        actions = [{"operation": name} for name in params["operations"]]
    return RuleResult({"policy": RuleRecord(POLICY_TYPE, {"mode": "allow",
        "call_path": list(path), "capability": params["capability"],
        "operations": list(params["operations"]), "actions": actions})})


def restrict(context, inputs, params):
    return RuleResult({"policy": RuleRecord(POLICY_TYPE, {"mode": "restrict",
        "graph_paths": plain(context.scope.get("graph_paths", (context.subject.get("call_path", ()),))),
        "capabilities": list(params["capabilities"])})})


def policies_from_executions(executions, call_paths):
    records = [record.value for execution in executions for result in execution.results.values()
        if result.state == "completed" for record in result.records.values() if record.type_id == POLICY_TYPE]
    return fold_policies(records, call_paths)


def handlers():
    return {"vibeflow.capability.allow": allow, "vibeflow.capability.restrict": restrict}


def policy_findings(graph, policies, descriptor, *, global_config=None, effective_params=None):
    """Check declarations against graph restrictions and per-call grants."""
    from vibeflow.core.graph_calls import graph_call_subjects
    from vibeflow.core.findings import HealthFinding
    findings = []
    for subject in graph_call_subjects(graph, global_config=global_config):
        for node in subject.graph.nodes:
            path = (*subject.call_path, node.id)
            constraints = policies.get(path, {}).get("capabilities", {})
            declared = descriptor(node.definition_id)
            if declared is None:
                continue
            for required in declared.capabilities:
                if required.id not in constraints:
                    continue
                missing = set(required.operations) - set(constraints[required.id])
                if missing or not required.operations and not constraints[required.id]:
                    findings.append(HealthFinding(rule_id="GRAPH.CAPABILITY.DENIED", severity="error",
                        object_type="node", object_id="/".join(path),
                        definition_id="vibeflow.capability.restrict",
                        message=f"call '{'/'.join(path)}' has no Rule grant for {required.id}: {sorted(missing) or 'all operations'}",
                        details={"call_path": list(path), "capability": required.id, "operations": sorted(missing)}))
        nodes = {node.id: node for node in subject.graph.nodes}
        for node in subject.graph.nodes:
            path = (*subject.call_path, node.id)
            actions = policies.get(path, {}).get("actions", ())
            from vibeflow.core.workflows.references import node_workflow_actions, workflow_node_params
            params = (effective_params or {}).get(path, workflow_node_params(node, descriptor(node.definition_id), subject))
            try:
                node_workflow_actions(actions, params, root=graph.root_id)
            except ValueError as error:
                findings.append(HealthFinding(rule_id="WORKFLOW.CONFIG.INVALID", severity="error",
                    object_type="node", object_id="/".join(path), message=str(error),
                    details={"call_path":list(path)}))
            calls = [action for action in actions if action.get("capability") == "vibeflow.workflow" and action.get("operation") == "call"]
            if not calls or params.get("allow_background") is True or all(action.get("wait") is True for action in calls):
                continue
            providers = {provider.type for provider in node.provides}
            handled = any(
                edge.source == node.id and edge.target in nodes
                and providers & {required.type for required in nodes[edge.target].requires}
                and any(action.get("operation") in {"wait", "kill"} and action.get("capability") == "vibeflow.workflow"
                    for action in policies.get((*subject.call_path, edge.target), {}).get("actions", ()))
                for edge in subject.graph.edges)
            if not handled:
                findings.append(HealthFinding(rule_id="WORKFLOW.CALL.UNOBSERVED", severity="warning",
                    object_type="node", object_id="/".join(path), definition_id="vibeflow.capability.allow",
                    message="call has no directly confirmed downstream wait/kill; the author owns cleanup. Set allow_background: true to acknowledge long-lived work.",
                    details={"call_path": list(path), "actions": plain(calls)}))
    return tuple(findings)
