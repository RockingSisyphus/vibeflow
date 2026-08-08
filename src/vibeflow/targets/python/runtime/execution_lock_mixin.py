"""Runtime integration for execution leases and ambient-state scopes."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.flow import STATUS_PLANNED
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.execution_locks import (
    CURRENT_EXECUTION_LEASE,
    PROCESS_EXECUTION_LOCK_COORDINATOR,
    ExecutionLease,
    ExecutionLockToken,
)


_CURRENT_EXECUTION_LOCK_STACK: ContextVar[tuple[tuple[str, str], ...]] = ContextVar(
    "vibeflow_python_execution_lock_stack",
    default=(),
)
_CURRENT_EXECUTION_PROTECTION_DEPTH: ContextVar[int] = ContextVar(
    "vibeflow_python_execution_protection_depth",
    default=0,
)


@dataclass(frozen=True)
class _HeldExecutionLock:
    token: ExecutionLockToken
    context_token: object


class RuntimeExecutionLockMixin:
    def _reset_execution_lock_state(self) -> None:
        self._lease: ExecutionLease | None = None
        self._lease_context_token = None
        self._root_protection_context_token = None
        self._run_lock_tokens: list[tuple[_HeldExecutionLock, str]] = []
        self._protected_futures: list[object] = []
        self._global_state_started = False
        self._global_state_nodes: list[str] = []

    def _begin_execution_lease(self) -> None:
        inherited = CURRENT_EXECUTION_LEASE.get()
        self._lease = inherited or ExecutionLease.create()
        self._lease_context_token = CURRENT_EXECUTION_LEASE.set(self._lease)
        try:
            root_lock = self.graph.execution_lock
            if root_lock is not None:
                scope = "block" if self._trace_path_prefix else "root"
                held = self._acquire_execution_lock(
                    root_lock.key,
                    mode="exclusive",
                    scope=scope,
                )
                self._run_lock_tokens.append((held, scope))
            if (
                _CURRENT_EXECUTION_PROTECTION_DEPTH.get() > 0
                or root_lock is not None
            ):
                self._root_protection_context_token = (
                    _CURRENT_EXECUTION_PROTECTION_DEPTH.set(
                        _CURRENT_EXECUTION_PROTECTION_DEPTH.get() + 1
                    )
                )
        except BaseException:
            try:
                self._release_run_execution_locks()
            finally:
                self._reset_root_protection_context()
                self._reset_lease_context()
            raise

    def _end_execution_lease(self) -> None:
        try:
            self._release_run_execution_locks()
        finally:
            try:
                self._reset_root_protection_context()
            finally:
                self._reset_lease_context()
                self._lease = None

    def _reset_root_protection_context(self) -> None:
        token = self._root_protection_context_token
        self._root_protection_context_token = None
        if token is not None:
            _CURRENT_EXECUTION_PROTECTION_DEPTH.reset(token)

    def _reset_lease_context(self) -> None:
        token = self._lease_context_token
        self._lease_context_token = None
        if token is not None:
            CURRENT_EXECUTION_LEASE.reset(token)

    def _release_run_execution_locks(self) -> None:
        pending = list(reversed(self._run_lock_tokens))
        self._run_lock_tokens = []
        first_error: BaseException | None = None
        for held, scope in pending:
            try:
                self._release_execution_lock(held, scope=scope)
            except BaseException as exc:
                # One trace or release failure must never strand the other
                # execution domains held by this root lease.
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    def _acquire_execution_lock(
        self,
        key: str,
        *,
        mode: str,
        scope: str,
        node_name: str = "pipeline",
        node_type: str = "pipeline",
    ) -> _HeldExecutionLock:
        lease = self._lease
        if lease is None:  # pragma: no cover - guarded by run lifecycle
            raise RuntimeError("execution lock acquired without a run lease")
        details = {
            "run_id": lease.run_id,
            "lease_id": lease.lease_id,
            "key": key,
            "domain": key,
            "scope": scope,
            "mode": mode,
            "wait_ms": 0.0,
        }
        self._record_runtime_event(
            "lock_wait",
            node_name,
            node_type,
            details=details,
        )
        lock_stack = _CURRENT_EXECUTION_LOCK_STACK.get()
        active_user_keys = tuple(
            held_key
            for held_key, _held_scope in lock_stack
            if not held_key.startswith("vibeflow.")
        )
        if (
            not key.startswith("vibeflow.")
            and any(held_key != key for held_key in active_user_keys)
        ):
            raise PipelineRuntimeError(
                f"cannot acquire execution lock '{key}' while user lock "
                f"'{active_user_keys[-1]}' is held"
            )
        acquisition = PROCESS_EXECUTION_LOCK_COORDINATOR.acquire(
            key,
            mode=mode,
            lease=lease,
            allow_reentrant=any(held_key == key for held_key, _ in lock_stack),
        )
        acquired_details = dict(details)
        acquired_details["wait_ms"] = acquisition.waited_ms
        acquired_details["reentrant"] = acquisition.token.reentrant
        try:
            self._record_runtime_event(
                "lock_acquired",
                node_name,
                node_type,
                details=acquired_details,
            )
        except BaseException:
            # The coordinator already granted the lock. If trace persistence
            # fails before the handle is returned to a caller, release it here
            # because no outer finally block can know about the token yet.
            PROCESS_EXECUTION_LOCK_COORDINATOR.release(acquisition.token)
            raise
        context_token = _CURRENT_EXECUTION_LOCK_STACK.set(
            (*lock_stack, (key, scope))
        )
        return _HeldExecutionLock(acquisition.token, context_token)

    def _release_execution_lock(
        self,
        held: _HeldExecutionLock,
        *,
        scope: str,
        node_name: str = "pipeline",
        node_type: str = "pipeline",
    ) -> None:
        token = held.token
        try:
            PROCESS_EXECUTION_LOCK_COORDINATOR.release(token)
        finally:
            _CURRENT_EXECUTION_LOCK_STACK.reset(held.context_token)
        lease = self._lease
        self._record_runtime_event(
            "lock_released",
            node_name,
            node_type,
            details={
                "run_id": lease.run_id if lease is not None else "",
                "lease_id": token.lease_id,
                "key": token.key,
                "domain": token.key,
                "scope": scope,
                "mode": token.mode,
                "reentrant": token.reentrant,
            },
        )

    @contextmanager
    def _frame_execution_scope(self, frame: object) -> Iterator[None]:
        node_name = str(getattr(frame, "name", "node"))
        node_type = str(getattr(frame, "node_type", "node"))
        is_planned = getattr(frame, "status", "implemented") == STATUS_PLANNED
        lock = None if is_planned else getattr(frame, "execution_lock", None)
        lock_scope = (
            "block"
            if getattr(frame, "is_nodeset", False)
            or getattr(frame, "is_loop", False)
            else "node"
        )
        held_lock: _HeldExecutionLock | None = None
        if lock is not None:
            held_lock = self._acquire_execution_lock(
                lock.key,
                mode="exclusive",
                scope=lock_scope,
                node_name=node_name,
                node_type=node_type,
            )
        is_global_state = (
            not is_planned
            and getattr(frame, "flow_kind", "") == FLOW_KIND_GLOBAL_STATE
        )
        protection_context_token = None
        failed = False
        global_state_entered = False
        primary_error: BaseException | None = None
        try:
            if held_lock is not None:
                protection_context_token = (
                    _CURRENT_EXECUTION_PROTECTION_DEPTH.set(
                        _CURRENT_EXECUTION_PROTECTION_DEPTH.get() + 1
                    )
                )
            if is_global_state:
                self._record_runtime_event(
                    "global_state_enter",
                    node_name,
                    node_type,
                    details=self._lease_details(),
                )
                self._global_state_started = True
                self._global_state_nodes.append(node_name)
                if self._lease is not None:
                    qualified = ".".join(
                        self._trace_event_path((node_name,))
                    )
                    self._lease.global_state_nodes.append(
                        qualified or node_name
                    )
                global_state_entered = True
            yield
        except BaseException as exc:
            failed = True
            primary_error = exc
            raise
        finally:
            cleanup_error: BaseException | None = None
            if global_state_entered:
                try:
                    details = self._lease_details()
                    details["failed"] = failed
                    self._record_runtime_event(
                        "global_state_exit",
                        node_name,
                        node_type,
                        details=details,
                    )
                except BaseException as exc:
                    cleanup_error = exc
            try:
                if held_lock is not None:
                    self._release_execution_lock(
                        held_lock,
                        scope=lock_scope,
                        node_name=node_name,
                        node_type=node_type,
                    )
            except BaseException as exc:
                if cleanup_error is None:
                    cleanup_error = exc
            finally:
                if protection_context_token is not None:
                    try:
                        _CURRENT_EXECUTION_PROTECTION_DEPTH.reset(
                            protection_context_token
                        )
                    except BaseException as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error

    def _lease_details(self) -> dict[str, object]:
        lease = self._lease
        lock_stack = _CURRENT_EXECUTION_LOCK_STACK.get()
        effective_key, effective_scope = (
            lock_stack[-1] if lock_stack else (None, None)
        )
        return {
            "run_id": lease.run_id if lease is not None else "",
            "lease_id": lease.lease_id if lease is not None else "",
            "key": effective_key,
            "domain": effective_key,
            "scope": effective_scope,
        }

    def _track_protected_future(
        self,
        future: object,
        *,
        force: bool = False,
    ) -> None:
        if force or self._execution_scope_is_protected():
            self._protected_futures.append(future)

    def _untrack_protected_future(self, future: object) -> None:
        self._protected_futures = [
            item for item in self._protected_futures if item is not future
        ]

    @staticmethod
    def _execution_scope_is_protected() -> bool:
        return _CURRENT_EXECUTION_PROTECTION_DEPTH.get() > 0

    def _drain_protected_tasks(
        self,
        *,
        fail_on_unjoined: bool = False,
    ) -> None:
        pending = self._protected_futures
        self._protected_futures = []
        first_error: BaseException | None = None
        for future in pending:
            result = getattr(future, "result", None)
            if not callable(result):
                continue
            try:
                # No timeout is intentional: a protected task may not escape
                # its lease. Static validation prevents detached/unjoined work;
                # this is the runtime fail-safe for failures and cancellation.
                result()
            except BaseException as exc:
                # The normal join/flush path owns task error reporting and the
                # original pipeline failure must remain authoritative.
                if first_error is None:
                    first_error = exc
        if not fail_on_unjoined or not pending:
            return
        if first_error is not None:
            raise PipelineRuntimeError(
                "protected async task failed before its scheduled join: "
                f"{first_error}"
            ) from first_error
        raise PipelineRuntimeError(
            "protected async task reached cleanup without its scheduled join"
        )


__all__ = ["RuntimeExecutionLockMixin"]
