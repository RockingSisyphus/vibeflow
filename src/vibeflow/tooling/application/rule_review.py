"""Inspect effective rule plans without loading or executing business code."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Mapping

from vibeflow.core.descriptors.categories import selected_node_rulesets
from vibeflow.core.rules import RuleGraphError, compile_ruleset
from vibeflow.core.rules.builtin import builtin_rule_resources
from vibeflow.tooling.project.config_loader import load_config_document, load_workspace_config_document
from vibeflow.tooling.project.descriptor_loader import load_project_descriptor_catalogs
from vibeflow.tooling.project.workspace_loader import find_project_config, load_project_workspace, load_workspace_config


def effective_rule_plans(config: Path, *, workspace=None, node_path: str = "", phase: str = "static") -> dict[str, object]:
    document = load_workspace_config_document(config, workspace=workspace) if workspace else load_config_document(config)
    owner = workspace.root_for_path(config) if workspace else None
    project_config = owner.config_path if owner else find_project_config(config)
    if project_config is None:
        raise ValueError(f"workflow has no owning project: {config}")
    if owner is None:
        owner = load_project_workspace(project_config).roots[0]
    catalogs = load_project_descriptor_catalogs(project_config.parent, project_config=project_config)
    builtin_rules, builtin_sets = builtin_rule_resources()
    rules = {item.id: item for item in builtin_rules}
    rulesets = {item.id: item for item in builtin_sets}
    _merge_definitions(rules, catalogs.rules, "Rule")
    _merge_definitions(rulesets, catalogs.rulesets, "Ruleset")
    # Keep the complete workspace for sibling resolution, without scanning unused source.
    if workspace:
        for root in workspace.roots:
            if root.path == project_config.parent:
                continue
            sibling = load_project_descriptor_catalogs(root.path, project_config=root.config_path)
            _merge_definitions(rules, sibling.rules, "Rule")
            _merge_definitions(rulesets, sibling.rulesets, "Ruleset")
            for category in sibling.categories:
                existing = catalogs.categories.get(category.id)
                if existing is None:
                    catalogs.categories.register(category, source=sibling.categories.source_for(category.id))
                elif existing != category:
                    raise ValueError(f"conflicting category declaration '{category.id}'")
            for descriptor in sibling.nodes:
                if catalogs.nodes.get(descriptor.id) is not None:
                    raise ValueError(f"duplicate Node declaration '{descriptor.id}' in workspace")
                catalogs.nodes.register(descriptor, source=sibling.nodes.source_for(descriptor.id))
    defaults = _project_rule_defaults(owner, document=document, workspace=workspace)
    for rule_id, params in defaults.items():
        rule = rules[rule_id]
        rules[rule_id] = replace(rule, params_defaults={**rule.params_defaults, **params})
    calls = list(_calls(document.data))
    if node_path:
        calls = [(path, call) for path, call in calls if path == node_path]
        if not calls:
            raise ValueError(f"unknown Node call path: {node_path}")
    output = []
    for path, call in calls:
        type_key = str(call.get("type_used", ""))
        descriptor = catalogs.nodes.get(type_key)
        if descriptor is None:
            continue
        selection = selected_node_rulesets(descriptor, catalogs.categories)
        plans = []
        for selected in selection:
            if selected not in rulesets:
                raise RuleGraphError("RULE.RESOURCE.UNKNOWN", f"unknown ruleset '{selected}'")
            plans.append(compile_ruleset(rulesets[selected], rules=rules, rulesets=rulesets, entrypoint=phase).to_dict())
        output.append({"call": path, "type_key": type_key, "category": descriptor.category,
                       "selection_source": "node" if descriptor.rulesets is not None else "category",
                       "rulesets": list(selection), "constraint_state": "selected" if selection else "unconstrained", "plans": plans})
    workflow = []
    for selected in document.data.get("rulesets", ("vibeflow.workflow",)):
        if selected not in rulesets:
            raise RuleGraphError("RULE.RESOURCE.UNKNOWN", f"unknown ruleset '{selected}'")
        workflow.append(compile_ruleset(rulesets[selected], rules=rules, rulesets=rulesets, entrypoint=phase).to_dict())
    scopes = []
    for owner, body in _called_bodies(document.data):
        if owner == "workflow":
            continue
        if node_path and not node_path.startswith(owner + "/"):
            continue
        selection = tuple(body.get("rulesets", ("vibeflow.workflow",)))
        plans = [compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase).to_dict() for selected in selection]
        scopes.append({"call": owner, "rulesets": list(selection), "plans": plans,
                       "constraint_state": "selected" if selection else "unconstrained"})
    return {"config": str(config.resolve()), "phase": phase, "workflow": workflow, "scopes": scopes, "nodes": output,
            "project_rule_defaults": defaults}


def _project_rule_defaults(root, *, document, workspace):
    if root.project_target == "python":
        from vibeflow.tooling.application.python.rule_defaults import source_rule_defaults
        defaults = source_rule_defaults(document, workspace=workspace)
        depth = root.runtime_options.get("nodeset_max_depth", 4)
    else:
        from vibeflow.tooling.application.javascript.rule_defaults import source_rule_defaults
        defaults = source_rule_defaults()
        javascript = root.project_config.get("javascript", {})
        if not isinstance(javascript, Mapping):
            raise ValueError("project javascript config must be an object")
        depth = javascript.get("nodeset_max_depth", 4)
    if not isinstance(depth, int) or isinstance(depth, bool) or depth <= 0:
        raise ValueError("project nodeset_max_depth must be a positive integer")
    return {**defaults,
            **{rule_id: {"nodeset_max_depth": depth}
               for rule_id in ("vibeflow.workflow", "vibeflow.graph.nodesets")}}


def _merge_definitions(values, catalog, kind):
    for descriptor in catalog:
        existing = values.get(descriptor.id)
        if existing is not None and existing != descriptor:
            raise ValueError(f"conflicting {kind} declaration '{descriptor.id}'")
        values[descriptor.id] = descriptor


def _called_bodies(data: Mapping[str, object]):
    def walk(body, prefix="workflow", inherited=None, active=()):
        definitions = dict(inherited or {})
        definitions.update({item["type_key"]: item for item in body.get("nodesets", ()) if isinstance(item, Mapping)})
        yield prefix, body
        for call in body.get("pipeline", {}).get("nodes", ()):
            target = call.get("type_used")
            if target in {"vibeflow.loop", "vibeflow.loop.while"}:
                target = call.get("loop", {}).get("body")
            if target in definitions and target not in active:
                path = ("" if prefix == "workflow" else prefix + "/") + str(call["id"])
                yield from walk(definitions[target], path, definitions, (*active, target))
    yield from walk(data)


def _calls(data: Mapping[str, object]):
    for owner, body in _called_bodies(data):
        prefix = "" if owner == "workflow" else owner + "/"
        for call in body.get("pipeline", {}).get("nodes", ()):
            yield prefix + str(call.get("id", "")), call


def rule_plans_mermaid(payload: Mapping[str, object]) -> str:
    lines = ["flowchart TD", "  classDef rule fill:#dbeafe,stroke:#2563eb,color:#172554;"]
    groups = [("workflow", plan) for plan in payload["workflow"]]
    for scope in payload.get("scopes", ()):
        for plan in scope["plans"]:
            groups.append((scope["call"], plan))
    for node in payload["nodes"]:
        for plan in node["plans"]:
            groups.append((node["call"], plan))
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
        print(json.dumps({"status": "ERROR", "code": getattr(exc, "code", getattr(exc, "rule_id", "RULE.REVIEW.FAILED")), "error": str(exc)}, ensure_ascii=False))
        return 1
