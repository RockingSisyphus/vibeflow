"""Process console tee for CLI runs, including native and child-process writes."""

import codecs
from contextlib import contextmanager
import os
import sys
from threading import Thread
from threading import Event
import select


@contextmanager
def capture_process_console(observer):
    """Only CLI owns process descriptors; embedded runtimes use scoped streams."""
    if os.name != "posix":
        yield
        return
    try:
        process_streams = sys.stdout.fileno() == 1 and sys.stderr.fileno() == 2
    except (AttributeError, OSError, ValueError):
        process_streams = False
    if not process_streams:
        yield
        return
    saved = []
    readers = []
    errors = []
    finishing = Event()
    for stream in (sys.stdout, sys.stderr):
        stream.flush()

    def drain(read_fd, terminal_fd):
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            while True:
                readable, _, _ = select.select([read_fd], [], [], .05)
                if not readable:
                    if finishing.is_set():
                        # The final flush may arrive after the timed poll
                        # expires but before we observe the shutdown signal.
                        readable, _, _ = select.select([read_fd], [], [], 0)
                        if not readable:
                            break
                    else:
                        continue
                data = os.read(read_fd, 65536)
                if not data:
                    break
                observer.write_business(decoder.decode(data))
                offset = 0
                while offset < len(data):
                    offset += os.write(terminal_fd, data[offset:])
            observer.write_business(decoder.decode(b"", final=True))
        except Exception as exc:
            errors.append(exc)
        finally:
            os.close(read_fd)

    try:
        for fd in (1, 2):
            terminal_fd = os.dup(fd)
            saved.append((fd, terminal_fd))
            read_fd, write_fd = os.pipe()
            os.dup2(write_fd, fd)
            os.close(write_fd)
            thread = Thread(target=drain, args=(read_fd, terminal_fd), daemon=True)
            readers.append(thread)
            thread.start()
        observer.capture_fds = True
        observer.terminal_stdout = saved[0][1]
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        for fd, terminal_fd in saved:
            os.dup2(terminal_fd, fd)
        finishing.set()
        for thread in readers:
            thread.join()
        for _, terminal_fd in saved:
            os.close(terminal_fd)
        observer.capture_fds = False
        observer.terminal_stdout = None
        if errors and sys.exc_info()[0] is None:
            raise errors[0]
