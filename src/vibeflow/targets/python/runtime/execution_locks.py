"""Process-wide execution-domain coordination for the Python target.

The coordinator is deliberately independent from Python thread ownership.
Framework-managed work may move between worker threads while it still belongs
to the same logical root run, so reentrancy is keyed by ``lease_id``.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Condition
import time
from uuid import uuid4


@dataclass
class ExecutionLease:
    run_id: str
    lease_id: str
    global_state_nodes: list[str] = field(default_factory=list)
    state_change_reported: bool = False

    @classmethod
    def create(cls) -> "ExecutionLease":
        run_id = uuid4().hex
        return cls(run_id=run_id, lease_id=f"lease:{run_id}")


@dataclass(frozen=True)
class ExecutionLockToken:
    key: str
    mode: str
    lease_id: str
    reentrant: bool = False


@dataclass(frozen=True)
class ExecutionLockAcquisition:
    token: ExecutionLockToken
    waited_ms: float


@dataclass
class _DomainState:
    readers: dict[str, int] = field(default_factory=dict)
    writer: str = ""
    writer_depth: int = 0
    waiting_readers: int = 0
    waiting_writers: int = 0


class ExecutionLockCoordinator:
    """A fair process-local shared/exclusive named lock coordinator."""

    def __init__(self) -> None:
        self._condition = Condition()
        self._domains: dict[str, _DomainState] = {}

    def acquire(
        self,
        key: str,
        *,
        mode: str,
        lease: ExecutionLease,
        allow_reentrant: bool = True,
    ) -> ExecutionLockAcquisition:
        if mode not in {"shared", "exclusive"}:
            raise ValueError("execution lock mode must be shared or exclusive")
        if not key:
            raise ValueError("execution lock key must be non-empty")
        started = time.perf_counter()
        with self._condition:
            state = self._domains.setdefault(key, _DomainState())
            if mode == "shared":
                token = self._acquire_shared(
                    state,
                    key=key,
                    lease=lease,
                    allow_reentrant=allow_reentrant,
                )
            else:
                token = self._acquire_exclusive(
                    state,
                    key=key,
                    lease=lease,
                    allow_reentrant=allow_reentrant,
                )
        return ExecutionLockAcquisition(
            token=token,
            waited_ms=(time.perf_counter() - started) * 1000.0,
        )

    def release(self, token: ExecutionLockToken) -> None:
        with self._condition:
            state = self._domains.get(token.key)
            if state is None:
                raise RuntimeError(f"execution lock '{token.key}' is not held")
            if token.mode == "shared":
                depth = state.readers.get(token.lease_id, 0)
                if depth <= 0:
                    raise RuntimeError(
                        f"execution lock '{token.key}' is not held shared by lease"
                    )
                if depth == 1:
                    del state.readers[token.lease_id]
                else:
                    state.readers[token.lease_id] = depth - 1
            elif token.mode == "exclusive":
                if state.writer != token.lease_id or state.writer_depth <= 0:
                    raise RuntimeError(
                        f"execution lock '{token.key}' is not held exclusively by lease"
                    )
                state.writer_depth -= 1
                if state.writer_depth == 0:
                    state.writer = ""
            else:  # pragma: no cover - tokens are constructed internally
                raise RuntimeError(f"invalid execution lock token mode: {token.mode}")
            if (
                not state.readers
                and not state.writer
                and state.waiting_readers == 0
                and state.waiting_writers == 0
            ):
                self._domains.pop(token.key, None)
            self._condition.notify_all()

    def _acquire_shared(
        self,
        state: _DomainState,
        *,
        key: str,
        lease: ExecutionLease,
        allow_reentrant: bool,
    ) -> ExecutionLockToken:
        if state.writer == lease.lease_id and allow_reentrant:
            state.writer_depth += 1
            return ExecutionLockToken(
                key=key,
                mode="exclusive",
                lease_id=lease.lease_id,
                reentrant=True,
            )
        if lease.lease_id in state.readers:
            state.readers[lease.lease_id] += 1
            return ExecutionLockToken(
                key=key,
                mode="shared",
                lease_id=lease.lease_id,
                reentrant=allow_reentrant,
            )
        # Writer preference: once an exclusive waiter appears, later readers
        # queue behind it so a steady stream of normal roots cannot starve it.
        if state.writer or state.waiting_writers:
            state.waiting_readers += 1
            try:
                while state.writer or state.waiting_writers:
                    self._condition.wait()
            finally:
                state.waiting_readers -= 1
        state.readers[lease.lease_id] = 1
        return ExecutionLockToken(
            key=key,
            mode="shared",
            lease_id=lease.lease_id,
        )

    def _acquire_exclusive(
        self,
        state: _DomainState,
        *,
        key: str,
        lease: ExecutionLease,
        allow_reentrant: bool,
    ) -> ExecutionLockToken:
        if state.writer == lease.lease_id and allow_reentrant:
            state.writer_depth += 1
            return ExecutionLockToken(
                key=key,
                mode="exclusive",
                lease_id=lease.lease_id,
                reentrant=True,
            )
        if lease.lease_id in state.readers and allow_reentrant:
            # Structured VibeFlow nesting never needs a shared-to-exclusive
            # upgrade. Failing here avoids the classic two-reader upgrade
            # deadlock for dynamically-created coordinator clients.
            raise RuntimeError(
                f"execution lease cannot upgrade shared lock '{key}' to exclusive"
            )
        state.waiting_writers += 1
        try:
            while state.writer or state.readers:
                self._condition.wait()
            state.writer = lease.lease_id
            state.writer_depth = 1
        finally:
            state.waiting_writers -= 1
            # If this waiter is cancelled/interrupted, readers that queued
            # only because writer preference was active must re-check the
            # domain immediately rather than waiting for an unrelated release.
            self._condition.notify_all()
        return ExecutionLockToken(
            key=key,
            mode="exclusive",
            lease_id=lease.lease_id,
        )


PROCESS_EXECUTION_LOCK_COORDINATOR = ExecutionLockCoordinator()
CURRENT_EXECUTION_LEASE: ContextVar[ExecutionLease | None] = ContextVar(
    "vibeflow_python_execution_lease",
    default=None,
)


__all__ = [
    "CURRENT_EXECUTION_LEASE",
    "ExecutionLease",
    "ExecutionLockAcquisition",
    "ExecutionLockCoordinator",
    "ExecutionLockToken",
    "PROCESS_EXECUTION_LOCK_COORDINATOR",
]
