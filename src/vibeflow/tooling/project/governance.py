"""Project/root Rule configuration and execution using the ordinary Rule engine."""

from dataclasses import dataclass, replace
from pathlib import Path
from os.path import relpath
from typing import Mapping

from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
from vibeflow.core.rules.models import readonly
from vibeflow.core.rules.selection import selection_refs
from vibeflow.tooling.project.config_loader import load_raw_config_document


@dataclass(frozen=True)
class GovernanceConfig:
    path: Path
    level: str
    selections: tuple
    plugins: tuple
    rule_params: Mapping


def load_governance_config(directory, level):
    if level not in {"project", "root"}:
        raise ValueError("governance configuration level must be project or root")
    path = Path(directory) / f"{level}_rules.jsonc"
    data = load_raw_config_document(path).data if path.exists() else {}
    unknown = set(data) - {"plugins", "rulesets", "rule_params"}
    if unknown:
        raise ValueError(f"{path}: unknown fields {sorted(unknown)}")
    selections = selection_refs(data.get("rulesets", [f"vibeflow.{level}.default"]))
    plugins, parameters = data.get("plugins", []), data.get("rule_params", {})
    if not isinstance(plugins, list) or not isinstance(parameters, Mapping):
        raise ValueError(f"{path}: plugins must be a list and rule_params must be an object")
    if any(not isinstance(key, str) or not isinstance(value, Mapping) for key, value in parameters.items()):
        raise ValueError(f"{path}: rule_params must map Rule IDs to parameter objects")
    return GovernanceConfig(path, level, selections, tuple(readonly(plugins)), readonly(parameters))


def governance_context(inventory, *, root=None, resources=()):
    workspace = inventory.workspace
    selected = root.path if root is not None else workspace.root
    facts = {"id": root.id if root is not None else str(workspace.root), "path": str(selected),
        "directories": inventory.directories["roots"][root.id] if root is not None else inventory.directories["project"],
        "resources": tuple(resources),
        "entries": inventory.entries["roots"][root.id] if root is not None else inventory.entries["project"]}
    level = "root" if root is not None else "project"
    if root is None:
        facts.update(roots=tuple({"id": item.id, "path": Path(relpath(item.path, workspace.root)).as_posix(),
                                 "absolute_path": str(item.path), "config_path": str(item.config_path),
                                 "target": item.project_target, "purpose": getattr(item, "purpose", ""),
                                 "directories": inventory.directories["roots"].get(item.id, ()),
                                 "workflows": tuple({"path": workflow.path.relative_to(item.path).as_posix(), "declaration": workflow.data}
                                      for workflow in inventory.for_root(item.id))} for item in workspace.roots),
                     inventory_complete=inventory.complete)
    else:
        facts["workflows"] = tuple({"path": item.path.relative_to(root.path).as_posix(), "declaration": item.data}
                                    for item in inventory.for_root(root.id))
    return RuleContext(facts={level: facts}, subject={"kind": level, "id": facts["id"]},
                       scope={"level": level, "id": facts["id"]}, target="project")


def execute_governance(config, context, *, catalogs, handlers):
    if context.scope.get("level") != config.level:
        raise ValueError("governance configuration and context levels differ")
    rules = {item.id: item for item in catalogs.rules}
    for identifier, parameters in config.rule_params.items():
        if identifier not in rules:
            raise ValueError(f"{config.path}: unknown Rule '{identifier}' in rule_params")
        rule = rules[identifier]
        rules[identifier] = replace(rule, params_defaults={**rule.params_defaults, **parameters})
    return tuple(replace(execute_rule_plan(compile_ruleset(reference, rules=rules, rulesets=catalogs.rulesets),
                                   context, handlers=handlers), scope=context.scope) for reference in config.selections)
