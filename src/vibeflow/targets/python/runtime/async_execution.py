"""Native asynchronous engine."""
from __future__ import annotations
from typing import Any, Mapping
from vibeflow.targets.python.runtime.block_compiler import graph_block
from vibeflow.core.contracts import DataEnvelope, RunResult
from vibeflow.targets.python.runtime.errors import DelegateCliExit, PipelineRuntimeError
from vibeflow.targets.python.runtime.options import runtime_hook_plan
from vibeflow.targets.python.runtime.trace import RuntimeTraceSink
from vibeflow.targets.python.runtime.types import _RuntimeState
from vibeflow.targets.python.runtime.observation import observe_run
from vibeflow.targets.python.project.plugins import plugin_lifetime_async
from .compiled import run_compiled_steps_async
from .completion import suspended

class AsyncPipelineRuntime:

    async def run_async(self, initial: Mapping[str, Any] | None=None) -> RunResult:
        self._assert_entry_mode('async')
        factory = getattr(self, '_runtime_plugin_factory', None)
        if factory is None or not self._owns_run:
            return await self._run_with_observation_async(initial)
        from vibeflow.targets.python.sdk.loading import source_paths
        with source_paths(self._bundle_source_roots), observe_run(self._run_dir, self.runtime_options):
            async_factory = getattr(self, '_runtime_plugin_factory_async', None)
            plugins = await async_factory() if async_factory is not None else factory()
            self._plugin_registry = plugins
            async with plugin_lifetime_async(plugins):
                initialize = getattr(self, '_runtime_plan_factory', None)
                if initialize is not None:
                    self._plan = initialize(plugins)
                    self._frames = self._plan.frames
                    self._runtime_plan_factory = None
                else:
                    from dataclasses import replace
                    self._plan = replace(self._plan, python_bindings=replace(self._plan.python_bindings, plugin_registry=plugins))
                self._runtime_plugins = plugins.runtime_plugins()
                self._hook_plan = runtime_hook_plan(self._runtime_plugins, self.runtime_options)
                return await self._run_with_observation_async(initial)

    async def _run_steps_async(self, state):
        from .scheduler import run_graph_async
        await run_graph_async(self, state)

    async def _run_block_steps_async(self, state):
        block = graph_block(self._plan)
        if block is None:
            raise PipelineRuntimeError('block execution requires a compiled graph block')
        await suspended(block.callable(self, state))

    async def _call_runtime_plugins_async(self, hook, *args):
        for name, method in self._hook_plan.for_hook(hook):
            try:
                value = method(*args)
                if self._plugin_registry.completion(next(plugin for plugin in self._runtime_plugins if plugin.name == name)) == 'immediate':
                    from .completion import immediate
                    immediate(value)
                else:
                    await suspended(value)
            except Exception as cause:
                raise PipelineRuntimeError(f"runtime plugin '{name}' {hook} failed: {cause}") from cause

    async def _run_with_observation_async(self, initial: Mapping[str, Any] | None=None) -> RunResult:
        if not self._owns_run:
            return await self._run_observed_async(initial)
        if self._has_run:
            from .lifecycle import CancellationSignal
            self._signal = CancellationSignal()
        self._has_run = True
        with observe_run(self._run_dir, self.runtime_options) as observer:
            observer.configure(self.runtime_options)
            observer.transition('running')
            unsubscribe = self._signal.subscribe(lambda reason: observer.transition('stopping'))
            try:
                return await self._run_observed_async(initial)
            finally:
                unsubscribe()

    async def _run_observed_async(self, initial: Mapping[str, Any] | None=None) -> RunResult:
        owns_trace_sink = self._trace_sink is None
        if owns_trace_sink:
            self._trace_path_prefix = ()
            self._trace_sink = RuntimeTraceSink(self._trace_file_path())
            self._trace_sink.open()
        self._reset_run_state()
        initial_values = initial or {}
        state = self._new_state(initial_values)
        lease_started = False
        primary_error = None
        try:
            await self._begin_execution_lease_async()
            lease_started = True
            self._validate_public_inputs(initial_values)
            self._record_run_boundary('run_start')
            if self._owns_run:
                await self._call_runtime_plugins_async('before_run', dict(initial_values))
            if self.runtime_options.execution == 'compiled':
                await run_compiled_steps_async(self, state)
            elif self.runtime_options.execution == 'block':
                await self._run_block_steps_async(state)
            else:
                await self._run_steps_async(state)
            self._signal.throw_if_aborted()
            self.trace.stop_reason = self.trace.stop_reason or 'completed'
            self._finalize_pipeline_outputs(state)
            self._record_run_boundary('run_end')
            self._write_trace(state.result)
            if self._owns_run:
                await self._call_runtime_plugins_async('after_run', state.result.to_dict(), self.trace.to_dict())
        except DelegateCliExit as exc:
            try:
                self._signal.request_stop('business exit')
            except BaseException as cleanup:
                primary_error = cleanup
                cleanup.business_exit = {'exit_code': exc.exit_code, 'source': exc.source}
                await self._record_runtime_failure_async(state, cleanup, force_node_failed=True)
                raise
            self.trace.stop_reason = 'business_exit'
            self.trace.exception = ''
            if not owns_trace_sink:
                raise
            self._record_runtime_event('business_exit', exc.source, 'delegate_cli', details={'exit_code': exc.exit_code})
            state.result.set('cli.exit_code', DataEnvelope(key='cli.exit_code', type='cli.exit_code', value=exc.exit_code, source_node=exc.source).to_input())
            self._write_trace(state.result)
        except BaseException as exc:
            primary_error = exc
            self._signal.request_stop('workflow failed')
            await self._record_runtime_failure_async(state, exc)
            raise
        finally:
            try:
                if self.trace.exception:
                    self._record_global_state_change_warning(self.trace.exception)
            finally:
                try:
                    if lease_started:
                        self._end_execution_lease()
                        self._write_trace(state.result)
                except BaseException as cleanup:
                    if primary_error is None:
                        raise
                    primary_error.add_note(str(cleanup))
                    primary_error.cleanup_errors = [*getattr(primary_error, 'cleanup_errors', ()), cleanup]
                finally:
                    if owns_trace_sink and self._trace_sink is not None:
                        try:
                            self._trace_sink.write_summary(self.trace)
                        finally:
                            self._trace_sink.close()
                            self._trace_sink = None
        return state.result

    async def _record_runtime_failure_async(self, state: _RuntimeState, exc: BaseException, *, force_node_failed: bool=False) -> None:
        if force_node_failed:
            self.trace.stop_reason = 'node_failed'
        else:
            self.trace.stop_reason = self.trace.stop_reason or 'node_failed'
        self.trace.exception = str(exc)
        self._record_global_state_change_warning(str(exc))
        self._write_trace(state.result)
        if self._owns_run:
            try:
                await self._call_runtime_plugins_async('run_failed', state.result.to_dict(), self.trace.to_dict(), str(exc))
            except BaseException as cleanup:
                exc.add_note(str(cleanup))
                exc.cleanup_errors = [*getattr(exc, 'cleanup_errors', ()), cleanup]
