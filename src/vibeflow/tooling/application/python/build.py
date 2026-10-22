"""Build a relocatable Python package from the checked common workflow plan."""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import platform
import shutil

from vibeflow.core.findings import HealthReport
from vibeflow.targets.shared.aot import BuildResult, artifact_manifest, staged_build, write_manifest
from vibeflow.targets.python.runtime.preparation import prepare_python_workflow, bind_python_workflow
from vibeflow.targets.python.runtime.support.snapshot import encode_snapshot


@dataclass(frozen=True)
class PythonBuildResult(BuildResult):
    health: HealthReport


@dataclass(frozen=True)
class PythonBuildRequest:
    workspace: object
    config: str | Path
    out_dir: str | Path
    include: tuple[str, ...] = ()
    replace: bool = False
    runtime_options: object | None = None
    preview_root: str | Path | None = None


def build_python_aot(request: PythonBuildRequest) -> PythonBuildResult:
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    from vibeflow.tooling.application.python.workspace_service import (
        _environment_or_report, _prepare_workspace_graph, _validate_prepared_workspace_graph)
    from vibeflow.tooling.application.python.project.project_options import _workspace_runtime_options
    from vibeflow.tooling.application.python.presentation.prepared import final_python_compilation
    from vibeflow.targets.python.project.check_session import python_check_scope
    from vibeflow.core.descriptors.json_values import thaw_json

    workspace = request.workspace if hasattr(request.workspace,'roots') else load_workspace_config(request.workspace)
    config = Path(request.config).resolve()
    from vibeflow.tooling.project.preparation import ProjectPreparation
    preparation = ProjectPreparation(workspace, root=workspace.root_for_path(config),
        workflow=config, includes=request.include)
    environment = _environment_or_report(workspace,config,preparation=preparation)
    if isinstance(environment,HealthReport):
        raise ValueError(json.dumps(environment.to_dict(),ensure_ascii=False))
    with python_check_scope(environment.registry):
        checked = _prepare_workspace_graph(config,workspace=workspace,env=environment)
        if isinstance(checked,HealthReport):
            raise ValueError(json.dumps(checked.to_dict(),ensure_ascii=False))
        options = _workspace_runtime_options(config,workspace=workspace,overrides=request.runtime_options)
        health = _validate_prepared_workspace_graph(checked,env=environment,workspace=workspace,
            runtime_options=options,rule_phase='run')
        if health.status in {'FAIL','ERROR'}:
            raise ValueError(json.dumps(health.to_dict(),ensure_ascii=False))
        compilation = final_python_compilation(checked.graph,environment.registry)
        prepared = prepare_python_workflow(compilation.workflow.graph,compilation.compiled_graph,
            registry=environment.registry,global_config=checked.resources.global_config)
        from vibeflow.targets.python.runtime.helpers import planned_items
        planned = planned_items(compilation.workflow.graph)
        if planned and not (options.allow_planned_stub and all(item.get('behavior') == 'python_stub' for item in planned)):
            raise ValueError('GRAPH.PLANNED.NODE_IN_RUN: planned nodes cannot run; implement them or enable allow_planned_stub for python_stub')
        native_plan = bind_python_workflow(prepared,registry=environment.registry,runtime_options=options,instantiate=False,select_entry=False)
        framework = Path(__file__).resolve().parents[3]
        owner = workspace.root_for_path(config)
        # Preserve the project tree: root-local and project-qualified imports
        # must refer to the same files after relocation.
        destinations = {owner.path.resolve(): str(Path('shared') / owner.path.resolve().relative_to(workspace.root.resolve())),
                        workspace.root.resolve(): 'shared'}
        used = {call.definition_id for block in prepared.workflow.blocks for call in block.nodes
            if not(call.is_nodeset or call.is_loop or call.status == 'planned')}
        from vibeflow.tooling.application.python.build_inputs import python_build_inputs
        inputs = python_build_inputs(environment.registry, used, checked.resources.resource_use, native_plan)
        from vibeflow.tooling.application.python.build_dependencies import implementation_packages, copy_implementation_packages
        dependency_roots, dependency_resources = implementation_packages(inputs,
            roots=tuple(destinations), framework=framework)
        mappings = sorted(list(destinations.items())
            + list(dependency_roots) + [(framework,'_framework/vibeflow')],key=lambda item:len(str(item[0])),reverse=True)

        def relative(path):
            path = Path(path).resolve()
            for source,destination in mappings:
                if path.is_relative_to(source):
                    return str(Path(destination) / path.relative_to(source))
            raise ValueError(f'AOT implementation is outside the declared roots: {path}')

        def relocate(value):
            return '@bundle/' + relative(value) if value else value

        def descriptor_value(descriptor):
            value = descriptor.to_dict()
            for implementation in value.get('implementations',()):
                for source in (implementation.get('source',{}),*implementation.get('implementation_files',())):
                    if source.get('kind') == 'file' and Path(source['ref']).is_absolute():
                        source['ref'] = '@bundle/' + relative(source['ref'])
            return value

        from vibeflow.block_compiler import map_plan_sources
        prepared = replace(prepared,workflow=map_plan_sources(prepared.workflow,
            lambda source:replace(source,ref=relocate(source.ref)) if source.kind not in {'native','catalog'} and Path(source.ref).is_absolute() else source))

        records = {record['id']:record for record in environment.registry.prepared_resources.records}
        def plugin_reference(plugin_id):
            record = records[plugin_id]
            source = thaw_json(record['source'])
            if source['kind'] == 'file' and Path(source['ref']).is_absolute():
                source['ref'] = '@bundle/' + relative(source['ref'])
            base = workspace.root if record.get('scope') == 'project' else workspace.root_by_id(record['root']).path
            return {'source':source,'root':destinations[base.resolve()]}

        registry = environment.registry
        nodes = []
        for key in sorted(used):
            descriptor = registry.descriptor(key)
            path, symbol, _, load_root = registry.source_locations[key]
            implementation = registry.direct_bindings.get(("node", key))
            # Plugin exports retain the namespace that loaded the class, which
            # need not be the plugin owner's source-analysis directory.
            load_root = next((root for root, namespace in registry.source_namespaces.items()
                if getattr(implementation, '__module__', '').startswith(namespace.name + '.')), load_root)
            binding = {'path':relative(path),'export':symbol,'load_root':relative(load_root)}
            info = registry.source_info(key)
            nodes.append({'descriptor':descriptor_value(descriptor),'binding':binding,
                'source':relocate(info.path),'source_line':info.line})
        plugins = []
        for selection in registry.prepared_resources.lifecycle_selections:
            if selection.get('status') == 'planned':
                continue
            descriptor = registry.prepared_resources.catalogs.plugins.require(selection['id'])
            if not checked.resources.resource_use.allows('plugin', descriptor.id):
                continue
            if descriptor.plugin_type != 'runtime':
                continue
            origin = registry.prepared_resources.catalogs.origins[('plugins',descriptor.id)]
            item = {'descriptor':descriptor_value(descriptor),'plugin':plugin_reference(origin.owner.plugin_id),
                'config':thaw_json(selection['config'])}
            if ('plugin',descriptor.id) not in registry.direct_bindings:
                from vibeflow.tooling.application.python.project.declarations import _implementation_path
                owner = registry.resource_roots[('plugins',descriptor.id)]
                source = descriptor.implementations[0].source
                item['factory_path'] = relative(_implementation_path(source.kind,source.ref,owner.path,registry.source_roots))
            plugins.append(item)

        blocks, source_functions = {}, []
        def save_blocks(plan,block_id):
            records = []
            for block in plan.blocks:
                function = 'block_' + str(len(source_functions))
                original = {'graph':'compiled_block','loop':'compiled_loop_block','nodeset':'compiled_nodeset_block'}[block.kind]
                source_functions.append(block.source.replace('def ' + original + '(', 'def ' + function + '(',1))
                records.append(dict(name=block.name,entry=block.entry,exits=block.exits,nodes=block.nodes,kind=block.kind,function=function,path=block.path,source=block.source))
            blocks[block_id] = records
            common = prepared.workflow.block(block_id)
            for call in common.nodes:
                frame = plan.frames[call.id]
                if call.child_block:
                    save_blocks(frame.subplan,call.child_block)
        save_blocks(native_plan,prepared.workflow.entry_block)
        from vibeflow.tooling.application.python.delegate_contract import validate_delegate_cli_graph_contract
        delegate_health = validate_delegate_cli_graph_contract(compilation.workflow.graph, health)
        from vibeflow.core.workflows.entries import project_entry
        delegate_entries = {name: validate_delegate_cli_graph_contract(
            project_entry(compilation.workflow.graph, compilation.compiled_graph, name)[0], health).to_dict()
            for name in compilation.workflow.graph.entries}
        data = dict(workflow_reference={"root":workspace.root_for_path(config).id, "path":config.relative_to(workspace.root_for_path(config).path).as_posix()}, resource_use=checked.resources.resource_use.to_dict(), delegate_health=delegate_health.to_dict(), delegate_health_by_entry=delegate_entries,
            workflow=prepared.workflow.to_dict(),graphs=encode_snapshot(prepared.graphs,relocate=relocate),
            compiled=encode_snapshot(prepared.compiled),globals=encode_snapshot(prepared.globals),overrides=encode_snapshot(prepared.overrides),
            source_roots=list(dict.fromkeys([*destinations.values(),*(destination for _,destination in dependency_roots)])),
            source_import_roots={relative(root):[relative(path) for path in namespace.roots]
                                 for root,namespace in registry.source_namespaces.items()},
            nodes=nodes,plugins=plugins,blocks=blocks,
            config_path=relative(config),runtime_options=asdict(options),health=health.to_dict())
        from vibeflow.tooling.application.python.build_files import python_bundle_files, copy_python_framework
        files = python_bundle_files(workspace, environment.registry, config, inputs,
            out_dir=Path(request.out_dir).resolve(), include=request.include)
        files = tuple(sorted({*files,*(Path(graph.source_path) for graph in prepared.graphs.values() if graph.source_path)}))
        from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
        from vibeflow.tooling.presentation.preview.diagnostics import incidental_preview, preview_operation
        from vibeflow.tooling.application.python.presentation.preview import python_preview
        def publish_build_preview():
            presentation = prepare_python_presentation(compilation.workflow.graph, registry=environment.registry,
                resources=checked.resources, compilation=compilation)
            return python_preview(presentation, config=config, workspace=workspace,
                preview_root=request.preview_root, category="build", status="building", check_status=health.status)
        preview_record = incidental_preview(publish_build_preview)
        with preview_operation(preview_record), staged_build(request.out_dir,replace=request.replace) as staging:
            copy_python_framework(staging/'_framework/vibeflow')
            from vibeflow.tooling.project.workflow_launches import graph_launches, write_bundle_launches
            write_bundle_launches(staging, graph_launches(compilation.workflow.graph, registry.prepared_resources.catalogs,
                root=workspace.root_for_path(config), global_config=checked.resources.global_config), base=relative(workspace.root_for_path(config).path), workflow=data["workflow_reference"])
            copy_implementation_packages(dependency_resources,staging)
            for source in files:
                target = staging / relative(source)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
            (staging/'python-workflow.json').write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n',encoding='utf-8')
            imports = 'from vibeflow.targets.python.runtime.block_compiler import CompiledBlockResult\n'
            (staging/'generated_blocks.py').write_text(imports+'\n\n'.join(source_functions)+'\n',encoding='utf-8')
            (staging/'run.py').write_text("from pathlib import Path\nimport sys\nsys.dont_write_bytecode = True\nROOT = Path(__file__).resolve().parent\nsys.path.insert(0, str(ROOT / '_framework'))\nfrom vibeflow.tooling.application.python.bundle_cli import main\nif __name__ == '__main__':\n    raise SystemExit(main(ROOT))\n",encoding='utf-8')
            manifest = artifact_manifest(staging,workflow=prepared.workflow,project_target='python',entry='run.py',
                plan_sha256=hashlib.sha256(prepared.workflow.to_json().encode()).hexdigest(),
                target_metadata=dict(target='python',profile='python-package',toolchain={'python':platform.python_version()},bindings='python-workflow.json'))
            write_manifest(staging,manifest)
        output = Path(request.out_dir).resolve()
        return PythonBuildResult(output,output/'run.py',output/'vibeflow-build.json',{'python':platform.python_version()},
            tuple([*manifest['files'],'vibeflow-build.json']), health)
