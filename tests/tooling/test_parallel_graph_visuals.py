"""Ordinary graph branches and collectors remain explicit in both renderers."""
from types import SimpleNamespace
from tests.tooling.test_presentation_cascade import Empty
from vibeflow.core.descriptors import DescriptorCatalogs,NodeDescriptor,NodeContractDescriptor
from vibeflow.targets.python.project import GraphCompiler,NodeRegistry
from vibeflow.tooling.application.javascript.audit import _javascript_graph_document
from vibeflow.tooling.application.javascript.review import render_mermaid
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.project.graph_config import parse_graph_config


def test_parallel_graph_has_normal_explicit_completion_edges():
    registry=NodeRegistry();catalogs=DescriptorCatalogs.empty()
    for key,kind in (("boundary","terminal"),("work","process")):
        descriptor=NodeDescriptor("fixture."+key,key,key,"1",kind,contract=NodeContractDescriptor(),rulesets=())
        registry.register(descriptor,Empty);catalogs.nodes.register(descriptor)
    graph=parse_graph_config({"pipeline":{"nodes":[{"id":name,"type_used":"fixture."+kind,"display_name":name,
        "description":"普通图节点",**({"join_policy":"all"} if name=="collect" else {})}
        for name,kind in (("start","boundary"),("left","work"),("right","work"),("collect","work"),("end","boundary"))],
        "edges":[["start","left"],["start","right"],["left","collect"],["right","collect"],["collect","end"]]}})
    compiled=GraphCompiler().compile(graph,registry=registry)
    architecture={"workflow":_javascript_graph_document(graph,compiled,source={},graph_lock_scope="graph",catalogs=catalogs,health_classes={})}
    texts=[export_mermaid(graph,compiled=compiled,registry=registry),render_mermaid(SimpleNamespace(graph=graph,compiled=compiled,catalogs=catalogs,architecture=architecture))]
    for text in texts:
        assert all(name in text for name in ("left","right","collect","end"))
        assert text.count("-->")==5
        assert "tasks/work" not in text and "启动" not in text
