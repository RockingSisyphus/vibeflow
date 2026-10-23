"""Threaded loopback router. Launchers and hosts retain lifecycle responsibility."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import asyncio
from threading import Thread

from .protocol import CoordinationError, TERMINAL, instance_id, json_value
from vibeflow.core.workflows.references import workflow_reference, launch_configuration


class WorkflowServer:
    def __init__(self, *, launches=(), port=0):
        self.launches = tuple({"workflow": workflow_reference(item["workflow"]),
            "launch": launch_configuration(item["launch"]), "base":item.get("base", "."),
            "caller":workflow_reference(item["caller"]) if item.get("caller") else None}
            for item in launches)
        from .engine import Coordinator
        from .process_launcher import ProcessLauncher
        self.loop = asyncio.new_event_loop()
        def failed(item, code):
            def report():
                if not item['registered'] and item['state'] not in TERMINAL:
                    self.coordinator.complete(item, 'failed', error={
                        'code':'VF_LAUNCH_FAILED','message':f'launcher exited with code {code} before registration'})
            if not self.loop.is_closed():
                self.loop.call_soon_threadsafe(report)
        self.coordinator = Coordinator(launches=self.launches, launcher=ProcessLauncher(lambda: self.url, failed))
        self.instances = self.coordinator.instances
        self.loop_thread = None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_OPTIONS(self):
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_POST(self):
                try:
                    request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                    result = {"value": owner.dispatch(self.path.removeprefix("/"), request)}
                    code = 200
                except Exception as error:
                    result = {"error": {"code": getattr(error, "code", "VF_COORDINATION_REQUEST"), "message": str(error)}}
                    code = 400
                body = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The requester can cancel a wait without stopping its peer.

        self.http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.http.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.http.server_port}"
        self.thread = None

    def start(self):
        self.loop_thread = Thread(target=self.loop.run_forever, daemon=True, name="vibeflow-coordination")
        self.loop_thread.start()
        self.thread = Thread(target=self.http.serve_forever, daemon=True, name="vibeflow-router")
        self.thread.start()
        return self

    def close(self):
        # Closing routing never stops independently running workflow processes.
        if self.thread is not None:
            self.http.shutdown()
            self.thread.join()
        self.http.server_close()
        if self.loop_thread is not None:
            asyncio.run_coroutine_threadsafe(self.coordinator.aclose(), self.loop).result()
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.loop_thread.join()
        self.loop.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *error):
        self.close()

    def dispatch(self, operation, request):
        return asyncio.run_coroutine_threadsafe(self._dispatch(operation, request), self.loop).result()

    async def _dispatch(self, operation, request):
        engine = self.coordinator
        if operation == 'instances':
            return [engine.status(item) for item in engine.instances.values()]
        if operation == 'register':
            return engine.register(request)
        if operation == 'call':
            return await engine.call(request['sender'], request, wait_ready=False)
        item = engine._instance(request.get('id'))
        if operation == 'release':
            engine.release(item['id'])
            return None
        if operation == 'status':return engine.status(item)
        if operation == 'complete':return engine.complete(item,request['state'],request.get('outputs'),request.get('error'))
        if operation == 'send':
            engine.send(request['sender'],item['id'],request.get('payload'),request.get('port','default'))
            return {'accepted':True}
        if operation == 'kill':
            engine.request_stop(item,request.get('workflow'))
            return engine.status(item)
        if operation in {'ready','wait','receive','control'}:
            try:
                return await engine.wait_for(operation,item['id'],port=request.get('port','default'),
                                             timeout=min(max(float(request.get('poll',.25)),0),1))
            except CoordinationError as error:
                if error.code != 'VF_WAIT_TIMEOUT':raise
                return {'pending':True}
        raise ValueError('unknown coordination operation: '+operation)
