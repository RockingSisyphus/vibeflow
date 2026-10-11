"""Python Node declarations, contributed through Plugin.resources."""

def node(*, type_key: str, contract, flow_kind="process", source=None, **options):
    """Declare a class implementing run_pure; source enables delayed binding."""
    from vibeflow.targets.python.sdk.resources import _decorator
    options = {"type_key": type_key, "contract": contract, "flow_kind": flow_kind,
               "display_name": type_key, "description": type_key, "version": "1.0.0", **options}
    return _decorator("node", options, source)
