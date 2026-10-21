"""A folded Nodeset is still compiled but its descendants are display-private."""

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import NodeRegistry
from vibeflow.tooling.application.python.presentation.ascii_flowchart import export_ascii_flowchart
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid, review_fragments, review_svg
from vibeflow.tooling.presentation.mermaid.types import SvgFragment
from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
from vibeflow.tooling.project.graph_config import parse_graph_config


@pytest.mark.parametrize("loop", [False, True])
@pytest.mark.parametrize("outer,inner,visible", [(True, True, ["inner_call", "leaf_work"]),
                                                 (False, True, []), (True, False, ["inner_call"])])
def test_python_display_stops_at_folded_definition(tmp_path, monkeypatch, loop, outer, inner, visible):
    registry = NodeRegistry()
    registry.register(NodeDescriptor("fixture.work", "Work", "Work", "1", "process",
        contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"),
        loader=lambda: pytest.fail("display must not bind Node implementations"))
    def call(identifier, kind, **fields):
        return {"id": identifier, "definition_id": kind, "display_name": identifier,
                "description": identifier, **fields}
    def definition(key, nodes, expand):
        return {"type_key": key, "display_name": key, "description": key, "expand": expand,
                "requires": [], "provides": [], "pipeline": {"nodes": nodes}}
    spec = call("outer_call", "vibeflow.loop.while", requires=[], provides=[],
                loop={"body": "detail.outer", "max_iterations": 1, "stop_after": 1}) if loop else call("outer_call", "detail.outer")
    graph = parse_graph_config({"rulesets": [], "nodeset_types": [
        definition("detail.inner", [call("leaf_work", "fixture.work")], inner),
        definition("detail.outer", [call("inner_call", "detail.inner")], outer),
    ], "pipeline": {"nodes": [spec]}}, project_root=tmp_path, root_path=tmp_path,
        root_id="fixture", source_path=tmp_path / "workflow.jsonc")
    prepared = prepare_python_presentation(graph, registry=registry)
    rendered = []
    def fragment(title, mermaid, *_args, **_kwargs):
        rendered.append((title, mermaid))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60)
    monkeypatch.setattr(review_fragments, "_render_fragment", fragment)
    review_svg.render_review_columns_svg(graph, prepared.compiled, tmp_path / "diagram.svg",
        expand_nodesets=True, prepared=prepared)
    svg_text = "\n".join(text for _, text in rendered)
    ascii_text = export_ascii_flowchart(graph, expand_nodesets=True, prepared=prepared)
    for layout in ("default", "review-columns"):
        text = export_mermaid(graph, expand_nodesets=True, mermaid_layout=layout, prepared=prepared)
        assert "outer_call" in text
        for name in ("inner_call", "leaf_work"):
            assert (name in text) == (name in visible)
    assert "outer_call" in svg_text and "outer_call" in ascii_text
    for name in ("inner_call", "leaf_work"):
        assert (name in svg_text) == (name in visible)
        assert (name in ascii_text) == (name in visible)
    if outer and not inner:
        assert next(text for title, text in rendered if "inner_call" in text).startswith("flowchart TD")
    assert set(prepared.graph.nodeset_types) == {"detail.outer", "detail.inner"}
    assert len(prepared._graphs) == 3
