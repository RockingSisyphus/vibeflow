"""Business Node declarations discovered under project/root nodes/."""

def node(*, id: str, node_type: str, contract, flow_kind="process", source=None, **options):
    """Declare a class implementing run_pure; source enables delayed binding."""
    from vibeflow.targets.python.sdk.resources import _decorator
    options = {"id": id, "node_type": node_type, "contract": contract, "flow_kind": flow_kind,
               "display_name": id, "description": id, "version": "1.0.0", **options}
    return _decorator("node", options, source)
