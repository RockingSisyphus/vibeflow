"""Ordinary graph branches and collectors remain explicit in both renderers."""
from types import SimpleNamespace
from dataclasses import replace
import pytest
from tests.tooling.test_presentation_cascade import Empty
from vibeflow.core.descriptors import DescriptorCatalogs,NodeDescriptor,NodeContractDescriptor
from vibeflow.targets.python.project import GraphCompiler,NodeRegistry
from vibeflow.tooling.architecture.workflow import graph_document
from vibeflow.tooling.application.javascript.presentation.diagrams import render_mermaid
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.project.graph_config import parse_graph_config


def test_parallel_graph_has_normal_explicit_completion_edges():
    registry=NodeRegistry();catalogs=DescriptorCatalogs.empty()
    for key,kind in (("boundary","terminal"),("work","process")):
        descriptor=NodeDescriptor("fixture."+key,key,key,"1",kind,contract=NodeContractDescriptor(),rulesets=(), node_type="vibeflow.node")
        registry.register(descriptor,Empty);catalogs.nodes.register(descriptor)
    graph=parse_graph_config({"pipeline":{"nodes":[{"id":name,"definition_id":"fixture."+kind,"display_name":name,
        "description":"普通图节点",**({"join_policy":"all"} if name=="collect" else {})}
        for name,kind in (("start","boundary"),("left","work"),("right","work"),("collect","work"),("end","boundary"))],
        "edges":[["start","left"],["start","right"],["left","collect"],["right","collect"],["collect","end"]]}})
    compiled=GraphCompiler().compile(graph,registry=registry)
    architecture={"workflow":graph_document(graph,compiled,source={},graph_lock_scope="graph",descriptor=catalogs.nodes.get,health_classes={})}
    texts=[export_mermaid(graph,compiled=compiled,registry=registry),render_mermaid(SimpleNamespace(graph=graph,compiled=compiled,descriptor=catalogs.nodes.get,architecture=architecture))]
    for text in texts:
        assert all(name in text for name in ("left","right","collect","end"))
        assert text.count("-->")==5
        assert "tasks/work" not in text and "启动" not in text


def _parallel_fixture(*, descriptor_shape="", call_shape="", external=False):
    registry=NodeRegistry();catalogs=DescriptorCatalogs.empty()
    for key,kind in (("boundary","terminal"),("dispatch","process"),("work","process"),("collect","process")):
        descriptor=NodeDescriptor("fixture."+key,key,key,"1",kind,contract=NodeContractDescriptor(),rulesets=(),
            external=external and key in {"dispatch","collect"},
            presentation={"shape":descriptor_shape} if descriptor_shape and key in {"dispatch","collect"} else {}, node_type="vibeflow.node")
        registry.register(descriptor,Empty);catalogs.nodes.register(descriptor)
    graph=parse_graph_config({"pipeline":{"nodes":[{"id":name,"definition_id":"fixture."+kind,
        "display_name":name,"description":"Ordinary parallel call",
        **({"join_policy":"all"} if name=="collect" else {}),
        **({"style":{"shape":call_shape}} if call_shape and name in {"dispatch","collect"} else {})}
        for name,kind in (("start","boundary"),("dispatch","dispatch"),("left","work"),
            ("right","work"),("collect","collect"),("end","boundary"))],
        "edges":[["start","dispatch"],["dispatch","left"],["dispatch","right"],
            ["left","collect"],["right","collect"],["collect","end"]]}})
    return graph,registry,catalogs


def _presentations(graph,registry,catalogs):
    compiled=GraphCompiler().compile(graph,registry=registry)
    py=build_architecture_document(graph,compiled=compiled,registry=registry)["workflow"]
    js=graph_document(graph,compiled,source={},graph_lock_scope="graph",descriptor=catalogs.nodes.get)
    assert {n['id']:n['presentation'] for n in py['nodes']}=={n['id']:n['presentation'] for n in js['nodes']}
    texts=[export_mermaid(graph,compiled=compiled,registry=registry),
        render_mermaid(SimpleNamespace(graph=graph,compiled=compiled,descriptor=catalogs.nodes.get,architecture={"workflow":js}))]
    return {n['id']:n['presentation'] for n in py['nodes']},texts


def test_ordinary_dispatch_and_collector_keep_double_circle_defaults():
    facts,texts=_presentations(*_parallel_fixture())
    for name in ("dispatch","collect"):
        assert facts[name]['values']['shape']=='dbl-circ'
        assert facts[name]['sources']['shape']=='native'
    assert facts['start']['values']['shape']==facts['end']['values']['shape']=='stadium'
    assert facts['left']['values']['shape']==facts['right']['values']['shape']=='rect'
    for text in texts:
        assert text.count('shape: dbl-circ')==2
        assert text.count('-->')==6


def test_external_boundary_keeps_its_colours_without_losing_parallel_shape():
    from vibeflow.tooling.presentation.style import SYSTEM_STYLE_COLORS
    facts,_=_presentations(*_parallel_fixture(external=True))
    for name in ('dispatch','collect'):
        assert facts[name]['values']['shape']=='dbl-circ'
        assert facts[name]['values']['fill']==SYSTEM_STYLE_COLORS['externalDependency'].fill


@pytest.mark.parametrize('descriptor_shape,call_shape,expected,source',[
    ('hex','','hex','node'),('hex','rect','rect','call')])
def test_parallel_defaults_respect_normal_presentation_cascade(descriptor_shape,call_shape,expected,source):
    facts,texts=_presentations(*_parallel_fixture(descriptor_shape=descriptor_shape,call_shape=call_shape))
    for name in ('dispatch','collect'):
        assert facts[name]['values']['shape']==expected
        assert facts[name]['sources']['shape']==source
    assert all('shape: dbl-circ' not in text for text in texts)


def test_transfer_only_edge_and_safe_any_merge_do_not_get_parallel_defaults():
    graph,registry,catalogs=_parallel_fixture()
    graph=replace(graph,edges=tuple(replace(edge,schedule=False) if edge.pair==('dispatch','right') else edge
        for edge in graph.edges),nodes=tuple(replace(node,join_policy='safe_any') if node.id=='collect' else node
        for node in graph.nodes))
    facts,_=_presentations(graph,registry,catalogs)
    assert facts['dispatch']['values']['shape']==facts['collect']['values']['shape']=='rect'


def test_same_endpoints_keep_each_conditional_edges_own_roles():
    graph,registry,catalogs=_parallel_fixture()
    edge=graph.edges[0]
    graph=replace(graph,edges=(replace(edge,when="route == 'run'",schedule=True,transfer=False),
        replace(edge,when="route == 'data'",schedule=False,transfer=True),
        replace(edge,when="route == 'both'",schedule=True,transfer=True),*graph.edges[1:]))
    compiled=GraphCompiler().compile(graph,registry=registry)
    py=build_architecture_document(graph,compiled=compiled,registry=registry)['workflow']
    js=graph_document(graph,compiled,source={},graph_lock_scope='root',descriptor=catalogs.nodes.get)
    for body in (py,js):
        actual={item['when']:item['roles'] for item in body['edges'] if item['from']=='start' and item['to']=='dispatch'}
        assert actual=={"route == 'run'":['mainline','schedule'],"route == 'data'":['data_bypass','transfer'],
                        "route == 'both'":['mainline','schedule','transfer']}

    texts=[export_mermaid(graph,compiled=compiled,registry=registry),
        render_mermaid(SimpleNamespace(graph=graph,compiled=compiled,descriptor=catalogs.nodes.get,architecture={"workflow":js}))]
    for text in texts:
        assert "linkStyle 0 stroke-width:4px" in text
        assert "linkStyle 1 stroke-dasharray:6 4,stroke-width:2px" in text
        assert "linkStyle 2 stroke-width:4px" in text


@pytest.mark.parametrize('target',[0,1],ids=['python','javascript'])
def test_real_svg_draws_both_parallel_calls_as_double_circles(tmp_path,target):
    from xml.etree import ElementTree as E
    from vibeflow.tooling.presentation.mermaid import render_mermaid_svg
    _,texts=_presentations(*_parallel_fixture())
    svg=render_mermaid_svg(texts[target],tmp_path/'parallel.svg')
    root=E.parse(svg).getroot()
    ns={'s':'http://www.w3.org/2000/svg'}
    for name in ('dispatch','collect'):
        groups=[g for g in root.findall('.//s:g',ns) if 'node' in g.get('class','').split()
            and any(f'flowchart-{prefix}{name}-' in g.get('id','') for prefix in ('','vf_'))]
        assert len(groups)==1,(name,[g.get('id') for g in root.findall('.//s:g',ns)])
        assert len(groups[0].findall('.//s:circle',ns))==2,E.tostring(groups[0],encoding='unicode')
