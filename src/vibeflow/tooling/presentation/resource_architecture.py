"""Selected project resource and source facts for Architecture JSONC."""
from pathlib import Path
import hashlib

from vibeflow.core.descriptors.source_bundle import source_resources, implementation_sources
from vibeflow.core.rules import compile_ruleset
from vibeflow.tooling.presentation.node_presentation import resolve_presentation


def _selected_resources(selections, catalogs):
    selected = {}
    for kind, values in (
                         [("base_lib", selections.get("base_lib", {}).get("modules", ()))]):
        for value in values:
            item = {"id":value} if isinstance(value,str) else value
            if item.get("id"):
                selected[(kind,item["id"])] = item
    for record in catalogs.plugin_records:
        if record.get("id"):
            selected[("plugin_declaration",record["id"])] = record
    for record in catalogs.lifecycle_selections:
        if record.get("id"):
            selected[("plugin",record["id"])] = record
    return selected


def _rule_plans(descriptor, catalogs):
    return {phase:[compile_ruleset(rule_id,rules=catalogs.rules,rulesets=catalogs.rulesets,
                                  entrypoint=phase).to_dict() for rule_id in descriptor.rulesets]
            for phase in ("import","static","run")}


def resource_architecture(catalogs, *, project_root, source_facts=(), selections=None,
                          selected_nodes=None, findings=(), roots=None):
    root = Path(project_root).resolve()
    selections = selections or {}
    snapshots = {str(Path(item["path"]).resolve()):item for item in source_facts}
    resources, files, edges = {}, {}, []
    selected = None if selected_nodes is None else set(selected_nodes)
    uses = _selected_resources(selections,catalogs)
    known_roots = {key:Path(value).resolve() for key,value in (roots or {}).items()}

    def source_id(path):
        file = Path(path)
        if file.is_relative_to(root):identity=file.relative_to(root).as_posix()
        else:
            identity=next(((key if key.startswith("@") else "@"+key)+"/"+file.relative_to(value).as_posix() for key,value in known_roots.items()
                           if file.is_relative_to(value)),str(file))
        return "file:" + hashlib.sha256(identity.encode()).hexdigest()[:16]

    def include_file(path, owner=None):
        key=source_id(path)
        file=files.setdefault(key,{"id":key,"path":path,"owners":[],
                                  "load_state":snapshots.get(path,{}).get("load_state",catalogs.source_load_states.get(path,"unknown"))})
        if owner and owner not in file["owners"]:file["owners"].append(owner)
        return key

    diagnostics = [item.to_dict() if hasattr(item,"to_dict") else item for item in findings]
    for kind, descriptor in source_resources(catalogs):
        if kind == "node" and selected is not None and descriptor.id not in selected:continue
        use=uses.get((kind,descriptor.id),{})
        source_rows = []
        for implementation in descriptor.implementations:
            for role, locator in implementation_sources(implementation):
                if locator.kind != "file":continue
                path=str((root / locator.ref).resolve())
                if snapshots and path not in snapshots and kind != "plugin_declaration" and not use:continue
                owner={"kind":kind,"id":descriptor.id,"role":role,"symbol":locator.export or ""}
                key=include_file(path,owner)
                source_rows.append({"id":key,"path":path,"role":role,"symbol":owner["symbol"],
                    "language":implementation.language,"load_state":files[key]["load_state"]})
        if not source_rows and kind != "plugin_declaration" and not use and not (kind == "node" and selected is not None):continue
        group={"node":"nodes","base_lib":"base_libs","plugin":"plugins"}.get(kind)
        origin=catalogs.origins.get((group,descriptor.id))
        plugin_id=origin.owner.plugin_id if origin else descriptor.id if kind == "plugin_declaration" else ""
        package=uses.get(("plugin_declaration",plugin_id),{})
        style=use.get("style", package.get("style",{}) if kind == "plugin" else {})
        status=use.get("status","implemented")
        related=[item for item in diagnostics if item.get("object_id",item.get("subject_id"))==descriptor.id
                 and item.get("object_type",kind) in {kind}
                 or not item.get("object_id",item.get("subject_id"))
                 and item.get("source_location",{}).get("path") in {row["path"] for row in source_rows}]
        markers=(["planned"] if status=="planned" else [])+(["external"] if getattr(descriptor,"external",False) else [])
        severity={item.get("severity") for item in related}
        markers += [value for value in ("error","warning") if value in severity]
        native={"base_lib":"baseLibResource","plugin":"pluginResource","plugin_declaration":"pluginResource"}.get(kind,"")
        status_class="plannedResource" if status=="planned" else "healthError" if "error" in severity else "healthWarning" if "warning" in severity else "externalDependency" if "external" in markers else ""
        presentation=resolve_presentation(descriptor,native_class=native,status_class=status_class,
                                          call_style=style,resource_kind=kind)
        key=kind+":"+descriptor.id
        ownership = origin.owner.to_dict() if origin else {"kind":"plugin", "id":plugin_id,
            "root_id":package.get("root", ""), "path":package.get("package_path", "")}
        resources[key]={**descriptor.to_dict(),"id":descriptor.id,"kind":kind,"plugin_id":plugin_id,"owner":ownership,
            "origin":origin.to_dict() if origin else {"owner":ownership,"path":source_rows[0]["path"] if source_rows else ""},
            "status":status,"markers":markers,"diagnostics":related,"effective_rules":_rule_plans(descriptor,catalogs),
            "effective_presentation":presentation.to_dict(),"sources":source_rows}
        for row in source_rows:edges.append({"from":key,"to":row["id"],"relation":row["role"]})
    # Planned selections need no implementation descriptor, but remain real
    # declarations with their own presentation and review metadata.
    for (kind, identity), record in uses.items():
        key = kind + ":" + identity
        if kind == "plugin_declaration" or key in resources or record.get("status") != "planned":
            continue
        native = {"base_lib":"baseLibResource", "plugin":"pluginResource"}[kind]
        presentation = resolve_presentation(record, native_class=native, status_class="plannedResource",
            call_style=record.get("style", {}), resource_kind=kind)
        resources[key] = {**record, "kind":kind, "id":identity, "plugin_id":"", "status":"planned",
            "markers":["planned"], "effective_rules":{}, "sources":[],
            "effective_presentation":presentation.to_dict()}
    for record in catalogs.plugin_records:
        if record.get("loaded") or not record.get("id"):continue
        key="plugin_declaration:"+record["id"]
        presentation=resolve_presentation(record,native_class="pluginResource",status_class="plannedResource",
                                          call_style=record.get("style",{}),resource_kind="plugin_declaration")
        resources[key]={**record,"kind":"plugin_declaration","id":record["id"],"plugin_id":record["id"],"owner":{"kind":"plugin","id":record["id"]},
            "status":"planned","markers":["planned"],"rulesets":[],"effective_rules":{},"sources":[],
            "origin":{"owner":{"kind":"plugin","id":record["id"]},"path":str(known_roots.get(record.get("root"),root)/record.get("source",{}).get("ref",""))},
            "effective_presentation":presentation.to_dict()}
    for descriptor in catalogs.rules:
        origin=catalogs.origins.get(("rules",descriptor.id))
        package="plugin_declaration:"+origin.owner.plugin_id if origin else ""
        if package not in resources:continue
        for implementation in descriptor.implementations:
            locator=implementation.source
            if locator.kind != "file":continue
            path=str((root/locator.ref).resolve())
            if path not in snapshots:continue
            key=include_file(path,{"kind":"rule","id":descriptor.id,"role":"entry","symbol":locator.export or ""})
            edges.append({"from":package,"to":key,"relation":"rule_implementation","rule_id":descriptor.id})
    # Unconstrained resources still expose reached local code as unknown ownership.
    for path in snapshots:
        if Path(path).is_relative_to(root) or any(Path(path).is_relative_to(value) for value in known_roots.values()):
            include_file(path)
    by_path={item["path"]:key for key,item in files.items()}
    for path,snapshot in snapshots.items():
        for imported in snapshot.get("imports",()):
            target=imported.get("path",imported.get("resolved_path",""))
            if path in by_path and target in by_path:
                edges.append({"from":by_path[path],"to":by_path[target],"relation":"import",
                    "specifier":imported.get("specifier",""),"line":imported.get("line"),"type_only":imported.get("type_only",False)})
    for key,resource in resources.items():
        for target in resource.get("base_libs",()):
            if "base_lib:"+target in resources:edges.append({"from":key,"to":"base_lib:"+target,"relation":"base_lib"})
        for target in resource.get("dependencies",()):
            dependency=resource["kind"]+":"+target
            if dependency in resources:edges.append({"from":key,"to":dependency,"relation":"dependency"})
        package="plugin_declaration:"+resource["plugin_id"]
        if package in resources and key != package:edges.append({"from":package,"to":key,"relation":"contributes"})
    return {"resources":resources,"files":files,"relations":edges}
