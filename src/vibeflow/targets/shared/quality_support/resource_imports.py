"""Project Target import measurements onto declared implementation symbols."""


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
