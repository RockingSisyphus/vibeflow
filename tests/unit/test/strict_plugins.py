import re
import xml.etree.ElementTree as ET

from tests.unit.strict_support import *


def _review_title_positions(svg_text: str) -> dict[str, tuple[float, float]]:
    root = ET.fromstring(svg_text)
    positions: dict[str, tuple[float, float]] = {}
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "text" and element.attrib.get("class") == "review-title" and element.text:
            positions[element.text] = (float(element.attrib["x"]), float(element.attrib["y"]))
    return positions


class SinkNode:
    NODE_INFO = NodeInfo(
        type_key="test.sink",
        display_name="Sink",
        category="test",
        description="Consumes a value.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("value.in", "exactly_one"),),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


def test_compiler_and_runtime_plugins_are_hooked(tmp_path) -> None:
    marker_path = tmp_path / "plugin_calls.jsonl"
    plugin_path = tmp_path / "hook_plugins.py"
    plugin_path.write_text(
        f"""
import json
from pathlib import Path
from vibeflow import PluginInfo

MARKER = Path({str(marker_path)!r})

def record(value):
    with MARKER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\\n")

class CompilerPlugin:
    PLUGIN_INFO = PluginInfo("compiler_hook", "compiler", "Compiler Hook", "test", "Records compiler hook calls.", "0.1.0")
    name = "compiler_hook"
    def after_compile(self, graph, compiled):
        record({{"hook": "after_compile", "nodes": len(graph.nodes)}})

class RuntimePlugin:
    PLUGIN_INFO = PluginInfo("runtime_hook", "runtime", "Runtime Hook", "test", "Records runtime hook calls.", "0.1.0")
    name = "runtime_hook"
    def before_node(self, name, node_type, input_summary):
        record({{"hook": "before_node", "name": name}})
    def after_run(self, state, trace):
        record({{"hook": "after_run", "events": len(trace.get("events", []))}})
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {
                "plugins": [
                    {"module": str(plugin_path), "class": "CompilerPlugin", "type": "compiler"},
                    {"module": str(plugin_path), "class": "RuntimePlugin", "type": "runtime"},
                ],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )
    run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="plugin_hooks")
    hooks = [json.loads(line)["hook"] for line in marker_path.read_text(encoding="utf-8").splitlines()]
    assert "after_compile" in hooks
    assert "before_node" in hooks
    assert "after_run" in hooks

def test_plugin_registry_priority_scope_and_conflict_strategy() -> None:
    class A:
        name = "same"
        priority = 20

    class B:
        name = "same"
        priority = 10

    registry = PluginRegistry()
    registry.register(A(), plugin_type="policy", scope="project")
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(B(), plugin_type="policy")
    registry.register(B(), plugin_type="policy", conflict="replace", scope="nodeset")
    descriptors = registry.to_dict()["plugins"]
    assert descriptors == [
        {"name": "same", "type": "policy", "priority": 10, "scope": "nodeset", "source": "manual"}
    ]

def test_nodeset_can_be_used_as_a_node() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                {
                    "name": "math.add_one",
                    "display_name": "Add One",
                    "category": "math",
                    "description": "Composite add-one flow.",
                    "version": "0.1.0",
                    "purity": "pure",
                    "requires": [REQ_SPEC("value.in")],
                    "provides": [PROV_SPEC("value.out")],
                    "exports": [PROV_SPEC("value.out")],
                    "pipeline": {
                        "inputs": [PROV_SPEC("value.in")],
                        "nodes": [
                            {"name": "start", "type": "test.start"},
                            {
                                "name": "add",
                                "type": "test.add",
                                "requires": [REQ_SPEC("value.in")],
                                "provides": [PROV_SPEC("value.out")],
                                "delta": 1,
                            },
                            {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                        ],
                        "edges": _edge_chain("start", "add", "end"),
                        "outputs": [REQ_SPEC("value.out")],
                    },
                }
            ],
                "pipeline": {
                    "inputs": [PROV_SPEC("value.in")],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": [REQ_SPEC("value.in")],
                            "provides": [PROV_SPEC("value.out")],
                        },
                        {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                    ],
                    "edges": _edge_chain("start", "composite", "end"),
                    "outputs": [REQ_SPEC("value.out")],
                },
        }
    )
    context = PipelineRuntime(graph, registry=_registry()).run({"value.in": 2})
    assert context.get("value.out")["value"] == 3

def test_health_report_and_mermaid_export() -> None:
    graph = parse_graph_config(
        {
            "pipeline": _seed_add_pipeline()
        }
    )
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    serialized = report.to_dict()
    assert serialized["warnings"][0]["rule_id"] == "GRAPH.SMELL.DUPLICATE_LOGIC"
    mermaid = export_mermaid(graph)
    assert "flowchart TD" in mermaid
    assert "seed --> add" in mermaid
    assert "provides: value.in" in mermaid
    assert "requires: value.in" in mermaid

def test_mermaid_collapses_and_expands_nodesets_with_contract_metadata() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"name": "inner", "description": "Internal add step."}),
                )
            ],
                "pipeline": {
                    "inputs": [PROV_SPEC("value.in")],
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "input", "type": "test.value_input", "requires": [REQ_SPEC("value.in")]},
                        {
                            "name": "composite",
                            "type": "nodeset.math.add_one",
                            "requires": [REQ_SPEC("value.in")],
                            "provides": [PROV_SPEC("value.out")],
                        },
                        {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                    ],
                    "edges": _edge_chain("start", "input", "composite", "end"),
                },
        }
    )

    collapsed = export_mermaid(graph)
    assert 'composite@{ shape: fr-rect, label: "composite\\nnodeset.math.add_one' in collapsed
    assert "requires: value.in" in collapsed
    assert "exports: value.out" in collapsed
    assert "composite__inner" not in collapsed

    expanded = export_mermaid(graph, expand_nodesets=True)
    assert 'subgraph composite__expanded["math.add_one"]' in expanded
    assert 'composite__inner@{ shape: rect, label: "inner\\ntest.add' in expanded
    assert "Internal add step." in expanded

def test_mermaid_review_columns_layout_separates_main_resources_and_expanded_nodesets() -> None:
    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"name": "inner", "description": "Internal add step."}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": [REQ_SPEC("value.in")]},
                    {
                        "name": "composite",
                        "type": "nodeset.math.add_one",
                        "requires": [REQ_SPEC("value.in")],
                        "provides": [PROV_SPEC("value.out")],
                    },
                    {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        }
    )
    resources = {
        "plugins": [
            {
                "name": "review_policy",
                "type": "policy",
                "module": "project.plugins.review_policy",
                "status": "planned",
                "info": {"display_name": "Review Policy", "description": "Checks graph policy."},
            }
        ],
        "base_lib": {
            "modules": [
                {
                    "name": "contracts",
                    "module": "project.base_lib.contracts",
                    "status": "implemented",
                    "info": {"display_name": "Contracts", "description": "Shared contract helpers."},
                }
            ]
        },
    }

    mermaid = export_mermaid(graph, expand_nodesets=True, resources=resources, mermaid_layout="review-columns")

    assert mermaid.startswith("flowchart LR")
    assert 'subgraph __vibeflow_layout_main["main pipeline"]' in mermaid
    assert "    direction TB" in mermaid
    assert "start --> input" in mermaid
    assert 'subgraph __vibeflow_layout_plugins["plugins"]' in mermaid
    assert 'subgraph __vibeflow_layout_base_lib["base_lib"]' in mermaid
    assert 'subgraph __vibeflow_layout_nodesets["expanded nodesets"]' in mermaid
    assert 'subgraph __vibeflow_layout_nodesets__composite__expanded["composite - math.add_one"]' in mermaid
    assert "__vibeflow_layout_nodesets__composite__inner" in mermaid
    assert mermaid.index("__vibeflow_layout_main") < mermaid.index("__vibeflow_layout_plugins")
    assert mermaid.index("__vibeflow_layout_plugins") < mermaid.index("__vibeflow_layout_base_lib")
    assert mermaid.index("__vibeflow_layout_base_lib") < mermaid.index("__vibeflow_layout_nodesets")

def test_review_columns_svg_composer_places_columns_left_to_right(tmp_path) -> None:
    if not is_mermaid_svg_renderer_available():
        pytest.skip("Mermaid SVG renderer is not installed")
    from vibeflow.mermaid_review_svg import render_review_columns_svg

    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"name": "inner"}),
                )
            ],
            "pipeline": {
                "inputs": [PROV_SPEC("value.in")],
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.value_input", "requires": [REQ_SPEC("value.in")]},
                    {"name": "composite", "type": "nodeset.math.add_one", "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("value.out")]},
                    {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        }
    )
    compiled = GraphCompiler().compile(graph)
    resources = {
        "plugins": [{"name": "policy", "type": "policy", "module": "project.plugins.policy", "status": "planned"}],
        "base_lib": {"modules": [{"name": "contracts", "module": "project.base_lib.contracts", "status": "implemented"}]},
    }

    output = tmp_path / "review.svg"
    render_review_columns_svg(graph, compiled, output, resources=resources, expand_nodesets=True)
    svg = output.read_text(encoding="utf-8")

    titles = re.findall(r'<text class="review-title" x="([0-9.]+)" y="([0-9.]+)">([^<]+)</text>', svg)
    positions = {title: (float(x), float(y)) for x, y, title in titles}
    assert positions["main pipeline"][0] < positions["plugins"][0] < positions["base_lib"][0]
    assert positions["base_lib"][0] < positions["composite - math.add_one"][0]
    assert positions["main pipeline"][1] == positions["plugins"][1] == positions["base_lib"][1] == positions["composite - math.add_one"][1]
    assert 'data:image/svg+xml;base64,' not in svg
    assert 'class="review-inline-fragment"' in svg


def test_review_columns_svg_composer_stacks_nodesets_and_scales_wide_fragments() -> None:
    from vibeflow.mermaid_review_svg import REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH, _SvgFragment, _compose_svg

    svg = _compose_svg(
        [
            [_SvgFragment("main pipeline", '<svg viewBox="0 0 100 200"></svg>', 100.0, 200.0)],
            [_SvgFragment("plugins", '<svg viewBox="0 0 50 50"></svg>', 50.0, 50.0)],
            [_SvgFragment("base_lib", '<svg viewBox="0 0 50 50"></svg>', 50.0, 50.0)],
            [
                _SvgFragment("first - ns", '<svg viewBox="0 0 6400 1600"></svg>', 6400.0, 1600.0),
                _SvgFragment("second - ns", '<svg viewBox="0 0 800 400"></svg>', 800.0, 400.0),
            ],
        ],
        background="transparent",
    )

    titles = re.findall(r'<text class="review-title" x="([0-9.]+)" y="([0-9.]+)">([^<]+)</text>', svg)
    positions = {title: (float(x), float(y)) for x, y, title in titles}
    assert positions["main pipeline"][0] < positions["plugins"][0] < positions["base_lib"][0] < positions["first - ns"][0]
    assert positions["first - ns"][0] == positions["second - ns"][0]
    assert positions["first - ns"][1] < positions["second - ns"][1]
    assert 'viewBox="0 0 3640.000 1376.000"' in svg
    assert svg.count('class="review-panel-frame"') == 5
    assert svg.count('class="review-title-bar"') == 5
    assert svg.count('class="review-inline-fragment"') == 5
    assert 'data:image/svg+xml;base64,' not in svg
    assert 'scale(0.500000 0.500000)' in svg

    narrow_svg = _compose_svg(
        [[_SvgFragment("wide", '<svg viewBox="0 0 6400 1600"></svg>', 6400.0, 1600.0)]],
        background="transparent",
        review_fragment_max_width=1600.0,
    )
    assert 'scale(0.250000 0.250000)' in narrow_svg
    assert 'viewBox="0 0 1648.000 490.000"' in narrow_svg


def test_review_columns_inline_fragments_prefix_duplicate_svg_ids() -> None:
    from vibeflow.mermaid_review_svg import _SvgFragment, _compose_svg

    fragment_svg = (
        '<svg id="my-svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10">'
        "<style>#my-svg{font-family:Arial}#my-svg .node rect{fill:#ECECFF}.edge{stroke: #abc;fill:#333333}</style>"
        '<defs><marker id="arrow"></marker></defs>'
        '<g class="node"><rect/></g><path class="edge" marker-end="url(#arrow)" href="#arrow" xlink:href="#arrow"/>'
        "</svg>"
    )
    svg = _compose_svg(
        [
            [
                _SvgFragment("first", fragment_svg, 10.0, 10.0),
                _SvgFragment("second", fragment_svg, 10.0, 10.0),
            ]
        ],
        background="transparent",
    )

    assert 'id="my-svg"' not in svg
    assert 'id="arrow"' not in svg
    assert 'id="vf_column_0_0_my-svg"' in svg
    assert 'id="vf_column_0_1_my-svg"' in svg
    assert 'id="vf_column_0_0_arrow"' in svg
    assert 'id="vf_column_0_1_arrow"' in svg
    assert "#my-svg" not in svg
    assert "#vf_column_0_0_my-svg{font-family:Arial}" in svg
    assert "#vf_column_0_0_my-svg .node rect" in svg
    assert "#vf_column_0_1_my-svg{font-family:Arial}" in svg
    assert "#vf_column_0_1_my-svg .node rect" in svg
    assert "fill:#333333" in svg
    assert "stroke: #abc" in svg
    assert 'marker-end="url(#vf_column_0_0_arrow)"' in svg
    assert 'marker-end="url(#vf_column_0_1_arrow)"' in svg
    assert 'href="#vf_column_0_0_arrow"' in svg
    assert 'href="#vf_column_0_1_arrow"' in svg
    assert 'xlink:href="#vf_column_0_0_arrow"' in svg
    assert 'xlink:href="#vf_column_0_1_arrow"' in svg


def test_review_columns_resource_fragments_render_root_left_to_children_right() -> None:
    from vibeflow.mermaid_review_svg import _resource_mermaid

    mermaid = _resource_mermaid(
        "plugins",
        (
            {"name": "policy", "type": "policy", "module": "project.plugins.policy"},
            {"name": "runtime", "type": "runtime", "module": "project.plugins.runtime"},
        ),
        kind="plugin",
    )

    assert mermaid.startswith("flowchart LR")
    assert "resource_plugins -.-> resource_plugins_0" in mermaid
    assert "resource_plugins -.-> resource_plugins_1" in mermaid


def test_run_checked_writes_quick_and_expanded_svg_artifacts(tmp_path, monkeypatch) -> None:
    import vibeflow.mermaid_render as mermaid_render_module
    import vibeflow.mermaid_review_svg as review_svg_module

    quick_calls: list[Path] = []
    expanded_calls: list[dict[str, object]] = []

    def fake_quick_svg(mermaid_text, output, **kwargs):
        quick_calls.append(Path(output))
        Path(output).write_text("<svg>quick</svg>", encoding="utf-8")

    def fake_expanded_svg(graph, compiled, output, **kwargs):
        expanded_calls.append({"output": Path(output), **kwargs})
        Path(output).write_text("<svg>expanded</svg>", encoding="utf-8")

    monkeypatch.setattr(mermaid_render_module, "render_mermaid_svg", fake_quick_svg)
    monkeypatch.setattr(review_svg_module, "render_review_columns_svg", fake_expanded_svg)

    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"pipeline": _seed_add_pipeline()}), encoding="utf-8")
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="svg_artifacts")

    assert quick_calls == [result.run_dir / "graph.svg"]
    assert (result.run_dir / "graph.svg").read_text(encoding="utf-8") == "<svg>quick</svg>"
    assert (result.run_dir / "graph.expanded.svg").read_text(encoding="utf-8") == "<svg>expanded</svg>"
    assert expanded_calls[0]["output"] == result.run_dir / "graph.expanded.svg"
    assert expanded_calls[0]["expand_nodesets"] is True
    assert expanded_calls[0]["resources"] is not None


def test_run_checked_records_expanded_svg_error_without_failing_run(tmp_path, monkeypatch) -> None:
    import vibeflow.mermaid_render as mermaid_render_module
    import vibeflow.mermaid_review_svg as review_svg_module
    from vibeflow.mermaid_render import MermaidRenderError

    def fake_quick_svg(mermaid_text, output, **kwargs):
        Path(output).write_text("<svg>quick</svg>", encoding="utf-8")

    def fail_expanded_svg(*args, **kwargs):
        raise MermaidRenderError("expanded failed")

    monkeypatch.setattr(mermaid_render_module, "render_mermaid_svg", fake_quick_svg)
    monkeypatch.setattr(review_svg_module, "render_review_columns_svg", fail_expanded_svg)

    config_path = tmp_path / "workflow.json"
    config_path.write_text(json.dumps({"pipeline": _seed_add_pipeline()}), encoding="utf-8")
    result = run_checked(config_path, registry=_registry(), run_root=tmp_path / "runs", run_id="svg_error")

    assert (result.run_dir / "graph.svg").exists()
    assert not (result.run_dir / "graph.expanded.svg").exists()
    assert (result.run_dir / "graph.expanded.svg.error.txt").read_text(encoding="utf-8") == "expanded failed"


def test_nodeset_detail_leaf_mermaid_uses_lr_with_layout_spine() -> None:
    from vibeflow.flowchart_render_helpers import compile_for_render
    from vibeflow.mermaid_review_svg import _nodeset_mermaid

    graph = parse_graph_config({"pipeline": _input_add_pipeline(add={"name": "inner"})})
    mermaid = _nodeset_mermaid(
        graph,
        compile_for_render(graph, None, _registry()),
        registry=_registry(),
        show_contract=True,
        show_semantics=True,
        direction="LR",
    )

    assert mermaid.startswith("flowchart LR")
    assert "classDef layoutAnchor" in mermaid
    assert "__vibeflow_layout_start ~~~ start" in mermaid
    assert "input ~~~ inner" in mermaid
    assert "inner ~~~ n_end" in mermaid


def test_nodeset_detail_parent_mermaid_preserves_collapsed_callsite_edges() -> None:
    from vibeflow.flowchart_render_helpers import compile_for_render
    from vibeflow.mermaid_review_svg import _nodeset_mermaid

    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config(
                    "detail.leaf",
                    pipeline=_input_add_pipeline(add={"name": "inner"}),
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                ),
                _nodeset_config(
                    "detail.parent",
                    pipeline={
                        "nodes": [
                            {"name": "start", "type": "test.start"},
                            {"name": "before", "type": "test.value_input", "requires": [REQ_SPEC("value.in")]},
                            {"name": "child", "type": "nodeset.detail.leaf"},
                            {"name": "after", "type": "test.out_end"},
                        ],
                        "edges": [
                            {"from": "start", "to": "before"},
                            {"from": "before", "to": "child", "when": "route == 'detail'"},
                            {"from": "child", "to": "after"},
                        ],
                    },
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                ),
            ],
            "pipeline": {
                "nodes": [
                    {"name": "main", "type": "nodeset.detail.parent"},
                ],
            },
        }
    )
    parent = graph.nodesets["detail.parent"]
    mermaid = _nodeset_mermaid(
        parent.graph,
        compile_for_render(parent.graph, None, _registry()),
        registry=_registry(),
        show_contract=True,
        show_semantics=True,
        direction="TD",
    )

    assert mermaid.startswith("flowchart TD")
    assert 'child@{ shape: fr-rect, label: "child\\nnodeset.detail.leaf' in mermaid
    assert "before -->|route == 'detail'| child" in mermaid
    assert "child --> after" in mermaid
    assert "inner@{ shape:" not in mermaid


def test_nodeset_detail_panel_places_children_right_and_stacked() -> None:
    from vibeflow.mermaid_review_svg import _SvgFragment, _compose_detail_panel_svg

    svg = _compose_detail_panel_svg(
        _SvgFragment("parent flow", '<svg viewBox="0 0 100 200"></svg>', 100.0, 200.0),
        [
            _SvgFragment("first - detail.leaf", '<svg viewBox="0 0 300 50"></svg>', 300.0, 50.0),
            _SvgFragment("second - detail.leaf", '<svg viewBox="0 0 200 70"></svg>', 200.0, 70.0),
        ],
        background="transparent",
    )

    titles = re.findall(r'<text class="review-title" x="([0-9.]+)" y="([0-9.]+)">([^<]+)</text>', svg)
    positions = {title: (float(x), float(y)) for x, y, title in titles}
    assert positions["parent flow"][0] < positions["first - detail.leaf"][0]
    assert positions["first - detail.leaf"][0] == positions["second - detail.leaf"][0]
    assert positions["first - detail.leaf"][1] < positions["second - detail.leaf"][1]
    assert svg.count('class="review-panel-frame"') == 3
    assert svg.count('class="review-title-bar"') == 3

    groups = re.findall(r'<g class="review-inline-fragment" transform="translate\(([0-9.]+) ([0-9.]+)\)', svg)
    assert float(groups[0][0]) < float(groups[1][0])
    assert 'data:image/svg+xml;base64,' not in svg


def test_nodeset_detail_fragment_recurses_nested_child_panels(tmp_path, monkeypatch) -> None:
    from vibeflow import mermaid_review_svg as review_svg

    graph = parse_graph_config(
        {
            "nodesets": [
                _nodeset_config("detail.leaf_one", pipeline=_input_add_pipeline(add={"name": "leaf_one_add"})),
                _nodeset_config("detail.leaf_two", pipeline=_input_add_pipeline(add={"name": "leaf_two_add"})),
                _nodeset_config("detail.leaf_three", pipeline=_input_add_pipeline(add={"name": "leaf_three_add"})),
                _nodeset_config(
                    "detail.mid",
                    pipeline={
                        "nodes": [
                            {"name": "mid_start", "type": "test.start"},
                            {"name": "inner_a", "type": "nodeset.detail.leaf_two"},
                            {"name": "inner_b", "type": "nodeset.detail.leaf_three"},
                            {"name": "mid_end", "type": "test.out_end"},
                        ],
                        "edges": _edge_chain("mid_start", "inner_a", "inner_b", "mid_end"),
                    },
                ),
                _nodeset_config(
                    "detail.root",
                    pipeline={
                        "nodes": [
                            {"name": "root_start", "type": "test.start"},
                            {"name": "first", "type": "nodeset.detail.leaf_one"},
                            {"name": "second", "type": "nodeset.detail.mid"},
                            {"name": "third", "type": "nodeset.detail.leaf_three"},
                            {"name": "root_end", "type": "test.out_end"},
                        ],
                        "edges": _edge_chain("root_start", "first", "second", "third", "root_end"),
                    },
                ),
            ],
            "pipeline": {"nodes": [{"name": "root", "type": "nodeset.detail.root"}]},
        }
    )
    rendered: list[tuple[str, str]] = []

    def fake_render_fragment(title, mermaid_text, temp_dir, **kwargs):
        rendered.append((title, mermaid_text))
        width = 180.0 + len(rendered) * 10
        height = 80.0 + len(rendered) * 5
        svg_text = f'<svg viewBox="0 0 {width:.3f} {height:.3f}"><text>{title}</text></svg>'
        return review_svg._SvgFragment(title, svg_text, width, height)

    monkeypatch.setattr(review_svg, "_render_fragment", fake_render_fragment)
    fragment = review_svg._render_nodeset_detail_fragment(
        "root - detail.root",
        graph.nodesets["detail.root"],
        tmp_path,
        registry=_registry(),
        show_contract=True,
        show_semantics=True,
        theme="default",
        background="transparent",
        max_text_size=None,
        max_edges=None,
        visited_nodesets=(),
    )

    assert fragment.title == "root - detail.root"
    assert rendered[0][0] == "parent flow"
    assert rendered[0][1].startswith("flowchart TD")
    assert any(title == "first - detail.leaf_one" and text.startswith("flowchart LR") for title, text in rendered)
    assert sum(1 for title, text in rendered if title == "parent flow" and text.startswith("flowchart TD")) == 2

    root_titles = re.findall(r'<text class="review-title" x="([0-9.]+)" y="([0-9.]+)">([^<]+)</text>', fragment.svg_text)
    root_positions = {title: (float(x), float(y)) for x, y, title in root_titles}
    assert root_positions["parent flow"][0] < root_positions["first - detail.leaf_one"][0]
    assert root_positions["first - detail.leaf_one"][0] == root_positions["second - detail.mid"][0]
    assert root_positions["second - detail.mid"][0] == root_positions["third - detail.leaf_three"][0]
    assert root_positions["first - detail.leaf_one"][1] < root_positions["second - detail.mid"][1] < root_positions["third - detail.leaf_three"][1]

    assert 'data:image/svg+xml;base64,' not in fragment.svg_text
    assert "inner_a - detail.leaf_two" in fragment.svg_text
    assert "inner_b - detail.leaf_three" in fragment.svg_text
    mid_positions = _review_title_positions(fragment.svg_text)
    assert mid_positions["parent flow"][0] < mid_positions["inner_a - detail.leaf_two"][0]
    assert mid_positions["inner_a - detail.leaf_two"][0] == mid_positions["inner_b - detail.leaf_three"][0]
    assert mid_positions["inner_a - detail.leaf_two"][1] < mid_positions["inner_b - detail.leaf_three"][1]


def test_mermaid_shows_when_edges_and_health_findings() -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    {"name": "consumer", "type": "test.add", "requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("value.out")]},
                ],
                "edges": [{"from": "seed", "to": "consumer", "when": "flow.route == 'go'"}],
            },
        }
    )
    report = HealthReport(
        status="CONCERNS",
        warnings=(
            HealthFinding(
                rule_id="POLICY.TEST",
                severity="warning",
                object_type="node",
                object_id="consumer",
                failure_layer="policy",
                message="policy warning",
            ),
        ),
    )

    mermaid = export_mermaid(graph, health_report=report)
    assert "seed -->|flow.route == 'go'| consumer" in mermaid
    assert "%% finding warning POLICY.TEST node:consumer policy warning" in mermaid
    assert "class consumer healthWarning;" in mermaid

def test_health_report_status_pass_when_no_findings() -> None:
    registry = _registry()
    register_node(registry, "test.sink", SinkNode)
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": "start", "type": "test.start"},
                    {"name": "input", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                    {"name": "sink", "type": "test.sink", "requires": [REQ_SPEC("value.in")]},
                    {"name": "end", "type": "test.start"},
                ],
                "edges": _edge_chain("start", "input", "sink", "end"),
            }
        }
    )
    report = validate_graph_health(graph, registry=registry, purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "CONCERNS"
    assert all(warning.rule_id == "GRAPH.SMELL.DUPLICATE_LOGIC" for warning in report.warnings)

def test_health_report_status_fail_for_unknown_node() -> None:
    graph = parse_graph_config({"pipeline": {"nodes": [{"name": "missing", "type": "test.missing", "provides": [PROV_SPEC("x")]}]}})
    report = validate_graph_health(graph, registry=_registry(), purity_policy=PurityPolicy(max_source_lines=1000))
    assert report.status == "FAIL"
    assert report.errors[0].rule_id == "NODE.TYPE.UNKNOWN"
    assert report.errors[0].object_type == "node"

def test_target_package_structure_reexports_stable_api_and_schema_resources() -> None:
    import vibeflow.core as core
    import vibeflow.devtools as devtools
    import vibeflow.plugins as plugins

    assert core.NodeInfo is NodeInfo
    assert core.GraphCompiler is GraphCompiler
    assert devtools.export_mermaid is export_mermaid
    assert devtools.export_ascii_flowchart is export_ascii_flowchart
    assert devtools.render_mermaid_svg is render_mermaid_svg
    assert devtools.is_mermaid_svg_renderer_available is is_mermaid_svg_renderer_available
    assert plugins.PluginRegistry is PluginRegistry
    assert "NodeInfo" in STABLE_PUBLIC_API
    assert "render_mermaid_svg" in STABLE_PUBLIC_API
    assert "schema_text" in STABLE_PUBLIC_API

    for schema_name in ("config", "policy", "health_report", "node", "nodeset"):
        payload = json.loads(schema_text(schema_name))
        assert payload["$schema"].startswith("https://json-schema.org/")
        assert payload["title"].startswith("VibeFlow")

def test_cli_validate_json_reports_pass(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {"pipeline": _seed_add_pipeline()}
        ),
        encoding="utf-8",
    )
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["info"]["nodes"] == 4
    assert payload["info"]["effective_edges"] == [["start", "seed"], ["seed", "add"], ["add", "end"]]

def test_cli_validate_json_reports_bad_json_location(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text('{"pipeline": ', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 1
    assert payload["errors"][0]["source_location"]["column"] > 1

def test_cli_validate_text_error_includes_rule_file_line_and_column(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.json"
    config_path.write_text('{"pipeline": ', encoding="utf-8")
    code = cli_main(["validate", "--config", str(config_path)])
    output = capsys.readouterr().out
    assert code == 1
    assert "CONFIG.JSON" in output
    assert str(config_path) in output
    assert "line 1" in output
    assert "column" in output

def test_cli_inspect_config_outputs_effective_edges(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.json"
    config_path.write_text(
        json.dumps(
            {"pipeline": _seed_add_pipeline()}
        ),
        encoding="utf-8",
    )
    code = cli_main(["inspect-config", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["config"]["nodes"][0]["name"] == "start"
    assert payload["config"]["effective_edges"] == [
        {"from": "start", "to": "seed", "when": ""},
        {"from": "seed", "to": "add", "when": ""},
        {"from": "add", "to": "end", "when": ""},
    ]

def test_cli_inspect_node_with_module_reports_metadata_and_contract(tmp_path, capsys) -> None:
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(
        """
from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo

class DemoNode:
    NODE_INFO = NodeInfo(
        type_key="demo.node",
        display_name="Demo",
        category="demo",
        description="Demo node.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=(DataRequirement("demo.in", "exactly_one"),),
        provides=(DataProvider("demo.out", "demo.out"),),
        input_semantics={"demo.in": ("demo input",)},
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {"demo.in": 5}, "params": {}},),
    )

    def run_pure(self, inputs, params):
        return {"demo.out": inputs["demo.in"]}
""".strip(),
        encoding="utf-8",
    )
    code = cli_main(["inspect-node", "--type", "demo.node", "--module", str(module_path)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["health"]["status"] == "PASS"
    assert payload["node"]["metadata"]["type_key"] == "demo.node"
    assert payload["node"]["contract"]["requires"] == [{"type": "demo.in", "cardinality": "exactly_one"}]
    assert payload["node"]["source"]["lines"] > 0

def test_cli_inspect_node_requires_module_boundary(capsys) -> None:
    code = cli_main(["inspect-node", "--type", "demo.node"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["health"]["status"] == "FAIL"
    assert payload["health"]["errors"][0]["rule_id"] == "NODE.INSPECT.MODULE_REQUIRED"
