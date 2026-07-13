from tests.unit.strict_support import *

from vibeflow.rendering.architecture_document import (
    ARCHITECTURE_DOCUMENT_HEADER,
    build_architecture_document,
    render_architecture_document,
)
from vibeflow.rendering.review_model import graph_root_ids


def _architecture_graph(tmp_path):
    app_root = tmp_path / "app"
    library_root = tmp_path / "library"
    unused_root = tmp_path / "unused"
    for root in (app_root, library_root, unused_root):
        root.mkdir(parents=True)
    return parse_graph_config(
        {
            "nodesets": [
                {
                    "type_key": "design.with_body",
                    "display_name": "Planned design",
                    "description": "A planned design with inspectable internals.",
                    "status": "planned",
                    "planned_behavior": "transparent",
                    "requires": [],
                    "provides": [],
                    "pipeline": {
                        "nodes": [
                            _node_call("planned_step", "test.add", "Shows the intended implementation."),
                        ]
                    },
                    "__vibeflow_root_id__": "app",
                    "__vibeflow_root_path__": str(app_root),
                    "__vibeflow_source_path__": str(app_root / "nodesets" / "design.jsonc"),
                },
                {
                    "type_key": "design.empty",
                    "display_name": "Empty design",
                    "description": "A planned design without a body.",
                    "status": "planned",
                    "requires": [],
                    "provides": [],
                    "__vibeflow_root_id__": "app",
                    "__vibeflow_root_path__": str(app_root),
                    "__vibeflow_source_path__": str(app_root / "nodesets" / "empty.jsonc"),
                },
                {
                    "type_key": "loop.body",
                    "display_name": "Loop body",
                    "description": "One loop iteration.",
                    "requires": [],
                    "provides": [PROV_SPEC("loop.iterations")],
                    "pipeline": {"nodes": [_node_call("body_step", "test.start", "Runs one iteration.")]},
                    "__vibeflow_root_id__": "library",
                    "__vibeflow_root_path__": str(library_root),
                    "__vibeflow_source_path__": str(library_root / "nodesets" / "loop.jsonc"),
                },
                {
                    "type_key": "unused.flow",
                    "display_name": "Unused flow",
                    "description": "Loaded for review but not called.",
                    "requires": [],
                    "provides": [],
                    "pipeline": {"nodes": [_node_call("unused_step", "test.start", "Unused body.")]},
                    "__vibeflow_root_id__": "unused",
                    "__vibeflow_root_path__": str(unused_root),
                    "__vibeflow_source_path__": str(unused_root / "nodesets" / "unused.jsonc"),
                },
            ],
            "pipeline": {
                "nodes": [
                    _node_call("start", "test.start", "Starts the workflow."),
                    _node_call(
                        "loop",
                        "vibeflow.loop.while",
                        "Repeats the library body.",
                        provides=[PROV_SPEC("loop.iterations")],
                        loop={
                            "body": "loop.body",
                            "stop_after": 2,
                            "max_iterations": 3,
                            "outputs": [{"from": "loop.iterations", "as": "loop.iterations"}],
                        },
                    ),
                    _node_call("design", "design.with_body", "Calls the planned design."),
                    _node_call(
                        "design_repeat",
                        "design.with_body",
                        "Calls the same planned design with different local config.",
                        config={"review_stage": "repeat"},
                    ),
                    _node_call("end", "test.start", "Ends the workflow."),
                ],
                "edges": _edge_chain("start", "loop", "design", "design_repeat", "end"),
            },
        },
        project_root=app_root,
        root_id="app",
        root_path=app_root,
        source_path=app_root / "configs" / "main.jsonc",
    )


def test_architecture_document_is_deterministic_and_keeps_planned_and_unused_bodies(tmp_path) -> None:
    graph = _architecture_graph(tmp_path)
    resources = {
        "global_config": {"config": {"delta": 3}},
        "base_lib": {
            "modules": [
                {"id": "loop_lib", "module": "base_lib.loop", "status": "implemented", "root_id": "library"},
                {"id": "unused_lib", "module": "base_lib.unused", "status": "implemented", "root_id": "unused"},
            ]
        },
        "plugins": [],
    }
    first = render_architecture_document(graph, registry=_registry(), resources=resources)
    second = render_architecture_document(graph, registry=_registry(), resources=resources)
    payload = build_architecture_document(graph, registry=_registry(), resources=resources)

    assert first == second
    assert first.startswith(ARCHITECTURE_DOCUMENT_HEADER + "{")
    assert str(tmp_path) not in first
    assert '"format"' not in first
    assert '"format_version"' not in first
    assert '"generated"' not in first
    assert '"executable"' not in first
    assert list(payload) == ["workflow", "nodesets", "node_types", "resources"]
    assert payload["workflow"]["source"] == {"root_id": "app", "path": "configs/main.jsonc"}
    assert payload["nodesets"]["design.with_body"]["body"]["nodes"][0]["id"] == "planned_step"
    assert payload["nodesets"]["design.empty"]["body"] is None
    assert payload["nodesets"]["unused.flow"]["reachable_from_workflow"] is False
    assert payload["workflow"]["nodes"][1]["invokes"] == {
        "kind": "loop_body",
        "target": "loop.body",
        "target_status": "implemented",
    }
    assert payload["workflow"]["nodes"][1]["loop"]["stop_after"] == 2
    design_calls = [
        node
        for node in payload["workflow"]["nodes"]
        if node["invokes"] and node["invokes"]["target"] == "design.with_body"
    ]
    assert [node["id"] for node in design_calls] == ["design", "design_repeat"]
    assert design_calls[1]["config"]["call"]["values"] == {"review_stage": "repeat"}
    assert list(payload["nodesets"]).count("design.with_body") == 1
    expanded = export_mermaid(graph, registry=_registry(), expand_nodesets=True)
    assert "planned_step" in expanded
    assert [item["module"] for item in payload["resources"]["base_lib"]] == ["base_lib.loop"]

    loop_type = payload["node_types"]["vibeflow.loop.while"]
    assert loop_type["info"]["display_name"] == "While Loop"
    assert loop_type["info"]["flow_kind"] == "predefined"
    assert loop_type["source"]["module"] == "vibeflow.graph_config.types"
    assert loop_type["source"]["class"] == "LoopSpec"
    assert loop_type["source"]["runtime"] == {
        "module": "vibeflow.runtime.loop_mixin",
        "class": "RuntimeLoopMixin",
        "entrypoints": ["_run_loop_node", "_run_loop_block_node", "_run_while_loop"],
    }
    assert loop_type["config"]["defaults"]["max_iterations"] == 1000
    assert loop_type["contract"]["params_schema"]["node_field"] == "loop"


def test_architecture_and_mermaid_share_edge_contract_roles_and_loop_resource_roots(tmp_path) -> None:
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    _node_call("seed", "test.seed", "Produces input.", provides=[PROV_SPEC("value.copy", "value.in")]),
                    _node_call("add", "test.add", "Consumes input.", requires=[REQ_SPEC("value.in")]),
                ],
                "edges": [{"from": "seed", "to": "add"}],
            }
        },
        project_root=tmp_path,
        root_id="app",
        root_path=tmp_path,
        source_path=tmp_path / "main.jsonc",
    )
    payload = build_architecture_document(graph, registry=_registry())
    edge = payload["workflow"]["edges"][0]

    assert edge["roles"] == ["mainline", "schedule", "transfer"]
    assert edge["transfers"] == [
        {
            "provider": {"key": "value.copy", "type": "value.in", "display_name": "Value Copy"},
            "requirement": {"type": "value.in", "cardinality": "exactly_one", "display_name": "Value In"},
        }
    ]
    assert "value.copy -> value.in" in export_mermaid(graph, registry=_registry())

    loop_graph = _architecture_graph(tmp_path / "roots")
    assert graph_root_ids(loop_graph) == frozenset({"app", "library"})
    mermaid = export_mermaid(
        loop_graph,
        registry=_registry(),
        resources={"base_lib": {"modules": [{"module": "base_lib.loop", "status": "implemented", "root_id": "library"}]}},
    )
    assert "base_lib.loop" in mermaid


def test_architecture_node_types_include_contract_schema_defaults_and_python_identity(tmp_path) -> None:
    graph = parse_graph_config(
        {"pipeline": _seed_add_pipeline(seed={"config": {"value": 4}}, add={"node_configs": {"child": {"delta": 2}}})},
        project_root=tmp_path,
        root_id="app",
        root_path=tmp_path,
        source_path=tmp_path / "main.jsonc",
    )
    payload = build_architecture_document(graph, registry=_registry())
    seed_type = payload["node_types"]["test.seed"]
    seed_call = next(item for item in payload["workflow"]["nodes"] if item["id"] == "seed")

    assert seed_type["info"]["description"] == "Produces a seed value."
    assert seed_type["contract"]["output_schema"] == {"value.in": {"type": "number"}}
    assert seed_type["config"] == {
        "defaults": {"value": 1},
        "schema": {"value": {"type": "number"}},
    }
    assert seed_type["source"]["module"] == "tests.unit.strict_support_runtime_nodes"
    assert seed_type["source"]["class"] == "SeedNode"
    assert "examples" not in seed_type["contract"]
    assert seed_call["config"]["call"]["values"] == {"value": 4}
