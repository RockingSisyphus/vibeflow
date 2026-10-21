"""Explicit, same-scope analysis and checks for the standard Workflow Ruleset."""
from dataclasses import replace

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleRecord, RuleResult
from vibeflow.targets.shared.rule_support.graph import _flow, _join, _nodesets, _duplicates, _planned

ANALYSIS = "vibeflow.graph_analysis.v1"


def graph_contexts(context, inputs):
    """Select only responsible graphs recorded by this plan's analysis."""
    available = context.facts.get("graphs", ({"graph": context.require("graph"),
        "compiled": context.facts.get("compiled"), "owner": context.facts.get("owner", "pipeline"), "call_path": ()},))
    wanted = {tuple(item["call_path"]) for item in inputs["analysis"].value["graphs"]}
    for item in available:
        if tuple(item["call_path"]) in wanted:
            yield replace(context, facts={**context.facts, **item})


def analysis(context, inputs, params):
    graphs = context.facts.get("graphs", ({"graph": context.require("graph"),
        "owner": context.facts.get("owner", "pipeline"), "call_path": ()},))
    return RuleResult({"graphs": RuleRecord(ANALYSIS, {"graphs": tuple(
        {"owner": item["owner"], "call_path": item["call_path"], "node_count": len(item["graph"].nodes)}
        for item in graphs), **_nodeset_analysis(context, graphs)})})


def _nodeset_analysis(context, graphs):
    """Analyze declaration relationships without fabricating execution calls."""
    from vibeflow.core.nodeset_dependencies import analyze_nodeset_dependencies, nodeset_dependency_cycles, nodeset_depth_violations
    from vibeflow.core.flow import LOOP_DEFINITION_IDS
    owned = {item["definition"].type_key: item["definition"] for item in graphs if item.get("definition") is not None}
    definitions = dict(owned)
    pending = list(owned.values())
    background = context.facts.get("global_graph", context.require("graph"))
    declaration_subtree = (context.subject.get("kind") == "nodeset_definition"
        and context.scope.get("graph_scope") == "effective_subtree")
    while pending:
        definition = pending.pop()
        graph = definition.graph
        for node in graph.nodes:
            key = node.loop.body if node.definition_id in LOOP_DEFINITION_IDS else node.definition_id
            child = graph.nodeset_types.get(key) or background.nodeset_types.get(key)
            if child is None or key in definitions:
                continue
            if declaration_subtree and child.graph.rulesets is None:
                definitions[key] = child
                pending.append(child)
            else:
                definitions[key] = replace(child, graph=replace(child.graph, nodes=(), edges=(), nodeset_types={}))
    graph = replace(context.require("graph"), nodeset_types=definitions)
    return {
        "nodeset_widths": tuple({"type_key":key, "node_count":len(item.graph.nodes),
            "call_paths":tuple(graph["call_path"] for graph in graphs
                if graph.get("definition") is not None and graph["definition"].type_key == key)
                if context.subject.get("kind") != "nodeset_definition" else ()}
            for key,item in owned.items()),
        "nodeset_cycles": tuple(cycle for cycle in nodeset_dependency_cycles(analyze_nodeset_dependencies(graph))
            if set(cycle) & owned.keys() and (not declaration_subtree or cycle[0] in owned)),
        "nodeset_depths": tuple(item.to_details() for item in nodeset_depth_violations(graph, max_depth=1)
            if item.chain[0] in owned),
    }


def topic(name):
    checker = {"flow": _flow, "join": _join, "nodeset_types": _nodesets, "duplicates": _duplicates, "planned": _planned}[name]
    def check(context, inputs, params):
        findings, events, unavailable = [], [], False
        for local in graph_contexts(context, inputs):
            if name == "duplicates" and not {"fingerprints", "node_metrics"} <= local.facts.keys():
                continue
            if name in {"flow", "join"} and local.facts.get("compiled") is None:
                unavailable = True
                continue
            # Nesting/width uses the analysis of responsible graphs; boundary
            # definitions deliberately contain no child implementation.
            if name == "nodeset_types":
                continue
            result = checker(local, {}, params)
            findings.extend(replace(item, details={**item.details, "owner": local.facts["owner"],
                "call_path": local.facts.get("call_path", ())}) for item in result.findings)
            if name == "planned":
                events.extend(result.records["events"].value)
        if name == "nodeset_types":
            measured = inputs["analysis"].value
            limit = params["nodeset_max_depth"]
            if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
                raise ValueError("nodeset max depth must be a positive integer")
            for item in measured["nodeset_widths"]:
                count = item["node_count"]
                if count > params["nodeset_warn_width"]:
                    findings.append(HealthFinding(rule_id="NODESET.SMELL.TOO_WIDE", severity="warning",
                        object_type="nodeset", object_id=item["type_key"],
                        failure_layer="topology", message=f"nodeset has {count} internal nodes; consider splitting it",
                        suggested_fix_type="fix_nodeset", details={"node_count": count, "limit": params["nodeset_warn_width"],
                            "call_paths":item["call_paths"]}))
            for cycle in measured["nodeset_cycles"]:
                findings.append(HealthFinding(rule_id="NODESET.RECURSION", severity="error",
                    object_type="nodeset", object_id=cycle[0], failure_layer="topology",
                    message="nodeset recursion is forbidden: " + " -> ".join(cycle),
                    suggested_fix_type="fix_nodeset", details={"cycle":cycle}))
            for item in measured["nodeset_depths"]:
                depth = item["actual_depth"]
                if depth > params["nodeset_max_depth"]:
                    findings.append(HealthFinding(rule_id="NODESET.NESTING.DEPTH_EXCEEDED", severity="error",
                        object_type="nodeset", object_id=item["chain"][0],
                        failure_layer="topology", message=f"nodeset nesting depth {depth} exceeds configured maximum {params['nodeset_max_depth']}",
                        suggested_fix_type="fix_nodeset", details={**item, "limit": params["nodeset_max_depth"]}))
        records = {"events": RuleRecord("vibeflow.planned_events.v1", events)} if name == "planned" else {}
        return RuleResult(records, tuple(findings), state="unavailable" if unavailable else "completed")
    return check


def review_graph(context):
    findings = []
    owner = context.facts.get("owner", "pipeline")
    for node in context.require("graph").nodes:
        if not node.id or node.id != node.id.lower() or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in node.id):
            findings.append(HealthFinding(rule_id="GRAPH.SMELL.CONFUSING_NODE_NAME", severity="warning",
                object_type="node", object_id=node.id, failure_layer="topology",
                message=f"node name should use lowercase snake_case: {node.id}"))
        for name in ("display_name", "description"):
            if not getattr(node.metadata, name, "").strip():
                findings.append(HealthFinding(rule_id="GRAPH.SMELL.MISSING_NODE_" + name.upper(), severity="warning",
                    object_type="node", object_id=node.id, failure_layer="topology",
                    message=f"config node '{node.id}' should declare {name} for readable SVG diagrams", details={"field": name, "owner": owner}))
    if owner == "pipeline":
        findings.extend(HealthFinding(rule_id=item.rule_id, severity=str(item.details.get("severity", "warning")),
            object_type="node", object_id=item.source, message=item.message, failure_layer="topology",
            details={**item.details, "source": item.source, "target": item.target})
            for item in context.facts.get("compilation_findings", ()))
    return tuple(findings)


def review(context, inputs, params):
    return RuleResult({"review": RuleRecord("vibeflow.workflow_review.v1", {"mainline": {}})},
        tuple(item for local in graph_contexts(context, inputs) for item in review_graph(local)))


def summary(context, inputs, params):
    return RuleResult({"planned_events": inputs["events"], "workflow_review": inputs["review"]})


def nodeset_types(context, inputs, params):
    return topic("nodeset_types")(context, inputs, params)
