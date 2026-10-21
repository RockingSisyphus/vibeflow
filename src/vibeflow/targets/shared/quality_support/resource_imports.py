"""Judge declared source relationships using Target-supplied ownership facts."""

from collections.abc import Mapping, Sequence


def implementation_import_scopes(scopes, implementations):
    """Keep entry references separate from a declaration module's initialization."""
    projections = {(item["kind"], item["id"], item["path"], item.get("export", "")): item
                   for item in implementations}
    result = []
    for scope in scopes:
        declarations = {owner["path"] for owner in scope["owners"]
                        if owner["kind"] == "plugin_declaration"}
        owners = []
        for owner in scope["owners"]:
            if owner["role"] != "entry":
                owners.append(owner)
                continue
            facts = projections.get((owner["kind"], owner["id"], owner["path"], owner["symbol"]), {})
            lines = facts.get("import_lines")
            if owner["kind"] != "plugin_declaration" and owner["path"] in declarations:
                lines = facts.get("entry_import_lines", lines)
            owners.append({**owner, "import_lines": lines})
        result.append({**scope, "owners": owners})
    return tuple(result)


def resource_import_violations(source_path, target_path, sites, scopes):
    """Return denying declarations; unowned source has no resource identity."""
    violations = []
    for scope in scopes:
        owners = scope.get("owners", ())
        sources = [item for item in owners if item["path"] == source_path and item.get("selected",True)]
        targets = [item for item in owners if item["path"] == target_path]
        if not sources:
            continue
        for owner in sources:
            selected = _selected_sites(owner, sites)
            if not selected or _allows(owner, targets):
                continue
            code = _code(owner["kind"])
            if code:
                violations.append((code, owner, selected, scope.get("id", "")))
    return violations


def _selected_sites(owner: Mapping, sites: Sequence):
    lines = owner.get("import_lines")
    if owner.get("role") != "entry" or lines is None:
        return sites
    return tuple(site for site in sites if site.get("line") in lines)


def _allows(source, targets):
    for target in targets:
        if source.get("plugin_id") and source["plugin_id"] == target.get("plugin_id"):
            return True
        if (source["kind"], source["id"]) == (target["kind"], target["id"]):
            return True
        if target["kind"] == "base_lib":
            libraries = (*source.get("base_libs", ()),
                *(source.get("dependencies", ()) if source["kind"] == "base_lib" else ()))
            if target["id"] in libraries:
                return True
        if source["kind"] == "plugin_declaration" and target.get("plugin_id") == source["id"]:
            return True
    return False


def _code(kind):
    return {
        "node": "QUALITY.STRUCTURE.NODE_UNDECLARED_PROJECT_IMPORT",
        "base_lib": "QUALITY.STRUCTURE.BASE_LIB_UPWARD_IMPORT",
        "plugin": "QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT",
        "plugin_declaration": "QUALITY.STRUCTURE.PLUGIN_NODE_IMPORT",

    }.get(kind)
