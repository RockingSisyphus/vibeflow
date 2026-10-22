"""Fold explicit policy Records at full call identities; no source inference."""
POLICY_TYPE = "vibeflow.capability_policy.v1"


def fold_policies(records, call_paths):
    restrictions, grants, actions = {}, {}, {}
    for record in records:
        if record.get("mode") == "restrict":
            for path in record["graph_paths"]:
                restrictions.setdefault(tuple(path), set()).update(record["capabilities"])
        elif record.get("mode") == "allow":
            path = tuple(record["call_path"])
            grants.setdefault(path, {}).setdefault(record["capability"], set()).update(record["operations"])
            declared = actions.setdefault(path, [])
            for action in record.get("actions", ()):
                intent = {**action, "capability": record["capability"]}
                if intent not in declared:
                    declared.append(intent)
    return {tuple(path): {"capabilities": {capability: sorted(grants.get(tuple(path), {}).get(capability, ()))
        for capability in sorted(restrictions.get(tuple(path[:-1]), ()))},
        "actions": actions.get(tuple(path), [])} for path in call_paths}
