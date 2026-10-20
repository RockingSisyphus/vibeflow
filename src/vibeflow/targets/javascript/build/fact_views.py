"""JavaScript declaration/source adapters for prepared fact views."""
from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping
from vibeflow.core.descriptors.contributions import contribution_facts
from vibeflow.core.descriptors.source_bundle import source_resources, implementation_sources
from vibeflow.core.rules.models import plain
from vibeflow.targets.shared.facts import FactStore
from vibeflow.targets.javascript.build.graph_wire import graph_wire


def closure_import_policy(policy: Mapping[str, Any], catalogs: Any, sources: list[Mapping[str, Any]], *, project_root: Path, target: str) -> Mapping[str, Any]:
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
                         "completion":implementation.completion, "flowKind":getattr(descriptor,"flow_kind","")}
                if owner not in owners:
                    owners.append(owner)
            if kind == "node":
                node_base_libs[resource_id] = list(descriptor.base_libs)
            elif kind == "base_lib":
                base_dependencies[resource_id] = list(descriptor.dependencies)
    return {**policy, "owners": owners, "node_base_libs": node_base_libs, "base_lib_dependencies": base_dependencies}


def identity_facts(facts):
    """Finite graph inputs, retaining every observable field and opaque extra."""
    result = dict(facts)
    for name in ("catalogs","analysis_cache"):
        result.pop(name,None)
    for name in ("graph","global_graph","declaration_graph"):
        if result.get(name) is not None:
            result[name] = graph_wire(result[name],plain)
    if result.get("definition") is not None:
        value = result["definition"]
        result["definition"] = {**plain(replace(value,graph=replace(value.graph,nodesets={}))),
            "graph":graph_wire(value.graph,plain)}
    if "graphs" in result:
        result["graphs"] = tuple(identity_facts(value) for value in result["graphs"])
    if facts.get("catalogs") is not None:
        # Prepared contexts already contain the declaration snapshot. Retain
        # only additional/different service inputs rather than encoding it twice.
        catalog_facts = contribution_facts(facts["catalogs"])
        result["catalog_changes"] = {key:value for key,value in catalog_facts.items()
            if key not in result or result[key] != value}
    return result


class JavascriptFacts:
    def __init__(self,target):
        self.store = FactStore(target)

    def capture(self,facts,*,scope=None):
        prepared = identity_facts(facts)
        return self.store.capture(facts,key=self.store.additions_key(prepared),scope=scope)
