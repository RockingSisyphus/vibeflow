from __future__ import annotations
from vibeflow.tooling.presentation.mermaid.style import mermaid_style, mermaid_shape
from types import SimpleNamespace
import pytest
from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig, NodeCallSpec, NodesetTypeSpec, LoopSpec
from vibeflow.tooling.application.javascript.presentation import diagrams as review
from vibeflow.tooling.presentation.mermaid.types import SvgFragment

def _compiled(graph):
    return CompiledGraph(order=tuple((n.id for n in graph.nodes)), explicit_edges=(), data_edges=(), effective_edges=(), providers={}, consumers={}, flow_kinds={n.id: 'predefined' if n.definition_id in graph.nodeset_types or n.definition_id.startswith('vibeflow.loop') else 'process' for n in graph.nodes})

def _result(*, outer_expand=True, inner_expand=True, loop=False):
    leaf = GraphConfig(nodes=(NodeCallSpec('leaf_work', 'demo.work'),))
    inner = NodesetTypeSpec('demo.inner', 'Inner', 'Inner detail', (), (), leaf, expand=inner_expand)
    body = GraphConfig(nodes=(NodeCallSpec('inner_call', 'demo.inner'),), nodeset_types={inner.type_key: inner})
    outer = NodesetTypeSpec('demo.outer', 'Outer', 'Outer detail', (), (), body, expand=outer_expand)
    top = NodeCallSpec('outer_call', 'vibeflow.loop.while', loop=LoopSpec(body='demo.outer', max_iterations=1, stop_after=1)) if loop else NodeCallSpec('outer_call', 'demo.outer')
    graph = GraphConfig(nodes=(top,), nodeset_types={outer.type_key: outer, inner.type_key: inner})
    descriptor = SimpleNamespace(rulesets=(), display_name='Work', description='Work', external=False, presentation={})
    internal = {'resources': {'node:demo.work': {'node_type': 'vibeflow.node', 'kind': 'node', 'id': 'demo.work'}}, 'files': {'private_kernel.py': {'path': 'private_kernel.py'}}, 'relations': [], 'rule_graph': {'rules': {'private.health': {}}, 'rulesets': {'private.default': {}}}}
    resources = {'base_lib': {'demo.math': {'id': 'demo.math', 'display_name': 'Math', 'presentation': {'shape': 'fr-rect', 'fill': '#c8e4ff'}}}, 'capabilities': {'demo.session': {'id': 'demo.session'}}}
    selected_plugins = ({'id': 'demo', 'status': 'implemented', 'declaration': {'display_name': 'Selected package', 'presentation': {'shape': 'hex', 'fill': '#e8d4ff'}}, 'source': {'ref': 'plugin.ts'}},)
    return SimpleNamespace(graph=graph, compiled=_compiled(graph), compiled_nodeset_types={'demo.outer': _compiled(body), 'demo.inner': _compiled(leaf)}, catalogs=SimpleNamespace(nodes={'demo.work': descriptor}, plugin_records=selected_plugins), architecture={'resources': resources, 'implementation_graph': internal}, plugin_records=({'id': 'demo.runtime'},), root=SimpleNamespace(id='demo'), plan=SimpleNamespace(workflow_id='demo'))

@pytest.mark.parametrize('loop', [False, True])
@pytest.mark.parametrize('outer,inner,visible', [(True, True, ['demo.outer', 'demo.inner']), (False, True, []), (True, False, ['demo.outer'])])
def test_hidden_nodeset_stops_all_javascript_display_traversal(tmp_path, monkeypatch, loop, outer, inner, visible):
    result = _result(outer_expand=outer, inner_expand=inner, loop=loop)
    rendered = []

    def fragment(title, mermaid, directory, **options):
        rendered.append((title, mermaid, options))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60, review_kind=options['kind'], review_owner=options['owner'], review_target=options['target'])
    monkeypatch.setattr(review, '_render_fragment', fragment)
    text = review.render_mermaid(result, expand_nodesets=True)
    ascii_text = review.render_ascii(result, expand_nodesets=True)
    coverage = review.write_review_svg(result, tmp_path / 'review.svg', expand_nodesets=True, mermaid_layout='review-columns')
    assert coverage == review.expected_review_coverage(result)
    assert 'outer_call' in text and 'outer_call' in ascii_text
    assert [group.target for group in review._expanded_groups(result.graph)] == visible
    assert ('leaf_work' in text) == ('demo.inner' in visible)
    assert ('leaf_work' in ascii_text) == ('demo.inner' in visible)
    assert any(('leaf_work' in mermaid for _, mermaid, _ in rendered)) == ('demo.inner' in visible)
    assert any(('inner_call' in mermaid for _, mermaid, _ in rendered)) == ('demo.outer' in visible)
    if outer and (not inner):
        assert next((mermaid for _, mermaid, _ in rendered if 'inner_call' in mermaid)).startswith('flowchart TD')
        assert text.split('%% expanded', 1)[1].splitlines()[1] == 'flowchart TD'
    assert set(result.graph.nodeset_types) == {'demo.outer', 'demo.inner'}
    assert set(result.compiled_nodeset_types) == {'demo.outer', 'demo.inner'}

def test_javascript_workflow_resources_are_small_directories(tmp_path, monkeypatch):
    result = _result()
    rendered = []

    def fragment(title, mermaid, directory, **options):
        rendered.append((title, mermaid))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60, review_kind=options['kind'], review_owner=options['owner'], review_target=options['target'])
    monkeypatch.setattr(review, '_render_fragment', fragment)
    coverage = review.write_review_svg(result, tmp_path / 'review.svg', expand_nodesets=True, mermaid_layout='review-columns')
    assert coverage == review.expected_review_coverage(result)
    assert [title for title, _ in rendered[:4]] == ['main pipeline', 'plugins', 'base_lib', 'capabilities']
    for title, text in rendered[1:4]:
        assert text.startswith('flowchart LR')
        assert text.count(' -.-> ') == 1
        assert f'label: "{title}"' in text
    assert 'vf_resource_' not in rendered[0][1]
    resources = '\n'.join((text for _, text in rendered[1:4]))
    assert 'Selected package' in resources and 'demo.math' in resources
    assert 'demo.runtime' not in resources
    assert 'shape: fr-rect' in resources and 'fill:#c8e4ff' in resources
    assert 'fill:#e8d4ff' in resources
    assert all((value not in resources for value in ('Node types', 'private_kernel.py', 'private.health', 'reference', 'plugin.ts', 'rule:')))
    default = review.render_mermaid(result)
    detailed = review.render_mermaid(result, mermaid_layout='review-columns')
    assert 'vf_resource_' not in default
    assert '%% resources: plugins' in detailed
    assert all((value not in detailed for value in ('Node types', 'private_kernel.py', 'private.health', 'reference', 'plugin.ts')))

def test_javascript_diagram_does_not_offer_internal_rule_catalog_switch():
    import inspect
    assert all(('show_rules' not in inspect.signature(function).parameters for function in (review.render_mermaid, review.write_review_svg, review.expected_review_coverage, review.render_review_svg)))

def test_javascript_empty_resources_do_not_create_catalog_panels():
    result = _result()
    result.architecture['resources'] = {}
    result.catalogs.plugin_records = ()
    result.plugin_records = ()
    assert review._resource_fragments(result) == ()
    assert '%% resources:' not in review.render_mermaid(result, mermaid_layout='review-columns')

def test_javascript_planned_selection_remains_one_directory_entry():
    result = _result()
    result.catalogs.plugin_records = ({'id': 'future.plugin', 'status': 'planned', 'source': {'ref': 'never-loaded.ts'}},)
    fragment = review._resource_fragments(result)[0]
    assert 'future.plugin' in fragment['mermaid'] and 'status: planned' in fragment['mermaid']
    assert 'never-loaded.ts' not in fragment['mermaid']
    assert fragment['mermaid'].count(' -.-> ') == 1

def test_javascript_selected_resource_health_and_call_style_remain_visible():
    result = _result()
    lifecycle = SimpleNamespace(id='demo.runtime', to_dict=lambda: {'id': 'demo.runtime'})
    result.catalogs.plugins = (lifecycle,)
    result.catalogs.origins = {('plugins', 'demo.runtime'): SimpleNamespace(owner=SimpleNamespace(plugin_id='demo'))}
    result.rule_report = SimpleNamespace(findings=({'object_type': 'plugin', 'object_id': 'demo.runtime', 'severity': 'warning'}, {'object_type': 'base_lib', 'object_id': 'demo.math', 'severity': 'warning'}))
    result.document = SimpleNamespace(data={'base_lib': {'modules': [{'id': 'demo.math', 'style': {'fill': '#ffeebb'}}]}})
    fragments = {item['id']: item['mermaid'] for item in review._resource_fragments(result)}
    assert 'fill:#fef3c7' in fragments['plugins']
    assert 'demo.runtime' not in fragments['plugins']
    assert 'fill:#ffeebb' in fragments['base_lib']
    assert 'shape: fr-rect' in fragments['base_lib']

def test_javascript_call_health_uses_rule_associations_not_shared_source_files():
    from vibeflow.tooling.application.javascript.presentation.status import node_health_classes
    graph = GraphConfig(nodes=(NodeCallSpec('first', 'demo.work'), NodeCallSpec('second', 'demo.work'), NodeCallSpec('neighbor', 'demo.other')))
    source = {'object_type': 'node', 'object_id': 'demo.work', 'severity': 'warning', 'source_location': {'path': 'same.ts', 'line': 1}, 'details': {'definition_id': 'demo.work', 'call_paths': [['first'], ['second']]}}
    call = {**source, 'severity': 'error', 'details': {'definition_id': 'demo.work', 'call_paths': [['first']]}}
    unowned = {'object_type': 'file', 'object_id': 'same.ts', 'severity': 'error', 'source_location': source['source_location']}
    statuses = node_health_classes(graph, (source, call, unowned))
    assert statuses == {(id(graph), 'first'): 'healthError', (id(graph), 'second'): 'healthWarning'}

def test_javascript_call_health_distinguishes_repeated_node_ids_in_nested_graphs():
    from vibeflow.tooling.application.javascript.presentation.status import node_health_classes
    child = GraphConfig(nodes=(NodeCallSpec('same', 'demo.work'),))
    definition = NodesetTypeSpec('demo.child', 'Child', 'A child', (), (), child)
    graph = GraphConfig(nodes=(NodeCallSpec('same', 'demo.work'), NodeCallSpec('parent', 'demo.child')), nodeset_types={definition.type_key: definition})
    finding = {'object_type': 'node', 'object_id': 'demo.work', 'severity': 'warning', 'details': {'definition_id': 'demo.work', 'call_paths': [['parent', 'same']]}}
    statuses = node_health_classes(graph, (finding,))
    assert statuses == {(id(child), 'same'): 'healthWarning'}
    workflow_finding = {'object_type': 'node', 'object_id': 'same', 'severity': 'warning', 'details': {'call_paths': [['parent']]}}
    assert node_health_classes(graph, (workflow_finding,)) == statuses

@pytest.mark.parametrize('status,override,expected,origin', [('implemented', '', '#fef3c7', 'status'), ('implemented', '#ffeebb', '#ffeebb', 'call'), ('planned', '', '#ECECFF', 'native')])
def test_javascript_actual_call_architecture_and_mermaid_share_health_style(status, override, expected, origin):
    from vibeflow.core.flow import NodeStyle
    from vibeflow.tooling.architecture.workflow import graph_document
    from vibeflow.tooling.application.javascript.presentation.status import node_health_classes
    result = _result()
    call = NodeCallSpec('call', 'demo.work', status=status, style=NodeStyle(fill=override))
    graph = GraphConfig(nodes=(call,))
    descriptor = result.catalogs.nodes['demo.work']
    descriptor.tags, descriptor.metadata = ((), {})
    result.graph, result.compiled = (graph, _compiled(graph))
    finding = {'object_type': 'node', 'object_id': 'demo.work', 'severity': 'warning', 'details': {'definition_id': 'demo.work', 'call_paths': [['call']]}}
    record = next(row for row in graph_document(graph, result.compiled, source={'path': 'workflow.jsonc'}, graph_lock_scope='root', descriptor=result.catalogs.nodes.get, health_classes=node_health_classes(graph, (finding,)))['nodes'] if row['id'] == call.id)
    result.architecture['workflow'] = {'nodes': [record]}
    assert record['presentation']['values']['fill'] == expected
    assert record['presentation']['sources']['fill'] == origin
    assert f'style vf_call fill:{expected}' in review.render_mermaid(result)

def test_javascript_resource_directory_defaults_use_the_shared_resource_presentation():
    from vibeflow.tooling.presentation.node_presentation import resolve_presentation
    for kind, resource_kind, native in (('base_lib', 'base_lib', 'baseLibResource'), ('plugins', 'plugin', 'pluginResource'), ('host_extensions', 'host_extension', 'hostExtensionResource')):
        presentation = resolve_presentation({'id': 'selected'}, resource_kind=resource_kind, native_class=native)
        text = review._resource_mermaid(kind, ({'id': 'selected'},))
        assert f'shape: {presentation.shape}' in text
        assert mermaid_style(presentation) in text
        assert text.count(' -.-> ') == 1


def test_rule_owned_diagnostic_uses_definition_identity_for_call_style():
    from vibeflow.core import GraphConfig, NodeCallSpec
    from vibeflow.tooling.application.javascript.presentation.status import node_health_classes
    graph = GraphConfig(nodes=(NodeCallSpec("work", "business.node"),))
    finding = {"object_type":"rule", "object_id":"custom.check", "severity":"error",
               "details":{"definition_id":"business.node", "call_paths":[["work"]]}}
    assert node_health_classes(graph, (finding,)) == {(id(graph), "work"): "healthError"}
