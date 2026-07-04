from tests.unit.strict_support import *


def _write_export_config(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        {"name": "start", "type": "test.start"},
                        {"name": "seed", "type": "test.seed", "provides": [PROV_SPEC("value.in")]},
                        {
                            "name": "add",
                            "type": "test.add",
                            "requires": [REQ_SPEC("value.in")],
                            "provides": [PROV_SPEC("value.out")],
                        },
                        {"name": "end", "type": "test.out_end", "requires": [REQ_SPEC("value.out")]},
                    ],
                    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]],
                }
            }
        ),
        encoding="utf-8",
    )


def _write_nodeset_export_config(path: Path) -> None:
    path.write_text(
        json.dumps(
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
        ),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("export-mermaid", ("flowchart TD", "seed --> add", "provides: value.in")),
        ("export-ascii", ("TOPOLOGY FLOWCHART", "seed ----> add", "provides=value.in")),
    ],
)
def test_cli_export_text_formats_read_jsonc(tmp_path, capsys, command, expected) -> None:
    config_path = tmp_path / "workflow.jsonc"
    _write_export_config(config_path)

    code = cli_main([command, "--config", str(config_path)])
    output = capsys.readouterr().out

    assert code == 0
    for item in expected:
        assert item in output


def test_cli_export_mermaid_includes_declared_resources(tmp_path, capsys) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    (base_dir / "math_tools.py").write_text(
        """
from vibeflow import BaseLibInfo

BASE_LIB_INFO = BaseLibInfo("base_lib.math_tools", "Math Tools", "math", "Pure arithmetic helpers.", "0.1.0")
""".strip(),
        encoding="utf-8",
    )
    plugin_path = tmp_path / "policy_plugin.py"
    plugin_path.write_text(
        """
from vibeflow import PluginInfo

PLUGIN_INFO = PluginInfo("policy", "policy", "Policy", "policy", "Policy extension.", "0.1.0")

class Plugin:
    name = "policy"
""".strip(),
        encoding="utf-8",
    )
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(
        json.dumps(
            {
                "base_lib": {"paths": ["base_lib"], "modules": ["base_lib.math_tools"]},
                "plugins": [
                    {"module": str(plugin_path), "type": "policy"},
                    {"name": "future_policy", "type": "policy", "status": "planned", "description": "planned policy"},
                ],
                "pipeline": _seed_only_pipeline(),
            }
        ),
        encoding="utf-8",
    )

    code = cli_main(["export-mermaid", "--config", str(config_path)])
    output = capsys.readouterr().out

    assert code == 0
    assert "resource_base_lib" in output
    assert "Math Tools" in output
    assert "resource_plugins" in output
    assert "future_policy" in output


def test_cli_export_svg_reads_jsonc(tmp_path, capsys) -> None:
    if not is_mermaid_svg_renderer_available():
        pytest.skip("Mermaid SVG renderer is not installed")
    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.svg"
    _write_export_config(config_path)

    code = cli_main(["export-svg", "--config", str(config_path), "--output", str(output_path)])

    assert code == 0
    assert "<svg" in output_path.read_text(encoding="utf-8")


def test_cli_export_svg_expand_nodesets_forces_review_columns_layout(tmp_path, monkeypatch) -> None:
    import vibeflow.mermaid_render as mermaid_render_module
    import vibeflow.mermaid_review_svg as review_svg_module

    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.svg"
    _write_nodeset_export_config(config_path)
    calls: list[dict[str, object]] = []

    def fake_review_columns_svg(graph, compiled, output, **kwargs):
        calls.append(kwargs)
        Path(output).write_text('<svg aria-roledescription="flowchart-review-columns">review</svg>', encoding="utf-8")

    def fail_default_svg(*args, **kwargs):
        raise AssertionError("expanded SVG must use review-columns composer")

    monkeypatch.setattr(review_svg_module, "render_review_columns_svg", fake_review_columns_svg)
    monkeypatch.setattr(mermaid_render_module, "render_mermaid_svg", fail_default_svg)

    code = cli_main(
        [
            "export-svg",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--expand-nodesets",
            "--mermaid-layout",
            "default",
        ]
    )

    assert code == 0
    assert calls and calls[0]["expand_nodesets"] is True
    assert "flowchart-review-columns" in output_path.read_text(encoding="utf-8")


def test_cli_export_svg_collapsed_default_uses_default_renderer(tmp_path, monkeypatch) -> None:
    import vibeflow.mermaid_render as mermaid_render_module
    import vibeflow.mermaid_review_svg as review_svg_module

    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.svg"
    _write_export_config(config_path)
    calls: list[str] = []

    def fail_review_columns_svg(*args, **kwargs):
        raise AssertionError("collapsed default SVG must not use review-columns composer")

    def fake_default_svg(mermaid_text, output, **kwargs):
        calls.append(mermaid_text)
        Path(output).write_text("<svg>default</svg>", encoding="utf-8")

    monkeypatch.setattr(review_svg_module, "render_review_columns_svg", fail_review_columns_svg)
    monkeypatch.setattr(mermaid_render_module, "render_mermaid_svg", fake_default_svg)

    code = cli_main(["export-svg", "--config", str(config_path), "--output", str(output_path), "--mermaid-layout", "default"])

    assert code == 0
    assert calls and calls[0].startswith("flowchart TD")
    assert output_path.read_text(encoding="utf-8") == "<svg>default</svg>"


def test_ascii_flowchart_distinguishes_standard_shapes() -> None:
    nodes = [
        ("start", "terminal"),
        ("input", "io"),
        ("prepare", "preparation"),
        ("call", "predefined"),
        ("route", "decision"),
        ("work", "process"),
        ("store", "data_store"),
        ("doc", "document"),
        ("end", "terminal"),
    ]
    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                    {"name": name, "status": "planned", "flow_kind": flow_kind}
                    for name, flow_kind in nodes
                ],
                "edges": [
                    {"from": source, "to": target, "when": "flow.route == 'ok'"}
                    if source == "route"
                    else [source, target]
                    for (source, _), (target, _) in zip(nodes, nodes[1:])
                ],
            }
        }
    )

    text = export_ascii_flowchart(graph)

    for marker in ("● START", "⇄ I/O", "INIT", "CALL", "DECISION", "PROCESS", "▣ STORE", "DOC", "~~~~~~~~"):
        assert marker in text
    assert "Node contracts:" in text


def test_cli_export_mermaid_writes_output_and_expands_nodesets(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.mmd"
    _write_nodeset_export_config(config_path)

    code = cli_main(["export-mermaid", "--config", str(config_path), "--output", str(output_path), "--expand-nodesets"])

    assert capsys.readouterr().out == ""
    assert code == 0
    output = output_path.read_text(encoding="utf-8")
    assert "flowchart TD" in output
    assert 'subgraph composite__expanded["math.add_one"]' in output
    assert "composite__inner" in output


def test_cli_export_mermaid_reports_config_errors_as_health_report(tmp_path, capsys) -> None:
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")

    code = cli_main(["export-mermaid", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 3
