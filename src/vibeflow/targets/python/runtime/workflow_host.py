"""Connect one native Runtime to the local protocol; hosts own their environment."""
from vibeflow.coordination.host import run_host
from .lifecycle import CancellationSignal
from .values import _public_result_value


def run_connected(runtime_factory, *, workflow=None, initial=None, entry=None, url=None, identifier=None):
    """Factory receives ``entry`` and the workflow Capability, and returns a fresh Runtime."""
    signal = CancellationSignal()

    def execute(client):
        runtime = runtime_factory(entry=client.entry if client.entry is not None else entry,
            capabilities={"vibeflow.workflow": client.operations()})
        from vibeflow.core.workflows.identity import WorkflowIdentity
        runtime.workflow = WorkflowIdentity(client.id)
        unsubscribe = signal.subscribe(runtime.request_stop)
        try:
            result = runtime.run({**(initial or {}), **client.inputs})
            return {spec.public_name: _public_result_value(result.get(spec.public_name))
                    for spec in runtime.graph.outputs if result.exists(spec.public_name)}
        finally:
            unsubscribe()

    return run_host(execute, workflow=workflow, stop=signal.request_stop, url=url, identifier=identifier)
