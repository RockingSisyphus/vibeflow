"""Bind Node cancellation and dispatch immediate operations to their host loop."""
import asyncio
from concurrent.futures import Future


def immediate_dispatch():
    """Capture the host loop before ordinary async-graph nodes enter workers."""
    try:
        owner_loop = asyncio.get_running_loop()
    except RuntimeError:
        owner_loop = None

    def dispatch(callback):
        if owner_loop is None:
            return callback()
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is owner_loop:
            return callback()
        outcome = Future()

        def execute():
            try:
                outcome.set_result(callback())
            except BaseException as error:
                outcome.set_exception(error)

        owner_loop.call_soon_threadsafe(execute)
        return outcome.result()

    return dispatch



class CoordinatorSession:
    """One caller's direct access to the in-process coordinator."""
    def __init__(self, scope, identifier):
        self.scope, self.identifier = scope, identifier
        self.dispatch = immediate_dispatch()

    def invoke_sync(self, request, *, signal=None):
        return self.scope.invoke_sync(request, sender=self.identifier, _dispatch=self.dispatch)

    def send(self, request, *, signal=None):
        return self.dispatch(lambda: self.scope.send(self.identifier, request['id'],
            request.get('payload'), request.get('port', 'default')))

    async def call(self, request, *, signal=None):
        return await self.scope.call(self.identifier, request, signal=signal)

    async def wait(self, request, *, signal=None):
        return await self.scope.wait_for('wait', request['id'], timeout=request.get('timeout'), signal=signal)

    async def receive(self, request, *, signal=None):
        return await self.scope.wait_for('receive', self.identifier,
            port=request.get('port', 'default'), timeout=request.get('timeout'), signal=signal)

    async def kill(self, request, *, signal=None):
        reference = self.scope._reference(request['workflow'], self.identifier)
        self.scope.request_stop(self.scope._instance(request['id']), reference)
        return await self.wait(request, signal=signal)


class HttpSession:
    """One caller's direct access to the local HTTP workflow protocol."""
    def __init__(self, client):
        self.client = client
        self.dispatch = immediate_dispatch()

    def send(self, request, *, signal=None):
        return self.dispatch(lambda: self.client.send(request['id'], request.get('port', 'default'), request.get('payload')))

    async def call(self, request, *, signal=None):
        return await self.client.call(request['workflow'], launch=request['launch'],
            inputs=request.get('inputs'), timeout=request.get('timeout'), signal=signal)

    async def wait(self, request, *, signal=None):
        return await self.client.wait(request['id'], timeout=request.get('timeout'), signal=signal)

    async def receive(self, request, *, signal=None):
        return await self.client.receive(request.get('port', 'default'), timeout=request.get('timeout'), signal=signal)

    async def kill(self, request, *, signal=None):
        return await self.client.kill(request['id'], workflow=request['workflow'], timeout=request.get('timeout'), signal=signal)
