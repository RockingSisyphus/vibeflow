"""Run one owned process tree, reap Linux orphans and record termination."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def _subreaper() -> bool:
    if sys.platform != "linux":
        return False
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "cannot enable child subreaper")
    return True


def _children() -> list[int]:
    path = Path(f"/proc/self/task/{os.getpid()}/children")
    if path.exists():
        return [int(pid) for pid in path.read_text().split()]
    # Some managed procfs implementations omit task/*/children.
    children = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[1]) == os.getpid():
                children.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
    return children


def supervise(command: list[str], *, state_path: Path | None = None,
              timeout: float | None = None, grace: float = 5) -> int:
    """Own only this command and its descendants; never signal unrelated jobs."""
    reaper = _subreaper()
    state = {"status": "running", "supervisor_pid": os.getpid(),
             "started_at": datetime.now(timezone.utc).isoformat(),
             "subreaper": reaper, "reaped_descendants": 0,
             "received_signal": None, "root_returncode": None,
             "cleanup_complete": False, "timed_out": False}

    def save():
        if state_path:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            temp = state_path.with_suffix(state_path.suffix + ".tmp")
            temp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
            temp.replace(state_path)

    def received(number, _frame):
        state["received_signal"] = number

    old_handlers = {s: signal.signal(s, received) for s in (signal.SIGTERM, signal.SIGINT)}
    process = None
    stopping_at = None
    started = time.monotonic()
    last_save = 0.0
    signaled = set()

    def stop_owned(number):
        # A new session isolates the command's group from the caller's shell.
        if os.name == "posix":
            try:
                os.killpg(process.pid, number)
            except ProcessLookupError:
                pass
        elif process.returncode is None:
            process.terminate() if number == signal.SIGTERM else process.kill()
        for pid in _children():
            key = (pid, number)
            if key not in signaled:
                try:
                    os.kill(pid, number)
                except ProcessLookupError:
                    pass
                signaled.add(key)

    try:
        env = {**os.environ, "VIBEFLOW_PROCESS_SUPERVISED": "1"}
        process = subprocess.Popen(command, env=env, start_new_session=os.name == "posix")
        state["root_pid"] = process.pid
        save()
        while True:
            no_children = False
            if os.name == "posix":
                while True:
                    try:
                        pid, status = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        no_children = True
                        break
                    if not pid:
                        break
                    code = os.waitstatus_to_exitcode(status)
                    if pid == process.pid:
                        process.returncode = code
                        state["root_returncode"] = code
                    else:
                        state["reaped_descendants"] += 1
            else:
                code = process.poll()
                if code is not None:
                    state["root_returncode"] = code
                    no_children = True
            now = time.monotonic()
            if timeout is not None and now - started >= timeout:
                state["timed_out"] = True
            if stopping_at is None and (state["received_signal"] or state["timed_out"]
                                        or state["root_returncode"] is not None):
                stopping_at = now
                state["status"] = "stopping"
                save()
            if no_children and state["root_returncode"] is not None:
                break
            if stopping_at is not None:
                stop_owned(signal.SIGKILL if now - stopping_at >= grace else signal.SIGTERM)
            if now - last_save >= 1:
                save()
                last_save = now
            time.sleep(0.05)
        interrupted = state["received_signal"] or state["timed_out"] or state["root_returncode"] < 0
        state.update(status="interrupted" if interrupted else "completed", cleanup_complete=True,
                     ended_at=datetime.now(timezone.utc).isoformat())
        save()
        if state["received_signal"]:
            return 128 + state["received_signal"]
        if state["timed_out"]:
            return 124
        code = state["root_returncode"]
        return 128 - code if code < 0 else code
    finally:
        if process is not None and not state["cleanup_complete"]:
            # Also own cleanup if state persistence or the supervision loop fails.
            deadline = time.monotonic() + grace
            while time.monotonic() < deadline:
                stop_owned(signal.SIGKILL)
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    state["cleanup_complete"] = True
                    break
                if pid == process.pid:
                    process.returncode = os.waitstatus_to_exitcode(status)
                    state["root_returncode"] = process.returncode
                elif pid:
                    state["reaped_descendants"] += 1
                else:
                    time.sleep(0.05)
            state.update(status="interrupted", ended_at=datetime.now(timezone.utc).isoformat())
            try:
                save()
            except OSError:
                pass
        for number, handler in old_handlers.items():
            signal.signal(number, handler)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--grace", type=float, default=5)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    if args.grace <= 0 or args.timeout is not None and args.timeout <= 0:
        parser.error("grace and timeout must be positive")
    return supervise(command, state_path=args.state, timeout=args.timeout, grace=args.grace)


if __name__ == "__main__":
    raise SystemExit(main())
