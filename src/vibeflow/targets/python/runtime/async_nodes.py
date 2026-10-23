"""Native asynchronous node mixin."""
from __future__ import annotations
import time
from typing import Mapping
from vibeflow.targets.python.runtime.block_compiler import loop_block, nodeset_block
from vibeflow.targets.python.project.registry import NodeRegistryError
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError, normalize_delegate_cli_system_exit
from vibeflow.targets.python.runtime.helpers import elapsed_ms
from vibeflow.targets.python.runtime.summaries import summarize_mapping

class AsyncRuntimeNodeMixin:

    async def _execute_frame_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        self._signal.throw_if_aborted()
        async with self._frame_execution_scope_async(frame):
            if frame.is_planned_stub:
                outputs = await self._run_planned_stub_node_async(frame, inputs)
            elif frame.is_loop:
                if loop_block(self._plan, frame.id) is not None:
                    outputs = await self._run_loop_block_node_async(frame, inputs)
                else:
                    outputs = await self._run_loop_node_async(frame, inputs)
            elif frame.is_nodeset:
                if nodeset_block(self._plan, frame.id) is not None:
                    outputs = await self._run_nodeset_block_node_async(frame, inputs)
                else:
                    outputs = await self._run_nodeset_node_async(frame, inputs)
            else:
                outputs = await self._run_pure_node_async(frame, inputs)
        return outputs

    async def _run_planned_stub_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        try:
            await self._call_runtime_plugins_async('before_node', frame.id, frame.definition_id, summarize_mapping(inputs))
            outputs = self._execute_planned_stub_outputs(frame, inputs)
            self._mark_node_run(frame.id)
            self._record_runtime_event('planned_stub', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started), details={'stub_module': frame.planned_stub_module, 'stub_path': frame.planned_stub_path, 'stub_sha256': frame.planned_stub_hash, 'input_types': list(inputs), 'output_keys': list(outputs)})
            await self._call_runtime_plugins_async('after_node', frame.id, frame.definition_id, summarize_mapping(outputs))
            return outputs
        except SystemExit as exc:
            if self.delegate_cli:
                try:
                    exit_signal = normalize_delegate_cli_system_exit(exc, source=frame.id, effect_scope=frame.effect_scope)
                except PipelineRuntimeError as denied:
                    failure = denied
                else:
                    raise exit_signal from exc
            else:
                failure = PipelineRuntimeError(f"planned python_stub node '{frame.id}' attempted SystemExit outside delegate CLI mode")
            self._record_runtime_event('node_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(failure), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(failure))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event('node_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _run_pure_node_async(self, frame: NodeFrame, inputs: Mapping[str, object]) -> Mapping[str, object]:
        started = time.perf_counter()
        try:
            node = frame.node
            if node is None:
                raise PipelineRuntimeError(f"node '{frame.id}' has no bound callable")
            await self._call_runtime_plugins_async('before_node', frame.id, frame.definition_id, summarize_mapping(inputs))
            outputs = await self._execute_pure_outputs_async(frame, inputs)
            self._mark_node_run(frame.id)
            self._record_runtime_event('node', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), output_summary=summarize_mapping(outputs), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('after_node', frame.id, frame.definition_id, summarize_mapping(outputs))
            return outputs
        except SystemExit as exc:
            if not self.delegate_cli:
                failure = PipelineRuntimeError(f"node '{frame.id}' attempted SystemExit outside delegate CLI mode")
                self._record_runtime_event('node_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(failure), elapsed_ms=elapsed_ms(started))
                await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(failure))
                raise failure from exc
            try:
                exit_signal = normalize_delegate_cli_system_exit(exc, source=frame.id, effect_scope=frame.effect_scope)
            except PipelineRuntimeError as failure:
                self._record_runtime_event('node_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(failure), elapsed_ms=elapsed_ms(started))
                await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(failure))
                raise failure from exc
            raise exit_signal from exc
        except NodeRegistryError as exc:
            failure = PipelineRuntimeError(str(exc))
            self._record_runtime_event('node_failed', frame.id, frame.definition_id, failure=str(failure), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(failure))
            raise failure from exc
        except Exception as exc:
            self._record_runtime_event('node_failed', frame.id, frame.definition_id, input_summary=summarize_mapping(inputs), failure=str(exc), elapsed_ms=elapsed_ms(started))
            await self._call_runtime_plugins_async('node_failed', frame.id, frame.definition_id, str(exc))
            raise

    async def _execute_pure_outputs_async(self, frame, inputs):
        from .lifecycle import NodeRunContext
        from .completion import immediate
        from .async_support import owned_thread, finish_cleanup
        params = self.registry.merge_config(frame.definition_id, {k: v for k, v in frame.params.items() if k != '_global'})
        if '_global' in frame.params:
            params['_global'] = frame.params['_global']
        context = NodeRunContext(self, frame) if frame.accepts_context else None
        primary = None

        def invoke():
            return frame.node.run_pure(inputs, params, context) if context else frame.node.run_pure(inputs, params)
        try:
            if frame.completion == 'suspend':
                outputs = await invoke()
            else:
                outputs = immediate(await owned_thread(invoke, context.signal if context else self._signal, name=f"vibeflow-node:{frame.id}"))
            self._signal.throw_if_aborted()
            return self._validate_outputs(frame, outputs)
        except BaseException as error:
            primary = error
            raise
        finally:
            if context:
                try:
                    await finish_cleanup(context.close_async())
                except BaseException as cleanup:
                    if primary is None:
                        raise
                    primary.cleanup_errors = [*getattr(primary, 'cleanup_errors', ()), cleanup]
