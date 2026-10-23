"""Target-owned Runtime adapters for HTTP and in-process coordination."""
from vibeflow.coordination.host import run_host
from .lifecycle import CancellationSignal
from .values import _public_result_value


def bind_workflow(coordinator, descriptor, runtime_factory):
    def execute(inputs, options):
        runtime=runtime_factory(entry=options.get('entry'),
            capabilities=options.get('capabilities',{}),workflow_instance_id=options['workflow_instance_id'])
        def outputs(result):
            return {spec.public_name:_public_result_value(result.get(spec.public_name))
                    for spec in runtime.graph.outputs if result.exists(spec.public_name)}
        if descriptor['entry_mode']=='sync':
            from .observation import independent_observation
            with independent_observation():
                return outputs(runtime.run(inputs))
        async def run():return outputs(await runtime.run_async(inputs))
        return run()
    return coordinator.bind(descriptor,execute)


async def run_connected(runtime_factory, *, workflow=None, initial=None, entry=None, url=None, identifier=None):
    signal=CancellationSignal()
    async def execute(client):
        runtime=runtime_factory(entry=client.entry if client.entry is not None else entry,
            capabilities={'vibeflow.workflow':client.operations()},workflow_instance_id=client.id)
        unsubscribe=signal.subscribe(runtime.request_stop)
        try:
            inputs={**(initial or {}),**client.inputs}
            result=await runtime.run_async(inputs) if runtime.graph.entry_mode=='async' else runtime.run(inputs)
            return {spec.public_name:_public_result_value(result.get(spec.public_name))
                    for spec in runtime.graph.outputs if result.exists(spec.public_name)}
        finally:unsubscribe()
    return await run_host(execute,workflow=workflow,stop=signal.request_stop,url=url,identifier=identifier)
