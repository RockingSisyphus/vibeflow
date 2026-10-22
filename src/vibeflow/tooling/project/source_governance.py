"""Resource ownership supplied to root source Rules, using prepared declarations."""



def private_root_imports(workspace, root, imports):
    """Attribute Target-resolved import edges; policy stays in the root Rule."""
    result = {}
    for source, target, line in imports:
        owner = workspace.root_for_path(target)
        shared = workspace.root_for_path(source) is None
        if owner is not None and (owner.id != root.id or shared):
            key = (str(source), str(target), line)
            result[key] = {"path":str(source), "imported_path":str(target), "root":owner.id, "line":line, "shared":shared}
    return tuple(result[key] for key in sorted(result))
