"""Present a successful build using the facts retained by its actual preparation."""

from vibeflow.core.flow import LOOP_NODE_TYPES
from vibeflow.tooling.presentation.preview.exporter import publish_preview, workflow_identity, workflow_links
from vibeflow.tooling.presentation.viewer import install_for_record


def publish_build_preview(prepared, *, preview_root=None, status="building"):
    from .architecture_facts import build_architecture_facts
    from vibeflow.tooling.presentation.resource_architecture import resource_architecture
    from vibeflow.tooling.presentation.portable_paths import portable_paths

    inputs = prepared.presentation_inputs
    compiled_nodesets = dict(inputs["declarations"])

    def remember(graph, path=()):
        for node in graph.nodes:
            target = node.loop.body if node.type_used in LOOP_NODE_TYPES else node.type_used
            definition = graph.nodesets.get(target)
            call = path + (node.id,)
            if definition is not None and call in inputs["compiled_by_path"]:
                compiled_nodesets.setdefault(target, inputs["compiled_by_path"][call])
                remember(definition.graph, call)

    remember(prepared.graph)
    architecture = build_architecture_facts(prepared.graph, compiled=prepared.compiled,
        compiled_nodesets=compiled_nodesets, catalogs=prepared.catalogs,
        used_node_types=frozenset(prepared.used_node_types), active_base_lib_ids=frozenset(prepared.used_base_libs),
        plugin_records=prepared.declared_plugins, host_records=prepared.declared_host_extensions,
        root_id=prepared.root.id, source_path=prepared.config_path.relative_to(prepared.root.path).as_posix(),
        findings=prepared.rule_report.findings)
    architecture["implementation_graph"] = resource_architecture(prepared.catalogs,
        project_root=prepared.root.path, selections=inputs["selections"], selected_nodes=prepared.used_node_types,
        source_facts=tuple(item for scope in prepared.rule_report.source_scopes.values() for item in scope["sources"]),
        findings=prepared.rule_report.findings, roots={root.id: root.path for root in prepared.workspace.roots})
    architecture = portable_paths(architecture, roots={r.id:r.path for r in prepared.workspace.roots}, primary_root=prepared.root.path)
    root=preview_root or prepared.workspace.root
    record=publish_preview(root=root,workflow=workflow_identity(prepared.config_path,prepared.workspace,target="javascript"),
        category="build",status=status,architecture=architecture,links=workflow_links(prepared.workspace),
        check_status="CONCERNS" if prepared.warnings else "PASS")
    install_for_record(record)
    return record
