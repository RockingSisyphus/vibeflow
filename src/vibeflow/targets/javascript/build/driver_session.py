"""Private, bounded JSONL analysis driver owned by one formal check."""
from contextlib import ExitStack
from contextvars import ContextVar
import json
from queue import Queue, Empty
import subprocess
import tempfile
from threading import Thread


_current = ContextVar("vibeflow_javascript_driver_scope", default=None)


class DriverSession:
    def __init__(self, node_command):
        from vibeflow.targets.javascript.resources import materialized_resources
        self.stack=ExitStack()
        resources=self.stack.enter_context(materialized_resources())
        self.stderr=self.stack.enter_context(tempfile.TemporaryFile(mode="w+t",encoding="utf-8"))
        try:
            self.process=subprocess.Popen([node_command,str(resources/"toolchain_driver.mjs"),"--session"],
                stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.stderr,text=True,encoding="utf-8",bufsize=1)
        except Exception as error:
            self.stack.close()
            if isinstance(error,FileNotFoundError):
                from vibeflow.targets.javascript.build.toolchain import AotToolchainError
                raise AotToolchainError("VF_TOOLCHAIN_MISSING",f"Node.js executable was not found: {node_command}") from error
            raise
        self.responses=Queue()
        def read():
            try:
                for line in self.process.stdout:self.responses.put(line)
            except (OSError,ValueError):pass
            finally:self.responses.put("")
        self.reader=Thread(target=read,daemon=True);self.reader.start()

    def request(self, payload):
        from vibeflow.targets.javascript.build.toolchain import AotToolchainError
        self.process.stdin.write(json.dumps(dict(payload),ensure_ascii=False,allow_nan=False)+"\n")
        self.process.stdin.flush()
        try:line=self.responses.get(timeout=180)
        except Empty as error:
            raise AotToolchainError("VF_TOOLCHAIN_TIMEOUT","JavaScript analysis driver timed out") from error
        if not line:
            self.stderr.seek(0)
            raise AotToolchainError("VF_PROTOCOL","JavaScript analysis driver exited: "+self.stderr.read())
        try:return json.loads(line)
        except ValueError as error:
            raise AotToolchainError("VF_PROTOCOL","JavaScript analysis driver returned invalid JSON") from error

    def close(self):
        from vibeflow.targets.javascript.build.cleanup import finish_cleanup
        errors=[]
        def release(action):
            try:action()
            except Exception as error:errors.append(error)
        try:
            release(self.process.stdin.close)
            try:self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                release(self.process.terminate)
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    release(self.process.kill)
                    release(lambda:self.process.wait(timeout=5))
            except Exception as error:errors.append(error)
        finally:
            release(lambda:self.reader.join(timeout=1))
            release(self.process.stdout.close)
            release(self.stack.close)
        finish_cleanup(None,errors)


class DriverScope:
    def __init__(self):self.drivers={};self.rule_sessions={};self.stack=ExitStack();self._token=None
    def __enter__(self):
        self._token=_current.set(self);return self
    def request(self,payload,node_command):
        if node_command not in self.drivers:
            self.drivers[node_command]=DriverSession(node_command)
        return self.drivers[node_command].request(payload)
    def __exit__(self,kind,error,traceback):
        from vibeflow.targets.javascript.build.cleanup import finish_cleanup
        errors=[]
        try:
            try:self.stack.__exit__(kind,error,traceback)
            except Exception as cause:errors.append(cause)
            for driver in self.drivers.values():
                try:driver.close()
                except Exception as cause:errors.append(cause)
        finally:
            self.drivers.clear();self.rule_sessions.clear();_current.reset(self._token)
        finish_cleanup(error,errors)


def current_scope():return _current.get()


def check_scope(function):
    """Nested formal phases borrow the command's scope, without a public SDK API."""
    from functools import wraps
    @wraps(function)
    def wrapped(*args,**kwargs):
        if current_scope() is not None:return function(*args,**kwargs)
        with DriverScope():return function(*args,**kwargs)
    return wrapped
