"""Inspect effective rule plans without loading or executing business code."""

from __future__ import annotations

from vibeflow.core.rules.models import plain
from vibeflow.core.rules.selection import resolve_node_selection, selection_data
from vibeflow.core.rules.planning import graph_rule_selections, graph_rule_tasks
from vibeflow.tooling.project.graph_config import parse_graph_config

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Mapping

from vibeflow.core.rules import RuleGraphError, compile_ruleset
from vibeflow.tooling.project.config_loader import load_config_document, load_workspace_config_document
from vibeflow.tooling.project.resources import prepare_workflow_resources
from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace, load_workspace_config


def effective_rule_plans(config: Path, *, workspace=None, node_path: str = "", phase: str = "static") -> dict[str, object]:
    document = load_workspace_config_document(config, workspace=workspace) if workspace else load_config_document(config)
    owner = workspace.root_for_path(config) if workspace else None
    project_config = owner.config_path if owner else find_project_config(config)
    if project_config is None:
        raise ValueError(f"workflow has no owning project: {config}")
    active_workspace = workspace or load_project_workspace(project_config)
    if owner is None:
        owner = active_workspace.root_for_path(config)
    if owner is None:
        raise ValueError(f"workflow does not belong to a registered root: {config}")
    loaded = prepare_workflow_resources(active_workspace, config)
    catalogs = loaded.catalogs
    from vibeflow.targets.shared.bindings import native_binding
    handlers = {item.id:native_binding(catalogs, "rule", item.id) for item in catalogs.rules}
    rules = {item.id: item for item in catalogs.rules}
    rulesets = {item.id: item for item in catalogs.rulesets}
    if owner.project_target == "python":
        from vibeflow.tooling.application.python.rule_defaults import declared_rule_resources
        registry, rules, rulesets = declared_rule_resources(active_workspace, config, prepared_resources=loaded)
    defaults = _project_rule_defaults(owner, document=document, workspace=workspace, handlers=handlers,
        rules=rules, origins=catalogs.origins)
    for rule_id, params in defaults.items():
        rule = rules[rule_id]
        rules[rule_id] = replace(rule, params_defaults={**rule.params_defaults, **params})
    purity_policy = None
    project_target = owner.project_target
    if owner.project_target == "python":
        from vibeflow.tooling.application.python.rule_defaults import default_source_policy
        purity_policy = default_source_policy()
    def compiled_plan(selected):
        plan = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
        if project_target == "python":
            from vibeflow.tooling.application.python.rule_defaults import complete_rule_plan
            plan = complete_rule_plan(plan, purity_policy, handlers=handlers)
        return plan.to_dict()
    graph = parse_graph_config(document.data)
    graph_choices = graph_rule_selections(graph, rulesets)
    tasks = graph_rule_tasks(graph, rulesets)
    specs = {"/".join((*subject.call_path, spec.id)): spec for subject, _ in graph_choices
        if not subject.declaration_only for spec in subject.graph.nodes}
    calls = [(path, plain(spec)) for path, spec in specs.items()]
    if node_path:
        calls = [(path, call) for path, call in calls if path == node_path]
        if not calls:
            raise ValueError(f"unknown Node call path: {node_path}")
    output = []
    for path, call in calls:
        definition_id = str(call.get("definition_id", ""))
        descriptor = catalogs.nodes.get(definition_id)
        if descriptor is None:
            continue
        choice = resolve_node_selection(descriptor, specs[path])
        selection = choice.references
        plans = [compiled_plan(selected) for selected in selection]
        if any(plan["graph_scope"] == "effective_subtree" for plan in plans):
            raise RuleGraphError("RULE.GRAPH_SCOPE.NODE", "Node selections cannot use an effective_subtree Ruleset")
        output.append({"call": path, "definition_id": definition_id, "selection": choice.to_dict(),
                       "selection_source": choice.source,
                       "origin": catalogs.origins[("nodes", definition_id)].to_dict(),
                       "rulesets": selection_data(selection), "constraint_state": "selected" if selection else "unconstrained", "plans": plans})
    reached_libraries = set()
    if owner.project_target == "python":
        from vibeflow.tooling.application.python.rule_defaults import reached_library_ids
        reached_libraries = reached_library_ids(registry, {call.get("definition_id") for _, call in calls if call.get("status") != "planned"})
    resources = _resource_plans(catalogs, calls=calls, data=document.data, project=owner.project_config,
        compiled_plan=compiled_plan, reached_libraries=reached_libraries)
    workflow = [compiled_plan(task.reference) for task in tasks if task.subject.owner == "pipeline"]
    workflow_selection = next(choice for subject,choice in graph_choices if subject.owner == "pipeline")
    workflow_coverage = [{"graph_scope":task.graph_scope, "graph_paths":[list(item.call_path) for item in task.subjects],
        "boundaries":[list(value) for value in task.boundaries]} for task in tasks if task.subject.owner == "pipeline"]
    scopes = []
    for subject, choice in graph_choices:
        if subject.owner == "pipeline":
            continue
        path = "/".join(subject.call_path)
        if node_path and not subject.declaration_only and not node_path.startswith(path + "/"):
            continue
        # Subject instances come from separate Core enumerations; compare their
        # full call identity, including independent declaration checks.
        local_tasks = [task for task in tasks if (task.subject.owner, task.subject.call_path, task.subject.declaration_only)
            == (subject.owner, subject.call_path, subject.declaration_only)]
        scopes.append({"call": subject.owner if subject.declaration_only else path,
            "selection": choice.to_dict(), "rulesets": selection_data(choice.references),
            "plans": [compiled_plan(task.reference) for task in local_tasks],
            "coverage": [{"graph_scope": task.graph_scope, "graph_paths": [list(item.call_path) for item in task.subjects],
                "boundaries": [list(value) for value in task.boundaries]} for task in local_tasks],
            "constraint_state": "selected" if choice.references else "unconstrained"})
    return {"config": str(config.resolve()), "phase": phase, "workflow": workflow, "scopes": scopes, "nodes": output,
            "workflow_selection":workflow_selection.to_dict(), "workflow_coverage":workflow_coverage,
            "resources":resources, "project_rule_defaults": defaults,
            "plugins":plain(catalogs.plugin_records)}


def _resource_plans(catalogs, *, calls, data, project, compiled_plan, reached_libraries):
    def ids(values):
        return {value if isinstance(value,str) else value.get("id") for value in values
                if isinstance(value,str) or isinstance(value,Mapping) and value.get("enabled",True) is not False}
    selected = {"base_lib":set(reached_libraries), "plugin":ids(catalogs.lifecycle_selections)}
    for _, call in calls:
        descriptor = catalogs.nodes.get(call.get("definition_id", ""))
        if descriptor is not None and call.get("status") != "planned":
            selected["base_lib"].update(descriptor.base_libs)
    for kind,catalog in ([("plugin",catalogs.plugins)]):
        pending, visited = list(selected[kind]), set()
        while pending:
            key = pending.pop()
            descriptor = catalog.get(key)
            if descriptor is None or key in visited:
                continue
            visited.add(key)
            selected["base_lib"].update(descriptor.base_libs)
            pending.extend(descriptor.dependencies)
    from vibeflow.core.descriptors.source_bundle import source_resources
    declarations = [item for kind,item in source_resources(catalogs) if kind == "plugin_declaration"]
    for item in declarations:
        selected["base_lib"].update(item.base_libs)
    output = [{"kind":"plugin_declaration","id":item.id,"selection_source":item.implementations[0].source.ref,
        "rulesets":selection_data(item.rulesets),"constraint_state":"selected" if item.rulesets else "unconstrained",
        "plans":[compiled_plan(selection) for selection in item.rulesets]}
        for item in declarations]
    for kind, catalog in (("base_lib",catalogs.base_libs),("plugin",catalogs.plugins)):
        pending, visited = list(selected[kind]), set()
        while pending:
            key = pending.pop()
            if key in visited:
                continue
            visited.add(key)
            descriptor = catalog.get(key)
            if descriptor is None:
                continue
            pending.extend(descriptor.dependencies)
            output.append({"kind":kind,"id":key,"selection_source":catalog.source_for(key),
                "rulesets":selection_data(descriptor.rulesets), "constraint_state":"selected" if descriptor.rulesets else "unconstrained",
                "plans":[compiled_plan(selection) for selection in descriptor.rulesets]})
    return sorted(output,key=lambda item:(item["kind"],item["id"]))


def _project_rule_defaults(root, *, document, workspace, handlers, rules, origins):
    if root.project_target == "python":
        from vibeflow.tooling.application.python.rule_defaults import source_rule_defaults
        return source_rule_defaults(handlers, rules=rules, origins=origins)
    from vibeflow.tooling.application.javascript.rule_defaults import source_rule_defaults
    return source_rule_defaults(handlers, rules=rules, origins=origins)


def rule_plans_mermaid(payload: Mapping[str, object]) -> str:
    lines = ["flowchart TD", "  classDef rule fill:#dbeafe,stroke:#2563eb,color:#172554;"]
    groups = [("workflow", plan) for plan in payload["workflow"]]
    for scope in payload.get("scopes", ()):
        for plan in scope["plans"]:
            groups.append((scope["call"], plan))
    for node in payload["nodes"]:
        for plan in node["plans"]:
            groups.append((node["call"], plan))
    for resource in payload.get("resources", ()):
        for plan in resource["plans"]:
            groups.append((resource["kind"] + ":" + resource["id"], plan))
    for index, (owner, plan) in enumerate(groups):
        prefix = f"g{index}_"
        lines.append(f'  subgraph g{index}["{_label(owner)} · {_label(plan["ruleset_id"])}"]')
        local = {call["id"]: prefix + str(number) for number, call in enumerate(plan["calls"])}
        for call in plan["calls"]:
            label_lines = [call["id"], call["rule_id"]]
            if call.get("origins"):
                label_lines.append("origin: " + " → ".join(call["origins"]))
            for name, value in sorted(call["params"].items()):
                source = call.get("parameter_sources", {}).get(name)
                label_lines.append(name + "=" + _parameter_label(value))
                if source:
                    label_lines.append("source: " + str(source))
            label = _label("\\n".join(label_lines))
            lines.append(f'    {local[call["id"]]}["{label}"]:::rule')
        for relation in plan["relations"]:
            source, target = relation["source"], relation["target"]
            for value in (source, target):
                if value not in local:
                    local[value] = prefix + str(len(local))
                    lines.append(f'    {local[value]}["{_label(value)}"]')
            lines.append(f'    {local[source]} -->|"{relation["kind"]}"| {local[target]}')
        lines.append("  end")
    return "\n".join(lines) + "\n"


def _label(value: object) -> str:
    # Native SVG labels show Mermaid/HTML entities literally. JSON character
    # escapes keep arbitrary declaration text readable without creating markup.
    return str(value).replace("&", r"\u0026").replace('"', r"\u0022").replace("<", r"\u003c").replace(">", r"\u003e")


def _parameter_label(value: object) -> str:
    if isinstance(value, str):
        return value if value else "(empty string)"
    if isinstance(value, Mapping):
        return "{" + ", ".join(str(key) + "=" + _parameter_label(item) for key, item in sorted(value.items())) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_parameter_label(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="vibeflow review-rules", description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--node", default="", help="qualified invocation path, e.g. outer/inner")
    parser.add_argument("--phase", choices=("import", "static", "run"), default="static")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        workspace = load_workspace_config(args.workspace) if args.workspace else None
        payload = effective_rule_plans(args.config, workspace=workspace, node_path=args.node, phase=args.phase)
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n" if args.json else rule_plans_mermaid(payload)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            if args.output.suffix.lower() == ".svg":
                from vibeflow.tooling.presentation.mermaid import render_mermaid_svg
                render_mermaid_svg(rule_plans_mermaid(payload), args.output)
            else:
                args.output.write_text(text, encoding="utf-8")
        else:
            print(text, end="")
        return 0
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "ERROR", "code": getattr(exc, "code", getattr(exc, "rule_id", "RULE.REVIEW.FAILED")),
            "error": str(exc), "details": dict(getattr(exc, "details", {})),
            "diagnostics": list(getattr(exc, "diagnostics", ()))}, ensure_ascii=False))
        return 1
