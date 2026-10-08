from __future__ import annotations

from types import SimpleNamespace

import pytest

from vibeflow.core.compiler import CompiledGraph
from vibeflow.core.flow import GraphConfig, NodeSpec, NodesetSpec, LoopSpec
from vibeflow.tooling.application.javascript import review
from vibeflow.tooling.presentation.review_types import SvgFragment


def _compiled(graph):
    return CompiledGraph(order=tuple(n.id for n in graph.nodes), explicit_edges=(), data_edges=(),
        effective_edges=(), providers={}, consumers={},
        flow_kinds={n.id: "predefined" if n.type_used in graph.nodesets or n.type_used.startswith("vibeflow.loop") else "process" for n in graph.nodes})


def _result(*, outer_expand=True, inner_expand=True, loop=False):
    leaf = GraphConfig(nodes=(NodeSpec("leaf_work", "demo.work"),))
    inner = NodesetSpec("demo.inner", "Inner", "Inner detail", (), (), leaf, expand=inner_expand)
    body = GraphConfig(nodes=(NodeSpec("inner_call", "demo.inner"),), nodesets={inner.type_key: inner})
    outer = NodesetSpec("demo.outer", "Outer", "Outer detail", (), (), body, expand=outer_expand)
    top = NodeSpec("outer_call", "vibeflow.loop.while", loop=LoopSpec(body="demo.outer", max_iterations=1, stop_after=1)) if loop else NodeSpec("outer_call", "demo.outer")
    graph = GraphConfig(nodes=(top,), nodesets={outer.type_key: outer, inner.type_key: inner})
    descriptor = SimpleNamespace(rulesets=(), display_name="Work", description="Work", external=False, presentation={})
    # The source/ownership audit view is deliberately rich; it must never be
    # reused as the user's workflow diagram.
    internal = {"resources": {"node:demo.work": {"kind": "node", "id": "demo.work"}},
        "files": {"private_kernel.py": {"path": "private_kernel.py"}}, "relations": [],
        "rule_graph": {"rules": {"private.health": {}}, "rulesets": {"private.default": {}}}}
    resources = {"base_lib": {"demo.math": {"id": "demo.math", "display_name": "Math",
        "presentation": {"shape": "fr-rect", "fill": "#c8e4ff"}}},
        "capabilities": {"demo.session": {"id": "demo.session"}}}
    selected_plugins = ({"id": "demo", "status": "implemented", "declaration": {
        "display_name": "Selected package", "presentation": {"shape": "hex", "fill": "#e8d4ff"}},
        "source": {"ref": "plugin.ts"}},)
    return SimpleNamespace(graph=graph, compiled=_compiled(graph), compiled_nodesets={"demo.outer": _compiled(body), "demo.inner": _compiled(leaf)},
        catalogs=SimpleNamespace(nodes={"demo.work": descriptor}, plugin_records=selected_plugins),
        architecture={"resources": resources, "implementation_graph": internal},
        plugin_records=({"id": "demo.runtime"},), host_records=({"id": "demo.host"},),
        root=SimpleNamespace(id="demo"), plan=SimpleNamespace(workflow_id="demo"))



@pytest.mark.parametrize("loop", [False, True])
@pytest.mark.parametrize("outer,inner,visible", [(True, True, ["demo.outer", "demo.inner"]), (False, True, []), (True, False, ["demo.outer"])])
def test_hidden_nodeset_stops_all_javascript_display_traversal(tmp_path, monkeypatch, loop, outer, inner, visible):
    result = _result(outer_expand=outer, inner_expand=inner, loop=loop)
    rendered = []

    def fragment(title, mermaid, directory, **options):
        rendered.append((title, mermaid, options))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60,
            review_kind=options["kind"], review_owner=options["owner"], review_target=options["target"])

    monkeypatch.setattr(review, "_render_fragment", fragment)
    text = review.render_mermaid(result, expand_nodesets=True)
    ascii_text = review.render_ascii(result, expand_nodesets=True)
    coverage = review.write_review_svg(result, tmp_path / "review.svg", expand_nodesets=True, mermaid_layout="review-columns")
    assert coverage == review.expected_review_coverage(result)
    assert "outer_call" in text and "outer_call" in ascii_text
    assert [group.target for group in review._expanded_groups(result.graph)] == visible
    assert ("leaf_work" in text) == ("demo.inner" in visible)
    assert ("leaf_work" in ascii_text) == ("demo.inner" in visible)
    assert any("leaf_work" in mermaid for _, mermaid, _ in rendered) == ("demo.inner" in visible)
    assert any("inner_call" in mermaid for _, mermaid, _ in rendered) == ("demo.outer" in visible)
    if outer and not inner:
        assert next(mermaid for _, mermaid, _ in rendered if "inner_call" in mermaid).startswith("flowchart TD")
        assert text.split("%% expanded", 1)[1].splitlines()[1] == "flowchart TD"
    # Display metadata never alters the complete executable declaration table.
    assert set(result.graph.nodesets) == {"demo.outer", "demo.inner"}
    assert set(result.compiled_nodesets) == {"demo.outer", "demo.inner"}


def test_javascript_workflow_resources_are_small_directories(tmp_path, monkeypatch):
    result = _result()
    rendered = []
    def fragment(title, mermaid, directory, **options):
        rendered.append((title, mermaid))
        return SvgFragment(title, '<svg viewBox="0 0 120 60"><rect width="120" height="60"/></svg>', 120, 60,
            review_kind=options["kind"], review_owner=options["owner"], review_target=options["target"])
    monkeypatch.setattr(review, "_render_fragment", fragment)
    coverage = review.write_review_svg(result, tmp_path / "review.svg", expand_nodesets=True, mermaid_layout="review-columns")
    assert coverage == review.expected_review_coverage(result)
    assert [title for title, _ in rendered[:5]] == ["main pipeline", "plugins", "base_lib", "host_extensions", "capabilities"]
    for title, text in rendered[1:5]:
        assert text.startswith("flowchart LR")
        assert text.count(" -.-> ") == 1
        assert f'label: "{title}"' in text
    assert "vf_resource_" not in rendered[0][1]
    resources = "\n".join(text for _, text in rendered[1:5])
    assert "Selected package" in resources and "demo.math" in resources and "demo.host" in resources
    assert "demo.runtime" not in resources
    assert "shape: fr-rect" in resources and "fill:#c8e4ff" in resources
    assert "fill:#e8d4ff" in resources
    assert all(value not in resources for value in ("Node types", "private_kernel.py", "private.health", "reference", "plugin.ts", "rule:"))
    default = review.render_mermaid(result)
    detailed = review.render_mermaid(result, mermaid_layout="review-columns")
    assert "vf_resource_" not in default
    assert "%% resources: plugins" in detailed
    assert all(value not in detailed for value in ("Node types", "private_kernel.py", "private.health", "reference", "plugin.ts"))


def test_javascript_diagram_does_not_offer_internal_rule_catalog_switch():
    import inspect
    assert all("show_rules" not in inspect.signature(function).parameters for function in (
        review.render_mermaid, review.write_review_svg, review.expected_review_coverage, review.render_review_svg))


def test_javascript_empty_resources_do_not_create_catalog_panels():
    result = _result()
    result.architecture["resources"] = {}
    result.catalogs.plugin_records = ()
    result.plugin_records = ()
    result.host_records = ()
    assert review._resource_fragments(result) == ()
    assert "%% resources:" not in review.render_mermaid(result, mermaid_layout="review-columns")


def test_javascript_planned_selection_remains_one_directory_entry():
    result = _result()
    result.catalogs.plugin_records = ({"id": "future.plugin", "status": "planned", "source": {"ref": "never-loaded.ts"}},)
    fragment = review._resource_fragments(result)[0]
    assert "future.plugin" in fragment["mermaid"] and "status: planned" in fragment["mermaid"]
    assert "never-loaded.ts" not in fragment["mermaid"]
    assert fragment["mermaid"].count(" -.-> ") == 1


def test_javascript_selected_resource_health_and_call_style_remain_visible():
    result = _result()
    lifecycle = SimpleNamespace(id="demo.runtime", to_dict=lambda: {"id": "demo.runtime"})
    result.catalogs.plugins = (lifecycle,)
    result.catalogs.origins = {("plugins", "demo.runtime"): SimpleNamespace(plugin_id="demo")}
    result.rule_report = SimpleNamespace(findings=({"object_type": "plugin", "object_id": "demo.runtime", "severity": "warning"},
        {"object_type": "base_lib", "object_id": "demo.math", "severity": "warning"}))
    result.document = SimpleNamespace(data={"base_lib": {"modules": [{"id": "demo.math", "style": {"fill": "#ffeebb"}}]}})
    fragments = {item["id"]: item["mermaid"] for item in review._resource_fragments(result)}
    assert "fill:#fef3c7" in fragments["plugins"]
    assert "demo.runtime" not in fragments["plugins"]
    assert "fill:#ffeebb" in fragments["base_lib"]
    assert "shape: fr-rect" in fragments["base_lib"]


def test_javascript_call_health_uses_rule_associations_not_shared_source_files():
    from vibeflow.tooling.application.javascript.presentation_status import node_health_classes
    graph = GraphConfig(nodes=(NodeSpec("first", "demo.work"), NodeSpec("second", "demo.work"),
                               NodeSpec("neighbor", "demo.other")))
    source = {"object_type": "node", "object_id": "demo.work", "severity": "warning",
              "source_location": {"path": "same.ts", "line": 1},
              "details": {"node_type": "demo.work", "call_paths": [["first"], ["second"]]}}
    call = {**source, "severity": "error", "details": {"node_type": "demo.work", "call_paths": [["first"]]}}
    unowned = {"object_type": "file", "object_id": "same.ts", "severity": "error",
               "source_location": source["source_location"]}
    statuses = node_health_classes(graph, (source, call, unowned))
    assert statuses == {(id(graph), "first"): "healthError", (id(graph), "second"): "healthWarning"}


def test_javascript_call_health_distinguishes_repeated_node_ids_in_nested_graphs():
    from vibeflow.tooling.application.javascript.presentation_status import node_health_classes
    child = GraphConfig(nodes=(NodeSpec("same", "demo.work"),))
    definition = NodesetSpec("demo.child", "Child", "A child", (), (), child)
    graph = GraphConfig(nodes=(NodeSpec("same", "demo.work"), NodeSpec("parent", "demo.child")),
                        nodesets={definition.type_key: definition})
    finding = {"object_type": "node", "object_id": "demo.work", "severity": "warning",
               "details": {"node_type": "demo.work", "call_paths": [["parent", "same"]]}}
    statuses = node_health_classes(graph, (finding,))
    assert statuses == {(id(child), "same"): "healthWarning"}
    # Native workflow Rules associate Node IDs with their block's call path.
    workflow_finding = {"object_type": "node", "object_id": "same", "severity": "warning",
                        "details": {"call_paths": [["parent"]]}}
    assert node_health_classes(graph, (workflow_finding,)) == statuses


@pytest.mark.parametrize("status,override,expected,origin", [
    ("implemented", "", "#fef3c7", "status"),
    ("implemented", "#ffeebb", "#ffeebb", "call"),
    ("planned", "", "#fef08a", "status"),
])
def test_javascript_actual_call_architecture_and_mermaid_share_health_style(status, override, expected, origin):
    from vibeflow.core.flow import NodeStyle
    from vibeflow.tooling.application.javascript.audit import _javascript_node_document
    from vibeflow.tooling.application.javascript.presentation_status import node_health_classes
    result = _result()
    call = NodeSpec("call", "demo.work", status=status, style=NodeStyle(fill=override))
    graph = GraphConfig(nodes=(call,))
    descriptor = result.catalogs.nodes["demo.work"]
    descriptor.tags, descriptor.metadata = (), {}
    result.graph, result.compiled = graph, _compiled(graph)
    finding = {"object_type": "node", "object_id": "demo.work", "severity": "warning",
               "details": {"node_type": "demo.work", "call_paths": [["call"]]}}
    record = _javascript_node_document(graph, result.compiled, call, source={"path": "workflow.jsonc"},
        graph_lock_scope="root", catalogs=result.catalogs, health_classes=node_health_classes(graph, (finding,)))
    result.architecture["workflow"] = {"nodes": [record]}
    assert record["presentation"]["values"]["fill"] == expected
    assert record["presentation"]["sources"]["fill"] == origin
    assert f"style vf_call fill:{expected}" in review.render_mermaid(result)


def test_javascript_resource_directory_defaults_use_the_shared_resource_presentation():
    from vibeflow.tooling.presentation.node_presentation import resolve_presentation
    for kind, resource_kind, native in (("base_lib", "base_lib", "baseLibResource"),
        ("plugins", "plugin", "pluginResource"), ("host_extensions", "host_extension", "hostExtensionResource")):
        presentation = resolve_presentation({"id": "selected"}, resource_kind=resource_kind, native_class=native)
        text = review._resource_mermaid(kind, ({"id": "selected"},))
        assert f"shape: {presentation.shape}" in text
        assert presentation.mermaid_style() in text
        assert text.count(" -.-> ") == 1


def test_host_selection_style_survives_resolution_and_directory_transport():
    from dataclasses import replace
    from vibeflow.core.descriptors import HostExtensionCatalog
    from vibeflow.core.descriptors.decode import decode_resource
    from vibeflow.tooling.application.javascript.host_selection import declared_hosts
    from vibeflow.tooling.project.host_extensions import host_extension_resources, resolve_host_extension_resources
    style = {"fill": "#ffeebb", "stroke": "#225588", "text": "#123789"}
    descriptor = decode_resource({"kind": "host_extension", "id": "demo.host", "targets": ["node"],
        "provides": [], "dependencies": [], "presentation": {"fill": "#aaccee"},
        "implementations": [{"language": "typescript", "targets": ["node"], "source": {"kind": "file", "ref": "host.ts", "export": "host"}}]})
    catalog = HostExtensionCatalog()
    catalog.register(descriptor)
    config = {"host_extensions": [{"id": "demo.host", "style": style}]}
    findings = []
    selections = host_extension_resources(config, findings=findings)
    resolved, failures = resolve_host_extension_resources(tuple(selections), catalog=catalog)
    assert findings == [] and failures == ()
    actual = declared_hosts(config, catalog=catalog)
    assert actual[0].to_dict()["style"] == resolved[0].to_dict()["style"] == style
    style["fill"] = "#abcdef"
    assert actual[0].style["fill"] == "#ffeebb"
    with pytest.raises(TypeError):
        actual[0].style["fill"] = "#abcdef"
    result = _result()
    result.catalogs.host_extensions = catalog
    result.host_records = (actual[0].to_dict(),)
    text = next(item["mermaid"] for item in review._resource_fragments(result) if item["id"] == "host_extensions")
    assert "fill:#ffeebb" in text and "stroke:#225588" in text and "color:#123789" in text
    assert replace(actual[0], status="planned").to_dict()["style"]["fill"] == "#ffeebb"
