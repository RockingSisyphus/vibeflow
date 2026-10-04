"""Migrate historical implicit helper fixtures to explicit source membership.

Only test-data conversion uses this discovery. Production resources always
list exact files through the SDK. Existing health decisions remain selected.
"""
from copy import deepcopy
from pathlib import Path


def explicit_python_files(project, values):
    from vibeflow.targets.python.project.source_closure import collect_python_source_facts, resolve_local_module_path
    converted = [(location,deepcopy(data)) if isinstance(item,tuple) else (None,deepcopy(item))
                 for item in values for location,data in (item if isinstance(item,tuple) else (None,item),)]
    registered = {}
    for _,data in converted:
        if data.get("kind") not in {"node","base_lib","plugin"}:
            continue
        for implementation in data.get("implementations", ()):
            locator = implementation["source"]
            path = (project / locator["ref"]).resolve() if locator["kind"] == "file" else resolve_local_module_path(locator["ref"],project_root=project)
            if path:
                registered.setdefault(str(path),[]).append((data["kind"],data.get("id",data.get("type_key"))))
    for _,data in converted:
        kind = data.get("kind")
        if kind not in {"node","base_lib","plugin"}:
            continue
        resource_id = data.get("id",data.get("type_key"))
        for implementation in data.get("implementations", ()):
            locator = implementation["source"]
            path = (project / locator["ref"]).resolve() if locator["kind"] == "file" else resolve_local_module_path(locator["ref"],project_root=project)
            if path is None or not path.is_file():
                continue
            support = list(implementation.get("implementation_files", ()))
            for fact in collect_python_source_facts(path,project_root=project):
                claims = registered.get(fact.path, ())
                for other_kind,key in claims:
                    if other_kind == "base_lib" and key != resource_id:
                        field = "dependencies" if kind == "base_lib" else "base_libs"
                        data.setdefault(field,[])
                        if key not in data[field]:data[field].append(key)
                if not claims and Path(fact.path) != path:
                    source = {"kind":"file","ref":str(Path(fact.path).relative_to(project)) if Path(fact.path).is_relative_to(project) else fact.path}
                    if source not in support:support.append(source)
            if support:implementation["implementation_files"] = support
    return converted
