"""Portable workflow references and node-owned launch declarations."""
from collections.abc import Mapping
from posixpath import normpath


def workflow_node_params(node, descriptor, subject):
    """Use the same declared scope and call override order as execution."""
    from vibeflow.core.config.scope import normalize_config_scope, scoped_node_params
    contract = getattr(descriptor, "contract", None)
    local = scoped_node_params(node.params, normalize_config_scope(subject.global_config),
        declared_keys=set(getattr(contract, "params_schema", {})))
    return {**getattr(contract, "params_defaults", {}), **local, **subject.overrides.get(node.id, {})}


def workflow_reference(value, *, root=""):
    if not isinstance(value, Mapping) or set(value) - {"root", "path", "entry"}:
        raise ValueError("workflow must contain root, path and optional entry")
    path = value.get("path")
    if not isinstance(path, str) or not path.strip() or path.startswith(("/", "\\")):
        raise ValueError("workflow.path must be relative to its root")
    path = normpath(path.replace("\\", "/"))
    if path == ".." or path.startswith("../") or ":" in path:
        raise ValueError("workflow.path must stay within its root")
    result = {"root": value.get("root") or root, "path": path}
    if not isinstance(result["root"], str):
        raise ValueError("workflow.root must be a root id")
    if "entry" in value and value["entry"] is not None:
        if not isinstance(value["entry"], str) or not value["entry"].strip():
            raise ValueError("workflow.entry must name an entry")
        result["entry"] = value["entry"]
    return result


def launch_configuration(value):
    if not isinstance(value, Mapping) or set(value) - {"command", "cwd", "env"}:
        raise ValueError("launch must contain command and optional cwd/env")
    command = value.get("command")
    if not isinstance(command, (list, tuple)) or not command or any(not isinstance(v, str) for v in command) or not command[0]:
        raise ValueError("launch.command must be a non-empty argument array")
    cwd, env = value.get("cwd", "."), value.get("env", {})
    if not isinstance(cwd, str) or not isinstance(env, Mapping) or any(
            not isinstance(k, str) or not k or not isinstance(v, str) for k, v in env.items()):
        raise ValueError("launch.cwd must be a string and launch.env must map strings")
    return {"command": list(command), "cwd": cwd, "env": dict(env)}


def node_workflow_actions(actions, params, *, root=""):
    """Join evaluated operations with the effective call configuration once."""
    result = []
    for original in actions:
        action = dict(original)
        if action.get("capability") == "vibeflow.workflow":
            if set(action) & {"target", "entry", "workflow", "launch", "expected_workflows"}:
                raise ValueError("workflow action target aliases are removed; configure node.workflow")
            operation = action.get("operation")
            if operation in {"call", "kill"}:
                action["workflow"] = workflow_reference(params.get("workflow"), root=root)
                if operation == "call":
                    launch_configuration(params.get("launch"))
            if operation in {"send", "receive"}:
                expected = params.get("expected_workflows", ())
                if not isinstance(expected, (list, tuple)):
                    raise ValueError("expected_workflows must be a list")
                action["expected_workflows"] = [workflow_reference(item, root=root) for item in expected]
        result.append(action)
    return result


def action_references(action):
    if action.get("capability") != "vibeflow.workflow":
        return ()
    if action.get("operation") in {"call", "kill"}:
        return (action["workflow"],)
    return tuple(action.get("expected_workflows", ()))


def launch_document(launches, *, base=".", workflow=None):
    return {"format":"vibeflow.workflow-launches.v1",
            "workflow":workflow,
            "launches":[{**item, "base":base} for item in launches]}
