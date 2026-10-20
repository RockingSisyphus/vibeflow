"""Load prepared Python workflows without source checks or graph compilation."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from uuid import uuid4

from vibeflow.block_compiler import workflow_plan_from_dict, WORKFLOW_ABI_VERSION, map_plan_sources
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.models import SourceLocator
from vibeflow.targets.python.project.registry import NodeRegistry, load_node_implementation
from vibeflow.targets.python.project.plugins import PluginRegistry, create_lifecycle_plugin
from vibeflow.targets.python.runtime.preparation import PreparedPythonWorkflow, bind_python_workflow
from vibeflow.targets.python.runtime.support.snapshot import decode_snapshot
from vibeflow.targets.python.sdk.loading import load_plugin, source_paths, load_source_module


class PythonBundle:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.metadata = json.loads((self.path / 'vibeflow-build.json').read_text())
        if self.metadata.get('format') != 'vibeflow.aot-build.v3' or self.metadata.get('abi_version') != WORKFLOW_ABI_VERSION:
            raise ValueError('unsupported Python AOT format or workflow ABI; rebuild the bundle')
        if self.metadata.get('project_target') != 'python':
            raise ValueError('bundle is not a Python workflow')
        self.data = json.loads((self.path / self.metadata['target_metadata']['bindings']).read_text())
        relocate = lambda value: str(self.path / value[len('@bundle/'):]) if isinstance(value,str) and value.startswith('@bundle/') else value
        self.workflow = map_plan_sources(workflow_plan_from_dict(self.data['workflow']),
            lambda source:replace(source,ref=relocate(source.ref)))
        self.prepared = PreparedPythonWorkflow(self.workflow,
            decode_snapshot(self.data['graphs'], relocate=relocate),
            decode_snapshot(self.data['compiled'], relocate=relocate),
            decode_snapshot(self.data['globals']), decode_snapshot(self.data['overrides']))
        self.roots = tuple(self.path / value for value in self.data['source_roots'])
        # Fixed, relocated declarations belong to the bundle, not each Runtime.
        self._node_records = tuple(self._prepare_node(record) for record in self.data['nodes'])
        self._plugin_records = tuple((self._descriptor(record['descriptor']),
            self._plugin_source(record['plugin']), record) for record in self.data['plugins'])
        self._plugin_bindings = {}
        self.generated = load_source_module(self.path / 'generated_blocks.py', '_vibeflow_aot_blocks_' + uuid4().hex)

    def _prepare_node(self, record):
        binding = dict(record['binding'])
        if 'plugin' in binding:
            binding['plugin'] = self._plugin_source(binding['plugin'])
        else:
            binding.update(path=self.path / binding['path'], load_root=self.path / binding['load_root'],
                members=tuple(binding['export'].split('.')))
        return self._descriptor(record['descriptor']), binding, self._path(record['source']), record['source_line']

    def _plugin_source(self, record):
        source = dict(record['source'])
        if source['kind'] == 'file':
            source['ref'] = self._path(source['ref'])
        return self.path / record['root'], SourceLocator(**source)

    def _bindings(self, source):
        if source not in self._plugin_bindings:
            root, locator = source
            definition = load_plugin(locator, root=root, source_roots=self.roots)
            self._plugin_bindings[source] = definition.bindings()
        return self._plugin_bindings[source]

    def _registry(self):
        registry = NodeRegistry()
        for descriptor, binding, source, line in self._node_records:
            def resolve(binding=binding, key=descriptor.id):
                if 'plugin' in binding:
                    return self._bindings(binding['plugin'])[('node',key)]
                def load():
                    with source_paths((binding['load_root'], *self.roots)):
                        value = load_source_module(binding['path'], binding['module'])
                        for part in binding['members']:
                            value = getattr(value, part)
                        return value
                return load_node_implementation(registry, key, binding['path'], binding['export'], load)
            registry.register(descriptor,loader=resolve,source=source,source_line=line)
        return registry

    def _plugins(self):
        result = PluginRegistry()
        created = []
        try:
            for descriptor, source, record in self._plugin_records:
                factory = self._bindings(source).get(('plugin',descriptor.id))
                if factory is None:
                    locator = descriptor.implementations[0].source
                    module = load_source_module(self.path / record['factory_path'], '_vibeflow_aot_factory_' + descriptor.id.replace('.','_'))
                    factory = module
                    for part in locator.export.split('.'):
                        factory = getattr(factory,part)
                from vibeflow.core.descriptors.json_values import freeze_mapping
                context = freeze_mapping({'config':record['config'],
                    'workflow_id':str(self.path / self.data['config_path']),
                    'config_path':str(self.path / self.data['config_path'])}, field_name='plugin.context')
                created.append(create_lifecycle_plugin(result,descriptor,factory,context,
                    source=descriptor.implementations[0].source.ref,
                    class_name=descriptor.implementations[0].source.export or '',
                    config_keys=tuple(record['config']),rulesets=descriptor.rulesets))
        except BaseException as error:
            from vibeflow.targets.python.project.plugins import dispose_instances
            dispose_instances(created, primary=error)
            raise
        return result

    def _blocks(self, plan, block_id):
        from vibeflow.targets.python.runtime.block_compiler import PythonCompiledBlock
        return tuple(PythonCompiledBlock(name=item['name'], entry=plan.order[0] if item['kind'] == 'graph' else item['entry'],
            exits=tuple(n for n in item['exits'] if n in plan.frames),
            nodes=tuple(n for n in item['nodes'] if n in plan.frames),
            edge_routes={node:tuple(plan.frames[node].outgoing) if item['kind'] == 'graph' else () for node in item['nodes'] if node in plan.frames},
            callable=getattr(self.generated, item['function']), source=item['source'], path=tuple(item['path']),
            supports_full_trace=True, supports_node_hooks=True, kind=item['kind'])
            for item in self.data['blocks'].get(block_id, ()) if item['kind'] == 'graph' or item['entry'] in plan.frames)

    def create_runtime(self, *, runtime_options=None, capabilities=None, run_dir=None,
                       node_config_overrides=None, global_config=None, delegate_cli=False, entry=None):
        from vibeflow.targets.python.runtime.engine import PipelineRuntime
        effective = self.effective_options(runtime_options)
        from vibeflow.targets.python.sdk.loading import _discard_foreign_project_modules
        _discard_foreign_project_modules(self.roots)
        registry = self._registry()
        prepared = self.prepared
        if node_config_overrides or global_config is not None:
            prepared = self._bind_config(prepared, registry, node_config_overrides, global_config)
        def bind(instances, plugins=None):
            return bind_python_workflow(prepared, registry=registry, runtime_options=effective,
                plugin_registry=plugins, instantiate=instances, block_loader=self._blocks,
                entry=entry,
                source_hash_for_path=lambda path:self.metadata['files'][path.relative_to(self.path).as_posix()])
        with source_paths(self.roots):
            plan = bind(False)
            runtime = PipelineRuntime(plan.graph, registry=registry,
                run_dir=run_dir, runtime_options=effective, capabilities=capabilities,
                delegate_cli=delegate_cli, _execution_plan=plan)
        from vibeflow.tooling.application.python.execution import (_checked_runtime_binding)
        runtime._runtime_plan_factory = lambda plugins: _checked_runtime_binding(
            lambda: bind(True, plugins), health=self.health, run_dir=runtime._run_dir)
        from vibeflow.tooling.application.python.project.lifecycle import checked_runtime_plugins
        runtime._runtime_plugin_factory = lambda: checked_runtime_plugins(
            self._plugins, config_path=self.path / self.data['config_path'],
            effective_policy=self.data['health']['effective_policy'], run_dir=runtime._run_dir)
        runtime._bundle_source_roots = self.roots
        return runtime

    def _bind_config(self, prepared, registry, overrides, global_config):
        from vibeflow.core.graph_calls import graph_call_subjects
        from vibeflow.core.config.concurrency import business_config, dispatch_limit
        from vibeflow.core.config.scope import ConfigScope, normalize_config_scope, scoped_node_params
        from vibeflow.block_compiler.compiler import _block_id
        from vibeflow.block_compiler.model import freeze_json_object
        root = prepared.graphs[prepared.workflow.entry_block]
        blocks = {block.id:block for block in prepared.workflow.blocks}
        globals_by_block = dict(prepared.globals)
        overrides_by_block = dict(prepared.overrides)
        for subject in graph_call_subjects(root, global_config=global_config if global_config is not None else ConfigScope(values=prepared.globals[prepared.workflow.entry_block]), node_config_overrides=overrides):
            key = _block_id(subject.call_path)
            if subject.declaration_only or key not in blocks:
                continue
            block = blocks[key]
            scope = normalize_config_scope(subject.global_config)
            globals_by_block[key] = scope.values
            overrides_by_block[key] = subject.overrides
            specs = {node.id:node for node in subject.graph.nodes}
            calls = []
            for call in block.nodes:
                spec = specs[call.id]
                if (call.is_loop or call.is_nodeset) and call.status != 'planned':
                    config = {**spec.params, **subject.overrides.get(call.id, {})}
                    calls.append(replace(call, max_concurrency=dispatch_limit(config)))
                    continue
                if call.status == 'planned':
                    params = {**spec.params, **subject.overrides.get(call.id, {})}
                else:
                    config = registry.get_config_spec(call.type_used)
                    params = scoped_node_params(spec.params,scope,declared_keys=set(config.schema))
                    params = registry.merge_config(call.type_used,{**params,**subject.overrides.get(call.id,{})})
                calls.append(replace(call, params=freeze_json_object(business_config(params)),
                    max_concurrency=dispatch_limit(params)))
            blocks[key] = replace(block,nodes=tuple(calls))
        return replace(prepared,workflow=replace(prepared.workflow,blocks=tuple(blocks.values())),globals=globals_by_block,overrides=overrides_by_block)

    def effective_options(self, overrides=None):
        from vibeflow.targets.python.runtime.options import merge_runtime_options
        return merge_runtime_options(self.data['runtime_options'], overrides)

    def run(self, initial=None, *, runtime_options=None, capabilities=None, run_root=None, run_id=None,
            delegate_cli=False, node_config_overrides=None, global_config=None, _prepared_run_dir=None, entry=None, signal=None):
        from vibeflow.tooling.application.python.run_directory import prepare_run_dir as _prepare_run_dir
        from vibeflow.tooling.application.python.execution import (CheckedRunResult, _new_run_id, _write_json, _summarize_run_result, _ensure_trace_files)
        from vibeflow.targets.python.runtime.observation import observe_run
        actual_id = _new_run_id() if run_id is None else run_id
        directory = _prepared_run_dir or _prepare_run_dir(run_root, actual_id)
        effective = self.effective_options(runtime_options)
        with observe_run(directory, effective):
            from vibeflow.core.workflows.entries import choose_entry
            selected = choose_entry({item.name:item for item in self.workflow.named_entries}, self.workflow.default_entry, entry)
            delegate_health = self.data['delegate_health_by_entry'][selected] if selected is not None else self.data['delegate_health']
            health = self._health(delegate_health if delegate_cli else self.data['health'])
            _write_json(directory / 'health_report.json', health.to_dict())
            _write_json(directory / 'effective_policy.json', health.effective_policy)
            if health.status in {'FAIL','ERROR'}:
                from vibeflow.tooling.application.python.execution import (CheckedRunError)
                raise CheckedRunError('bundle run refused: invalid delegated CLI contract', CheckedRunResult(actual_id,directory,health))
            from vibeflow.targets.python.runtime.summaries import summarize_mapping
            _write_json(directory / 'input_summary.json', summarize_mapping(dict(initial or {})))
            runtime = self.create_runtime(runtime_options=effective, capabilities=capabilities,
                run_dir=directory, delegate_cli=delegate_cli,
                node_config_overrides=node_config_overrides, global_config=global_config, entry=entry)
            unsubscribe = signal.subscribe(runtime.request_stop) if signal is not None else lambda: None
            try:
                context = runtime.run(initial)
            finally:
                unsubscribe()
                _ensure_trace_files(directory)
            _write_json(directory / 'output_summary.json', _summarize_run_result(context))
            from .execution import checked_result
            return checked_result(actual_id,directory,health,context,runtime.graph)

    @property
    def health(self):
        return self._health(self.data['health'])

    @staticmethod
    def _health(value):
        from vibeflow.core.findings import HealthReport, HealthFinding
        return HealthReport(**{**value,**{key:tuple(HealthFinding(**item) for item in value[key])
            for key in ('errors','warnings','skipped')}})

    def _path(self, value):
        return str(self.path / value[len('@bundle/'):]) if value.startswith('@bundle/') else value

    def _descriptor(self, value):
        from copy import deepcopy
        value = deepcopy(value)
        for implementation in value.get('implementations',()):
            for source in (implementation['source'],*implementation.get('implementation_files',())):
                if source['kind'] == 'file':
                    source['ref'] = self._path(source['ref'])
        return decode_resource(value)


def load_bundle(path):
    return PythonBundle(path)
