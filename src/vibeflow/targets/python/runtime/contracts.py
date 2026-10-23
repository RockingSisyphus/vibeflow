"""Python completion facts shared by source checks and Runtime binding."""
from vibeflow.core.workflows.coordination import synchronous_violation
from vibeflow.core.workflows.interfaces import workflow_capability_descriptor, port_capability_descriptor


def capability_descriptors(registry):
    prepared = getattr(registry, 'prepared_resources', None)
    declared = (prepared.catalogs.capabilities.descriptors() if prepared is not None
                else getattr(registry, 'capability_descriptors', ()))
    return (*declared, workflow_capability_descriptor(), port_capability_descriptor({'send', 'receive'}))


def graph_sync_findings(graph, registry, *, source_context=None):
    if graph.entry_mode != 'sync':
        return ()
    from vibeflow.core.graph_calls import graph_call_subjects
    from vibeflow.core.findings import HealthFinding
    findings = []
    for subject in graph_call_subjects(graph):
        for node in subject.graph.nodes:
            if node.status == 'planned' or node.definition_id not in registry.available():
                continue
            descriptor = registry.descriptor(node.definition_id)
            implementation = next((item for item in descriptor.implementations if item.language == 'python'), None)
            problem = synchronous_violation(implementation.completion if implementation else 'immediate',
                capabilities=descriptor.capabilities, descriptors=capability_descriptors(registry))
            if problem:
                path = '/'.join((*subject.call_path, node.id))
                info = registry.source_info(node.definition_id)
                location = {'path':info.path, 'line':info.line}
                if source_context is not None:
                    source = next((item for item in source_context.nodes if item.definition_id==node.definition_id), None)
                    symbol = source_context.symbol(source.path,source.symbol) if source else None
                    member = source_context.class_members(symbol).get('run_pure') if symbol else None
                    if member is not None:
                        location = {'path':member.path, 'line':member._node.lineno}
                findings.append(HealthFinding(rule_id='VF_ENTRY_MODE_SUSPEND_IN_SYNC', severity='error',
                    object_type='node', object_id=path, source_location=location,
                    message=f'{path}: {problem}; declare entry_mode async'))
    prepared = getattr(registry, 'prepared_resources', None)
    if prepared is not None:
        for selection in prepared.lifecycle_selections:
            if selection.get('status') == 'planned':
                continue
            descriptor = prepared.catalogs.plugins.require(selection['id'])
            if selection.get('status') == 'planned' or descriptor.plugin_type != 'runtime':
                continue
            if any(item.completion == 'suspend' for item in descriptor.implementations if item.language == 'python'):
                findings.append(HealthFinding(rule_id='VF_ENTRY_MODE_PLUGIN_SUSPEND_IN_SYNC',severity='error',
                    object_type='plugin',object_id=descriptor.id,message='sync workflow declares asynchronous runtime lifecycle'))
    return tuple(findings)
