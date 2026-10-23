"""Native asyncio instance/mailbox owner; execution is supplied by host bindings."""
import asyncio
import inspect
from concurrent.futures import Future
from collections import deque

from vibeflow.core.workflows.coordination import TERMINAL, validate_descriptor
from vibeflow.core.workflows.entries import choose_entry
from vibeflow.core.workflows.references import launch_configuration, workflow_reference
from .protocol import CoordinationError, instance_id, json_value, error_record


def _key(reference):
    return reference['root'], reference['path']


class Coordinator:
    def __init__(self, *, launches=(), launcher=None):
        self.instances, self.bindings = {}, {}
        self.launches = [dict(item, workflow=workflow_reference(item['workflow']),
                              launch=launch_configuration(item['launch'])) for item in launches]
        self.launcher = launcher
        self.closed = False

    def bind(self, descriptor, runner):
        descriptor = validate_descriptor(json_value(descriptor))
        key = _key(descriptor['workflow'])
        if key in self.bindings:
            raise CoordinationError('VF_WORKFLOW_BOUND', str(key))
        self.bindings[key] = (descriptor, runner)
        for action in descriptor.get('calls', ()):
            if action['operation'] == 'call':
                self.launches.append({**action, 'caller':descriptor['workflow']})
        return self

    def _instance(self, identifier):
        try:
            return self.instances[identifier]
        except KeyError as cause:
            raise CoordinationError('VF_INSTANCE_UNKNOWN', str(identifier)) from cause

    def _notify(self, item):
        event = item['changed']
        item['changed'] = asyncio.Event()
        event.set()

    def reserve(self, *, identifier=None, workflow=None, inputs=None):
        if self.closed:
            raise CoordinationError('VF_SCOPE_CLOSED', 'coordinator is closed')
        identifier = identifier or instance_id()
        if identifier in self.instances:
            raise CoordinationError('VF_INSTANCE_EXISTS', identifier)
        item = dict(id=identifier, workflow=workflow, entry=workflow.get('entry') if isinstance(workflow,dict) else None,
                    inputs=json_value(inputs or {}), state='starting', registered=False, stop_requested=False,
                    stop_supported=False, outputs=None, error=None, pid=None, mailboxes={}, changed=asyncio.Event(), task=None)
        self.instances[identifier] = item
        return item

    def register(self, request):
        identifier = request.get('id')
        item = self._instance(identifier) if identifier in self.instances else self.reserve(identifier=identifier)
        if item['registered'] or item['state'] in TERMINAL:
            raise CoordinationError('VF_INSTANCE_EXISTS', item['id'])
        expected, actual = item['workflow'], request.get('workflow')
        if isinstance(actual, dict):
            actual = workflow_reference(actual, root=expected['root'] if isinstance(expected,dict) else '')
        if isinstance(expected,dict) and actual is not None and (not isinstance(actual,dict) or _key(expected) != _key(actual)):
            self.complete(item, 'failed', error={'code':'VF_WORKFLOW_MISMATCH',
                'message':f'registered workflow {actual!r} differs from declared target {expected!r}'})
            raise CoordinationError('VF_WORKFLOW_MISMATCH', item['id'])
        item.update(registered=True, state='running', workflow=expected or actual,
                    stop_supported=bool(request.get('stop_supported')), pid=request.get('pid'))
        self._notify(item)
        return {k:item[k] for k in ('id','inputs','entry','workflow')}

    def status(self, item):
        return json_value({k:item[k] for k in ('id','state','outputs','error','pid','workflow','entry')})

    def complete(self, item, state, outputs=None, error=None):
        if state not in TERMINAL:
            raise ValueError('completion state must be terminal')
        if item['state'] in TERMINAL:
            raise CoordinationError('VF_INSTANCE_ENDED', item['id'])
        item.update(state=state, outputs=json_value(outputs), error=json_value(error))
        self._notify(item)
        return self.status(item)

    def send(self, sender, identifier, payload, port='default'):
        self._instance(sender)
        item = self._instance(identifier)
        if item['state'] in TERMINAL:
            raise CoordinationError('VF_INSTANCE_ENDED', identifier)
        item['mailboxes'].setdefault(port,deque()).append(json_value({'sender':sender,'port':port,'payload':payload}))
        self._notify(item)

    async def wait_for(self, operation, identifier, *, port='default', timeout=None, signal=None):
        item = self._instance(identifier)
        loop = asyncio.get_running_loop()
        deadline = None if timeout is None else loop.time()+timeout
        while True:
            if self.closed:
                raise CoordinationError('VF_SCOPE_CLOSED', 'coordinator is closed')
            if signal is not None:
                signal.throw_if_aborted()
            event = item['changed']
            if operation == 'ready':
                if item['registered']:return {'id':identifier}
                if item['state'] in TERMINAL:raise CoordinationError('VF_LAUNCH_FAILED', str(item['error']))
            if operation == 'wait' and item['state'] in TERMINAL:return self.status(item)
            if operation == 'control' and (item['stop_requested'] or item['state'] in TERMINAL):
                return {'stop':item['stop_requested'],'ended':item['state'] in TERMINAL}
            if operation == 'receive':
                mailbox = item['mailboxes'].setdefault(port,deque())
                if mailbox:return mailbox.popleft()
                if item['state'] in TERMINAL:raise CoordinationError('VF_INSTANCE_ENDED', identifier)
            remaining = None if deadline is None else deadline-loop.time()
            if remaining is not None and remaining <= 0:raise CoordinationError('VF_WAIT_TIMEOUT', identifier)
            task = asyncio.current_task()
            unsubscribe = signal.subscribe(lambda reason:loop.call_soon_threadsafe(task.cancel)) if signal else lambda:None
            try:
                await asyncio.wait_for(event.wait(), remaining)
            except TimeoutError as cause:
                raise CoordinationError('VF_WAIT_TIMEOUT', identifier) from cause
            finally:
                unsubscribe()

    def _target(self, reference):
        reference = workflow_reference(reference)
        try:descriptor, runner = self.bindings[_key(reference)]
        except KeyError as cause:raise CoordinationError('VF_WORKFLOW_UNBOUND', str(reference)) from cause
        entry = choose_entry(descriptor.get('entries',{}),descriptor.get('default_entry',''),reference.get('entry'))
        return reference, descriptor, runner, entry

    def invoke_sync(self, request, *, sender=None, _dispatch=lambda callback:callback()):
        def prepare():
            if self.closed:raise CoordinationError('VF_SCOPE_CLOSED','coordinator is closed')
            reference = self._reference(request['workflow'], sender)
            self._declared(sender, reference, 'invoke_sync')
            reference, descriptor, runner, entry = self._target(reference)
            if descriptor['entry_mode'] != 'sync':raise CoordinationError('VF_WORKFLOW_SYNC_UNSUPPORTED',str(reference))
            inputs = json_value(request.get('inputs',{}))
            item=self.reserve(workflow=reference)
            self.register({'id':item['id'],'workflow':reference})
            options = {'entry':entry,'workflow_instance_id':item['id'],
                       'capabilities':{'vibeflow.workflow':self.operations(item['id'])}}
            return reference, runner, entry, item, inputs, options
        reference, runner, entry, item, inputs, options = _dispatch(prepare)
        try:
            # Keep computation in the current call/thread. Only coordination
            # state crosses to the owner's event loop when the caller is a worker.
            result = runner(inputs, options)
            if inspect.isawaitable(result) or isinstance(result, Future):
                if inspect.iscoroutine(result):result.close()
                raise CoordinationError('VF_COMPLETION_MISMATCH','synchronous target returned pending work')
            return json_value(result)
        except BaseException as error:
            invocation = {'id':item['id'], 'workflow':reference, 'entry':entry}
            error.workflow_calls = [*getattr(error, 'workflow_calls', ()), invocation]
            error.add_note(f"synchronous workflow {reference!r}, instance {item['id']}")
            raise
        finally:
            _dispatch(lambda:self.instances.pop(item['id'],None))

    def _reference(self, reference, sender):
        owner = self._instance(sender)['workflow'] if sender else None
        return workflow_reference(reference, root=owner.get('root','') if isinstance(owner,dict) else '')

    def _declared(self, sender, reference, operation):
        if sender is None:
            return
        owner = self._instance(sender)['workflow']
        binding = self.bindings.get(_key(owner)) if isinstance(owner,dict) else None
        if binding and not any(action['operation'] == operation and action['workflow'] == reference
                               for action in binding[0].get('calls', ())):
            raise CoordinationError('VF_WORKFLOW_UNDECLARED', f'{operation} target was not declared')

    async def run(self, reference, inputs=None):
        """Explicit host entry, using the same owned execution path as Call."""
        reference, descriptor, runner, entry = self._target(reference)
        item = self.reserve(workflow=reference, inputs=inputs)
        self.register({'id':item['id'],'workflow':reference,'stop_supported':True})
        self._start(item, descriptor, runner, entry)
        await asyncio.shield(item['task'])
        return self.status(item)

    def _start(self, item, descriptor, runner, entry):
        async def execute():
            try:
                result = runner(json_value(item['inputs']), {'entry':entry,
                    'workflow_instance_id':item['id'],
                    'capabilities':{'vibeflow.workflow':self.operations(item['id'])}})
                if descriptor['entry_mode'] == 'sync' and (inspect.isawaitable(result) or isinstance(result,Future)):
                    if inspect.iscoroutine(result):result.close()
                    raise CoordinationError('VF_COMPLETION_MISMATCH','sync target returned pending work')
                if inspect.isawaitable(result):result = await result
                self.complete(item,'succeeded',result)
            except asyncio.CancelledError as error:
                self.complete(item,'cancelled',error=self._error(error))
            except BaseException as error:
                self.complete(item,'cancelled' if item['stop_requested'] or getattr(error,'code','')=='VF_ABORTED' else 'failed',
                              error=self._error(error))
        from contextvars import Context
        item['task'] = asyncio.create_task(execute(),context=Context())
        def completed(task):
            if task.cancelled() and item['state'] not in TERMINAL:self.complete(item,'cancelled')
        item['task'].add_done_callback(completed)

    _error = staticmethod(error_record)

    async def call(self, sender, request, *, wait_ready=True, signal=None):
        reference = workflow_reference(request['workflow'],root=self._instance(sender)['workflow'].get('root','') if isinstance(self._instance(sender)['workflow'],dict) else '')
        launch = launch_configuration(request['launch'])
        declarations = [item for item in self.launches if item['workflow']==reference and item['launch']==launch
                        and (not item.get('caller') or isinstance(self._instance(sender)['workflow'],dict)
                             and _key(item['caller'])==_key(self._instance(sender)['workflow']))]
        if not declarations:raise CoordinationError('VF_LAUNCH_UNDECLARED','Call must match a declared workflow and launch')
        if launch['kind']=='in_process':
            _, descriptor, runner, entry = self._target(reference)
        elif self.launcher is None:
            raise CoordinationError('VF_LAUNCH_UNSUPPORTED','process launcher was not supplied')
        item = self.reserve(workflow=reference,inputs=request.get('inputs'))
        if launch['kind']=='process':
            try:self.launcher(item,launch,declarations)
            except Exception as error:
                self.complete(item,'failed',error={'code':'VF_LAUNCH_FAILED','message':str(error)})
                raise
        else:
            self.register({'id':item['id'],'workflow':reference,'stop_supported':True})
            self._start(item, descriptor, runner, entry)
        if not wait_ready:return {'id':item['id']}
        return await self.wait_for('ready',item['id'],timeout=request.get('timeout'),signal=signal)

    def request_stop(self, item, workflow=None):
        if workflow is not None:
            reference=workflow_reference(workflow)
            if not isinstance(item['workflow'],dict) or _key(reference)!=_key(item['workflow']):
                raise CoordinationError('VF_WORKFLOW_MISMATCH',item['id'])
        if item['state'] not in TERMINAL:
            if not item['stop_supported']:raise CoordinationError('VF_STOP_UNSUPPORTED',item['id'])
            item.update(stop_requested=True,state='stopping')
            if item['task'] is not None:item['task'].cancel()
            self._notify(item)

    def operations(self, identifier):
        from .operations import Operation
        # Ordinary nodes in an async graph run on owned workers. Immediate
        # operations still mutate instance state on the host's event loop.
        try:owner_loop = asyncio.get_running_loop()
        except RuntimeError:owner_loop = None
        def immediate(callback):
            if owner_loop is None:
                return callback()
            try:current_loop = asyncio.get_running_loop()
            except RuntimeError:current_loop = None
            if current_loop is owner_loop:
                return callback()
            from concurrent.futures import Future
            outcome = Future()
            def execute():
                try:outcome.set_result(callback())
                except BaseException as error:outcome.set_exception(error)
            owner_loop.call_soon_threadsafe(execute)
            return outcome.result()
        async def call(request,signal):return await self.call(identifier,request,signal=signal)
        async def wait(request,signal):return await self.wait_for('wait',request['id'],timeout=request.get('timeout'),signal=signal)
        async def receive(request,signal):return await self.wait_for('receive',identifier,port=request.get('port','default'),timeout=request.get('timeout'),signal=signal)
        async def kill(request,signal):
            self.request_stop(self._instance(request['id']),request['workflow'])
            return await wait(request,signal)
        return {'invoke_sync':Operation(lambda request,signal:self.invoke_sync(request,sender=identifier,_dispatch=immediate)),
                'call':Operation(call),'wait':Operation(wait),'receive':Operation(receive),'kill':Operation(kill),
                'send':Operation(lambda request,signal:immediate(lambda:self.send(identifier,request['id'],request.get('payload'),request.get('port','default'))))}

    def release(self, identifier):
        item=self._instance(identifier)
        if item['state'] not in TERMINAL:raise CoordinationError('VF_INSTANCE_RUNNING',identifier)
        del self.instances[identifier]

    async def aclose(self):
        self.closed=True
        tasks=[]
        for item in self.instances.values():
            self._notify(item)
            if item['task'] is not None:
                if item['state'] not in TERMINAL:self.request_stop(item)
                tasks.append(item['task'])
        await asyncio.gather(*tasks,return_exceptions=True)
        self.instances.clear()
