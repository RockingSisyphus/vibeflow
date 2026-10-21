"""Prepared review facts do not opt workflow fragments into resource rendering."""

from collections import Counter

import pytest

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid, review_fragments, review_svg
from vibeflow.tooling.presentation.mermaid.types import SvgFragment
from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation
from vibeflow.tooling.project.graph_config import parse_graph_config


@pytest.fixture
def prepared_review(tmp_path, monkeypatch):
    registry = NodeRegistry()
    bindings = []

    def loader():
        bindings.append("bound")
        raise AssertionError("diagram rendering must not bind an implementation")

    registry.register(NodeDescriptor("fixture.work", "Work", "Work implementation", "1", "process",
        contract=NodeContractDescriptor(), rulesets=(), node_type="vibeflow.node"), loader=loader)

    def call(identifier, kind):
        return {"id": identifier, "definition_id": kind, "display_name": identifier, "description": identifier}

    def definition(key, nodes):
        return {"type_key": key, "display_name": key, "description": key,
                "requires": [], "provides": [], "pipeline": {"nodes": nodes}}

    graph = parse_graph_config({"rulesets": [], "nodeset_types": [
        definition("detail.shared", [call("leaf_work", "fixture.work")]),
        definition("detail.one", [call("first_child", "detail.shared"), call("second_child", "detail.shared")]),
        definition("detail.two", [call("third_child", "detail.shared")]),
    ], "pipeline": {"nodes": [call("parent_one", "detail.one"), call("parent_two", "detail.two")]}},
        project_root=tmp_path, root_path=tmp_path, root_id="fixture", source_path=tmp_path / "workflow.jsonc")
    resources = {
        "plugins": [{"id": "fixture.plugin", "name": "Fixture Plugin", "type": "runtime"}],
        "base_lib": {"modules": [{"id": "fixture.base", "module": "Fixture BaseLib"}]},
    }
    counts = Counter()
    original = GraphCompiler.compile_with_findings

    def compile(self, graph, **kwargs):
        counts["compiles"] += 1
        return original(self, graph, **kwargs)

    monkeypatch.setattr(GraphCompiler, "compile_with_findings", compile)
    prepared = prepare_python_presentation(graph, registry=registry, resources=resources)
    assert counts["compiles"] == 4  # Root plus three definitions, not each shared invocation.
    return graph, resources, prepared, counts, bindings


def test_review_workflow_and_nested_frames_exclude_resource_columns(prepared_review, tmp_path, monkeypatch):
    graph, resources, prepared, counts, bindings = prepared_review
    rendered = []

    def fragment(title, mermaid_text, *_args, **_kwargs):
        rendered.append((title, mermaid_text))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60)

    monkeypatch.setattr(review_fragments, "_render_fragment", fragment)
    output = tmp_path / "review.svg"
    review_svg.render_review_columns_svg(graph, prepared.compiled, output,
        resources=resources, expand_nodesets=True, prepared=prepared)

    resource_titles = {"plugins", "base_lib"}
    frames = [(title, text) for title, text in rendered if title not in resource_titles]
    assert rendered[0][0] == "main pipeline"
    assert sum(title == "parent flow" for title, _ in frames) == 2
    shared = [(title, text) for title, text in frames if "type_key: detail.shared" in title]
    assert len(shared) == 2  # One local group per parent, reusing one compiled definition.
    assert any("calls: 2 [first_child, second_child]" in title for title, _ in shared)
    assert any("id: third_child" in title for title, _ in shared)
    for title, text in frames:
        assert "resource_plugins" not in text, (title, text)
        assert "resource_base_lib" not in text, (title, text)
        assert "resource_host_extensions" not in text, (title, text)
        assert "Fixture Plugin" not in text and "Fixture BaseLib" not in text and "Fixture Host" not in text

    columns = {title: text for title, text in rendered if title in resource_titles}
    assert set(columns) == resource_titles
    assert "Fixture Plugin" in columns["plugins"]
    assert "Fixture BaseLib" in columns["base_lib"]
    assert output.is_file()
    assert counts["compiles"] == 4 and bindings == []


def test_explicit_mermaid_resources_remain_visible_with_shared_preparation(prepared_review):
    graph, resources, prepared, counts, bindings = prepared_review
    implicit = export_mermaid(graph, expand_nodesets=True, prepared=prepared)
    explicit = export_mermaid(graph, resources=resources, expand_nodesets=True, prepared=prepared)
    assert "resource_plugins" not in implicit
    assert "resource_base_lib" not in implicit
    assert "resource_host_extensions" not in implicit
    for label in ("Fixture Plugin", "Fixture BaseLib"):
        assert label in explicit
    assert "leaf_work" in implicit and "leaf_work" in explicit
    assert counts["compiles"] == 4 and bindings == []


def test_explicit_resource_subset_is_not_replaced_by_prepared_resources(prepared_review):
    graph, resources, prepared, counts, bindings = prepared_review
    selected = {"plugins": resources["plugins"]}
    text = export_mermaid(graph, resources=selected, prepared=prepared)
    assert "Fixture Plugin" in text
    assert "Fixture BaseLib" not in text and "Fixture Host" not in text
    assert counts["compiles"] == 4 and bindings == []


@pytest.mark.parametrize("layout", ["default", "review-columns"])
@pytest.mark.parametrize("selection", ["omitted", "none", "empty", "subset"])
def test_resource_selection_is_local_to_each_export_and_preserves_architecture(prepared_review, layout, selection):
    graph, resources, prepared, counts, bindings = prepared_review
    before = build_architecture_document(graph, prepared=prepared)
    options = {"prepared": prepared, "mermaid_layout": layout}
    if selection != "omitted":
        options["resources"] = None if selection == "none" else {} if selection == "empty" else {"plugins": resources["plugins"]}
    selected = export_mermaid(graph, **options)
    full = export_mermaid(graph, resources=resources, prepared=prepared, mermaid_layout=layout)
    after = build_architecture_document(graph, prepared=prepared)

    assert after == before  # A subset followed by a full view never mutates shared facts.
    assert counts["compiles"] == 4 and bindings == []
    assert ("Fixture Plugin" in selected) == (selection == "subset")
    assert "Fixture BaseLib" not in selected and "Fixture Host" not in selected
    for label in ("Fixture Plugin", "Fixture BaseLib"):
        assert label in full
