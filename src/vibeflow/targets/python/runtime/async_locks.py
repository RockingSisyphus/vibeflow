"""Native asynchronous execution lock mixin."""
from __future__ import annotations
from typing import Iterator
from vibeflow.core.constants import FLOW_KIND_GLOBAL_STATE
from vibeflow.core.flow import STATUS_PLANNED
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.execution_locks import CURRENT_EXECUTION_LEASE, PROCESS_EXECUTION_LOCK_COORDINATOR, ExecutionLease
from .execution_lock_mixin import _HeldExecutionLock, _CURRENT_EXECUTION_LOCK_STACK, _CURRENT_EXECUTION_PROTECTION_DEPTH
from contextlib import asynccontextmanager

class AsyncRuntimeExecutionLockMixin:

    async def _begin_execution_lease_async(self) -> None:
        inherited = CURRENT_EXECUTION_LEASE.get()
        self._lease = inherited or ExecutionLease.create()
        self._lease_context_token = CURRENT_EXECUTION_LEASE.set(self._lease)
        try:
            root_lock = self.graph.execution_lock
            if root_lock is not None:
                scope = 'block' if self._trace_path_prefix else 'root'
                held = await self._acquire_execution_lock_async(root_lock.key, mode='exclusive', scope=scope)
                self._run_lock_tokens.append((held, scope))
            if _CURRENT_EXECUTION_PROTECTION_DEPTH.get() > 0 or root_lock is not None:
                self._root_protection_context_token = _CURRENT_EXECUTION_PROTECTION_DEPTH.set(_CURRENT_EXECUTION_PROTECTION_DEPTH.get() + 1)
        except BaseException:
            try:
                self._release_run_execution_locks()
            finally:
                self._reset_root_protection_context()
                self._reset_lease_context()
            raise

    async def _acquire_execution_lock_async(self, key: str, *, mode: str, scope: str, node_name: str='pipeline', definition_id: str='pipeline') -> _HeldExecutionLock:
        lease = self._lease
        if lease is None:
            raise RuntimeError('execution lock acquired without a run lease')
        details = {'run_id': lease.run_id, 'lease_id': lease.lease_id, 'key': key, 'domain': key, 'scope': scope, 'mode': mode, 'wait_ms': 0.0}
        self._record_runtime_event('lock_wait', node_name, definition_id, details=details)
        lock_stack = _CURRENT_EXECUTION_LOCK_STACK.get()
        active_user_keys = tuple((held_key for held_key, _held_scope in lock_stack if not held_key.startswith('vibeflow.')))
        if not key.startswith('vibeflow.') and any((held_key != key for held_key in active_user_keys)):
            raise PipelineRuntimeError(f"cannot acquire execution lock '{key}' while user lock '{active_user_keys[-1]}' is held")
        import asyncio
        from .lifecycle import NodeCancelled
        self._signal.throw_if_aborted()
        loop, task = asyncio.get_running_loop(), asyncio.current_task()
        unsubscribe = self._signal.subscribe(lambda reason: loop.call_soon_threadsafe(task.cancel))
        try:
            acquisition = await PROCESS_EXECUTION_LOCK_COORDINATOR.acquire_async(key, mode=mode, lease=lease, allow_reentrant=any((held_key == key for held_key, _ in lock_stack)))
        except asyncio.CancelledError:
            if self._signal.aborted:
                raise NodeCancelled('VF_ABORTED: cancelled while waiting for execution lock')
            raise
        finally:
            unsubscribe()
        acquired_details = dict(details)
        acquired_details['wait_ms'] = acquisition.waited_ms
        acquired_details['reentrant'] = acquisition.token.reentrant
        try:
            self._record_runtime_event('lock_acquired', node_name, definition_id, details=acquired_details)
        except BaseException:
            PROCESS_EXECUTION_LOCK_COORDINATOR.release(acquisition.token)
            raise
        context_token = _CURRENT_EXECUTION_LOCK_STACK.set((*lock_stack, (key, scope)))
        return _HeldExecutionLock(acquisition.token, context_token)

    @asynccontextmanager
    async def _frame_execution_scope_async(self, frame: object) -> Iterator[None]:
        node_name = frame.id
        definition_id = frame.definition_id
        is_planned = getattr(frame, 'status', 'implemented') == STATUS_PLANNED
        lock = None if is_planned else getattr(frame, 'execution_lock', None)
        lock_scope = 'block' if getattr(frame, 'is_nodeset', False) or getattr(frame, 'is_loop', False) else 'node'
        held_lock: _HeldExecutionLock | None = None
        if lock is not None:
            held_lock = await self._acquire_execution_lock_async(lock.key, mode='exclusive', scope=lock_scope, node_name=node_name, definition_id=definition_id)
        is_global_state = not is_planned and getattr(frame, 'flow_kind', '') == FLOW_KIND_GLOBAL_STATE
        protection_context_token = None
        failed = False
        global_state_entered = False
        primary_error: BaseException | None = None
        try:
            self._signal.throw_if_aborted()
            if held_lock is not None:
                protection_context_token = _CURRENT_EXECUTION_PROTECTION_DEPTH.set(_CURRENT_EXECUTION_PROTECTION_DEPTH.get() + 1)
            if is_global_state:
                self._record_runtime_event('global_state_enter', node_name, definition_id, details=self._lease_details())
                self._global_state_started = True
                self._global_state_nodes.append(node_name)
                if self._lease is not None:
                    qualified = '.'.join(self._trace_event_path((node_name,)))
                    self._lease.global_state_nodes.append(qualified or node_name)
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
                    details['failed'] = failed
                    self._record_runtime_event('global_state_exit', node_name, definition_id, details=details)
                except BaseException as exc:
                    cleanup_error = exc
            try:
                if held_lock is not None:
                    self._release_execution_lock(held_lock, scope=lock_scope, node_name=node_name, definition_id=definition_id)
            except BaseException as exc:
                if cleanup_error is None:
                    cleanup_error = exc
            finally:
                if protection_context_token is not None:
                    try:
                        _CURRENT_EXECUTION_PROTECTION_DEPTH.reset(protection_context_token)
                    except BaseException as exc:
                        if cleanup_error is None:
                            cleanup_error = exc
            if primary_error is None and cleanup_error is not None:
                raise cleanup_error
