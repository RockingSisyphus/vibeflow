"""Report actual invocation completion; hosts retain their own lifetime."""
import asyncio
import inspect
from .client import WorkflowClient
from .protocol import error_record


async def run_host(run, *, workflow=None, stop=None, url=None, identifier=None):
    client = (await WorkflowClient.open(url,identifier=identifier,workflow=workflow,stop=stop)
              if url is not None else await WorkflowClient.from_environment(workflow=workflow,stop=stop))
    try:
        outputs=run(client)
        if inspect.isawaitable(outputs):outputs=await outputs
    except BaseException as error:
        state='cancelled' if isinstance(error,asyncio.CancelledError) or getattr(error,'code','')=='VF_ABORTED' else 'failed'
        try:await client.finish(state=state,error=error_record(error))
        except BaseException as delivery:error.add_note(f'coordination completion could not be delivered: {delivery}')
        raise
    await client.finish(outputs=outputs)
    return outputs
