"""Live status, business output and kernel diagnostics for one run."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import traceback
from tempfile import NamedTemporaryFile
from threading import Event, RLock, Thread

from vibeflow.core.run_status import run_status_record, snapshot_info


_CURRENT = ContextVar("vibeflow_run_observation", default=None)
_STREAM_LOCK = RLock()
_STREAM_USERS = 0
_STREAM_ORIGINALS = None


def current_observation():
    return _CURRENT.get()


def update_run_info(info: list[dict[str, object]]) -> None:
    """Replace this run's cached info; the next heartbeat publishes it."""
    observer = current_observation()
    if observer is None:
        raise RuntimeError("update_run_info requires an active VibeFlow run")
    observer.update_info(info)


class _BusinessStream:
    def __init__(self, original):
        self.original = original
        self._isatty = getattr(original, "isatty", lambda: False)()

    def write(self, text):
        observer = current_observation()
        if observer is not None and not observer.capture_fds:
            observer.write_business(text)
        return self.original.write(text)

    def isatty(self):
        return self._isatty

    def flush(self):
        return self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


@contextmanager
def _console_streams():
    global _STREAM_USERS, _STREAM_ORIGINALS
    with _STREAM_LOCK:
        if _STREAM_USERS == 0:
            _STREAM_ORIGINALS = (sys.stdout, sys.stderr)
            sys.stdout = _BusinessStream(sys.stdout)
            sys.stderr = _BusinessStream(sys.stderr)
        _STREAM_USERS += 1
    try:
        yield
    finally:
        with _STREAM_LOCK:
            _STREAM_USERS -= 1
            if _STREAM_USERS == 0:
                sys.stdout, sys.stderr = _STREAM_ORIGINALS
                _STREAM_ORIGINALS = None


class RunObservation:
    def __init__(self, run_dir, *, interval: float = 60, status_file=None):
        self._origin = Path.cwd()
        self.run_dir = Path(run_dir).resolve()
        self.status_file = Path(status_file).resolve() if status_file else self.run_dir / "status.json"
        self.interval = interval
        self._lock = RLock()
        self._stop = Event()
        self._wake = Event()
        self._info = []
        self._state = "starting"
        self._error = None
        self._closed = False
        self._heartbeat_error = None
        self._thread = None
        self._business = None
        self._kernel = None
        self.capture_fds = False
        self.terminal_stdout = None

    @property
    def result(self):
        """A read-only status snapshot for operation observers."""
        from types import MappingProxyType
        with self._lock:
            return MappingProxyType({"status": self._state, "error": self._error})

    def open(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        self._business = (self.run_dir / "business.log").open("w", encoding="utf-8", buffering=1)
        self._kernel = (self.run_dir / "vibeflow.log").open("w", encoding="utf-8", buffering=1)
        try:
            self.transition("starting")
        except BaseException:
            self.close()
            raise
        self._thread = Thread(target=self._heartbeat, name="vibeflow-status", daemon=True)
        self._thread.start()

    def _heartbeat(self):
        while not self._stop.is_set():
            if self._wake.wait(self.interval):
                self._wake.clear()
                continue
            try:
                self.publish()
            except OSError as exc:
                self._heartbeat_error = exc
                self._stop.set()

    def update_info(self, info):
        value = snapshot_info(info)
        with self._lock:
            if self._closed:
                raise RuntimeError("cannot update info after the run has finished")
            self._info = value

    def transition(self, state, error=None):
        with self._lock:
            run_status_record(state, error, "", self._info)
            if (state, error) == (self._state, self._error) and self.status_file.exists():
                return
            self._state = state
            self._error = error
            self.write_kernel(f"STATE {state}" + (f" {error}" if error else ""))
            self.publish()

    def configure(self, options):
        """Apply the effective root workflow options before business execution."""
        if self._state != "starting":
            return
        self.interval = options.status_interval
        self._wake.set()
        if options.status_file is not None:
            self.status_file = (self._origin / options.status_file).resolve()
            self.status_file.parent.mkdir(parents=True, exist_ok=True)
            self.publish()

    def publish(self):
        with self._lock:
            if self._closed:
                return
            if self._heartbeat_error is not None:
                raise self._heartbeat_error
            stamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            record = run_status_record(self._state, self._error, stamp, self._info)
            temporary = None
            try:
                with NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.status_file.parent,
                                        prefix="." + self.status_file.name + "-", delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump(record, stream, ensure_ascii=False, allow_nan=False)
                    stream.write("\n")
                os.replace(temporary, self.status_file)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)

    def write_business(self, text):
        with self._lock:
            if not self._closed and self._business is not None:
                self._business.write(text)
                self._business.flush()

    def write_kernel(self, message):
        with self._lock:
            if not self._closed and self._kernel is not None:
                self._kernel.write(str(message) + "\n")
                self._kernel.flush()

    def close(self):
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join()
        with self._lock:
            self._closed = True
            for stream in (self._business, self._kernel):
                if stream is not None:
                    stream.close()

    @contextmanager
    def scope(self):
        self.open()
        token = _CURRENT.set(self)
        try:
            with _console_streams():
                yield self
        except BaseException as exc:
            try:
                self.write_kernel("".join(traceback.format_exception(exc)))
                self.transition("failed", str(exc) or type(exc).__name__)
            except OSError:
                pass  # Preserve the execution error if the output device also fails.
            raise
        else:
            if self._state != "failed":
                self.transition("succeeded")
        finally:
            _CURRENT.reset(token)
            self.close()


@contextmanager
def observe_run(run_dir, options):
    observer = current_observation()
    if observer is not None:
        yield observer
        return
    with RunObservation(run_dir, interval=options.status_interval,
                        status_file=options.status_file).scope() as observer:
        yield observer
