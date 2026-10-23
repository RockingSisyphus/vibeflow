"""Native asynchronous HTTP client. Blocking HTTP is confined to the transport."""
import asyncio
import inspect
import json
import os
from .async_support import finish_cleanup
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from vibeflow.core.workflows.references import workflow_reference, launch_configuration
from .operations import Operation, immediate_dispatch
from .protocol import CoordinationError, json_value, error_record, merge_cleanup_error


class WorkflowClient:
    def __init__(self, url):
        self.url = url.rstrip('/')
        self.closed = False
        self._pending, self._errors = [], []
        self._watcher = None
        self._finishing = None

    @classmethod
    async def open(cls, url, *, identifier=None, workflow=None, stop=None):
        client = cls(url)
        registered = await client.request('register',{'id':identifier,'workflow':workflow,'pid':os.getpid(),'stop_supported':stop is not None})
        client.id, client.inputs, client.entry, client.workflow = (registered[k] for k in ('id','inputs','entry','workflow'))
        if stop is not None:client._watcher=asyncio.create_task(client._watch_stop(stop))
        return client

    @classmethod
    async def from_environment(cls, **options):
        return await cls.open(os.environ['VIBEFLOW_COORDINATION_URL'],identifier=os.environ.get('VIBEFLOW_INSTANCE_ID'),**options)

    async def request(self, operation, value):
        body=json.dumps(json_value(value),ensure_ascii=False,allow_nan=False).encode()
        def transfer():
            request=Request(self.url+'/'+operation,data=body,headers={'Content-Type':'application/json'})
            try:response=urlopen(request,timeout=5)
            except HTTPError as error:response=error
            with response:return json.load(response)
        # The thread belongs to this request and is joined before cancellation exits.
        task=asyncio.create_task(asyncio.to_thread(transfer))
        try:result=await asyncio.shield(task)
        except asyncio.CancelledError:
            while not task.done():
                try:await asyncio.shield(task)
                except asyncio.CancelledError:continue
            task.exception()
            raise
        if 'error' in result:raise CoordinationError(result['error']['code'],result['error']['message'])
        return result['value']

    async def _watch_stop(self, stop):
        try:
            while not self.closed:
                result=await self.request('control',{'id':self.id})
                if result.get('stop'):
                    value=stop()
                    if inspect.isawaitable(value):await value
                    return
                if result.get('ended'):return
        except Exception as error:
            if not self.closed:self._errors.append(error)

    def send(self, identifier, port, payload):
        if self.closed or self._finishing is not None:raise CoordinationError('VF_INSTANCE_ENDED',self.id)
        value=json_value({'id':identifier,'sender':self.id,'port':port,'payload':payload})
        previous = self._pending[-1] if self._pending else None
        async def deliver():
            if previous is not None:
                try:await previous
                except Exception:pass  # Flush reports every earlier delivery failure.
            return await self.request('send',value)
        self._pending.append(asyncio.create_task(deliver()))

    async def flush(self):
        pending,self._pending=self._pending,[]
        outcomes=await asyncio.gather(*pending,return_exceptions=True)
        self._errors.extend(item for item in outcomes if isinstance(item,BaseException))
        if self._errors:raise self._errors[0]

    async def _wait(self, operation, identifier, *, port=None, timeout=None, signal=None):
        loop=asyncio.get_running_loop()
        deadline=None if timeout is None else loop.time()+timeout
        while True:
            if signal:signal.throw_if_aborted()
            if self.closed:raise CoordinationError('VF_INSTANCE_ENDED',self.id)
            if deadline is not None and loop.time()>=deadline:raise CoordinationError('VF_WAIT_TIMEOUT',identifier)
            request={'id':identifier}
            if port is not None:request['port']=port
            result=await self.request(operation,request)
            if not result.get('pending'):return result

    async def call(self, workflow, *, launch, inputs=None, timeout=None, signal=None):
        reference=workflow_reference(workflow,root=self.workflow.get('root','') if isinstance(self.workflow,dict) else '')
        value=await self.request('call',{'sender':self.id,'workflow':reference,'launch':launch_configuration(launch),'inputs':inputs or {}})
        return await self._wait('ready',value['id'],timeout=timeout,signal=signal)

    async def wait(self, identifier, *, timeout=None, signal=None):
        return await self._wait('wait',identifier,timeout=timeout,signal=signal)

    async def receive(self, port='default', *, timeout=None, signal=None):
        return await self._wait('receive',self.id,port=port,timeout=timeout,signal=signal)

    async def kill(self, identifier, *, workflow=None, timeout=None, signal=None):
        value={'id':identifier}
        if workflow is not None:value['workflow']=workflow_reference(workflow,root=self.workflow.get('root','') if isinstance(self.workflow,dict) else '')
        await self.request('kill',value)
        return await self.wait(identifier,timeout=timeout,signal=signal)

    def operations(self):
        immediate = immediate_dispatch()
        return {'call':Operation(lambda r,s:self.call(r['workflow'],launch=r['launch'],inputs=r.get('inputs'),timeout=r.get('timeout'),signal=s)),
                'wait':Operation(lambda r,s:self.wait(r['id'],timeout=r.get('timeout'),signal=s)),
                'receive':Operation(lambda r,s:self.receive(r.get('port','default'),timeout=r.get('timeout'),signal=s)),
                'send':Operation(lambda r,s:immediate(lambda:self.send(r['id'],r.get('port','default'),r.get('payload')))),
                'kill':Operation(lambda r,s:self.kill(r['id'],workflow=r['workflow'],timeout=r.get('timeout'),signal=s))}

    async def finish(self, *, state='succeeded', outputs=None, error=None):
        if self._finishing is None:self._finishing=asyncio.create_task(self._finish(state,outputs,error))
        primary = None
        try:
            await finish_cleanup(self._finishing)
        except BaseException as failure:
            primary = failure
            raise
        finally:
            try:
                if self._watcher is not None and self._watcher is not asyncio.current_task():
                    await finish_cleanup(self._watcher)
            except BaseException as cleanup:
                if primary is None:
                    raise
                primary.cleanup_errors = [*getattr(primary, 'cleanup_errors', ()), cleanup]

    async def _finish(self,state,outputs,error):
        if self.closed:return
        failure=None
        try:
            try:await self.flush()
            except BaseException as cause:
                failure=cause
                detail = {**error_record(cause),'code':getattr(cause,'code','VF_DELIVERY_FAILED')}
                state,error='failed',merge_cleanup_error(error,detail)
            try:payload=json_value({'id':self.id,'state':state,'outputs':outputs,'error':error})
            except BaseException as cause:
                failure=failure or cause
                payload={'id':self.id,'state':'failed','outputs':None,
                         'error':merge_cleanup_error(error,{'code':'VF_RESULT_NOT_JSON','message':str(cause)})}
            await self.request('complete',payload)
            if failure:raise failure
        finally:self.closed=True
