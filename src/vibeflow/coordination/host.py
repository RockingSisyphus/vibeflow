"""Report a host's actual completion without owning children or host lifetime."""
from .client import WorkflowClient


def run_host(run, *, workflow=None, stop=None, url=None, identifier=None):
    """``run(client)`` returns public JSON outputs after its own cleanup."""
    client = (WorkflowClient(url, identifier=identifier, workflow=workflow, stop=stop)
              if url is not None else WorkflowClient.from_environment(workflow=workflow, stop=stop))
    try:
        outputs = run(client)
    except BaseException as error:
        state = "cancelled" if getattr(error, "code", "") == "VF_ABORTED" or isinstance(error, KeyboardInterrupt) else "failed"
        try:
            client.finish(state=state, error={"code": getattr(error, "code", type(error).__name__), "message": str(error)})
        except Exception as delivery:
            error.add_note(f"coordination completion could not be delivered: {delivery}")
        raise
    client.finish(outputs=outputs)
    return outputs
