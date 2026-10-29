from tests.fixtures.support.plugins import publish_native_fixture, append_resource
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from tests.fixtures.support.declarations import node_declaration, configured_declaration
from tests.fixtures.support.strict_support import *


CliExternalNode_DECLARATION = node_declaration(NodeDescriptor(rulesets=(), id='test.cli_external', display_name='CLI External', description='Exercises workspace registry metadata during CLI export.', version='0.1.0', flow_kind='process', external=True, contract=NodeContractDescriptor(), node_type="vibeflow.node"), NodeContractDescriptor(), rulesets=("vibeflow.process",))

class CliExternalNode:

    def run_pure(self, inputs, params):
        return {}


def _write_export_config(path: Path) -> None:
    from tests.fixtures.support.projects import register_root
    register_root(path.parent)
    path.write_text(
        json.dumps(
            {
                "pipeline": {
                    "nodes": [
                        _node_call("start", "test.start", "Starts the export fixture.", status="planned", flow_kind="terminal", requires=[], provides=[]),
                        _node_call("seed", "test.seed", "Produces value.in.", status="planned", flow_kind="process", requires=[], provides=[PROV_SPEC("value.in")]),
                        _node_call("add", "test.add", "Adds delta to value.in.", status="planned", flow_kind="process", requires=[REQ_SPEC("value.in")], provides=[PROV_SPEC("value.out")]),
                        _node_call("end", "test.out_end", "Consumes value.out at the end.", status="planned", flow_kind="terminal", requires=[REQ_SPEC("value.out")], provides=[]),
                    ],
                    "edges": [["start", "seed"], ["seed", "add"], ["add", "end"]],
                }
            }
        ),
        encoding="utf-8",
    )


def _write_nodeset_export_config(path: Path) -> None:
    _write_config_file(
        path,
        {
            "nodeset_types": [
                _nodeset_config(
                    "math.add_one",
                    requires=["value.in"],
                    provides=["value.out"],
                    exports=["value.out"],
                    pipeline=_input_add_pipeline(add={"id": "inner"}),
                )
            ],
            "pipeline": {
                "inputs": [INPUT_SPEC("value.in")],
                "nodes": [
                    _node_call("start", "test.start", "Starts the nodeset export fixture."),
                    _node_call("input", "test.value_input", "Reads value.in."),
                    _node_call("composite", "math.add_one", "Calls the add-one composite."),
                    _node_call("end", "test.out_end", "Consumes value.out at the end."),
                ],
                "edges": _edge_chain("start", "input", "composite", "end"),
            },
        },
    )

    publish_native_fixture(path, _registry())


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("export-mermaid", ("flowchart TD", "data: Value In", "id: seed")),
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
    (base_dir / "__init__.py").write_text("")
    (base_dir / "math_tools.py").write_text("def add(a,b):\n    return a+b\n")
    (tmp_path / "plugins/policy").mkdir(parents=True)
    (tmp_path / "plugins/policy/plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin\ndef runtime(context):\n    return object()\nplugin=Plugin(id="policy",runtime=runtime,display_name="Config Policy",description="Config-level policy declaration.")\n')
    config_path = tmp_path / "workflow.jsonc"
    config_path.write_text(json.dumps({"base_lib":{"modules":["base_lib.math_tools"]},
        "plugins":[{"source":{"kind":"file","ref":"plugins/policy/plugin.py","export":"plugin"}},
            {"id":"future_policy","type":"runtime","status":"planned","display_name":"Future Policy", "description":"planned policy"}],
        "pipeline":_seed_only_pipeline()}))
    publish_native_fixture(config_path, _registry())
    append_resource(tmp_path, {"kind":"base_lib","id":"base_lib.math_tools","display_name":"Config Math Tools",
        "description":"Config-level math helper declaration.","implementations":[{"language":"python","targets":["python"],
        "source":{"kind":"file","ref":"base_lib/math_tools.py"}}]})
    code = cli_main(["export-mermaid", "--config", str(config_path)])
    output = capsys.readouterr().out

    assert code == 0
    assert "resource_base_lib" in output
    assert "Config Math Tools" in output
    assert "resource_plugins" in output
    assert "Config Policy" in output
    assert "desc: Config-level policy declaration." in output
    assert "future_policy" in output
    planned = re.search(r'(resource_plugins_\d+)@\{[^\n]*Future Policy', output)
    assert planned and f"class {planned[1]} plannedResource;" in output


def test_cli_export_mermaid_writes_output_and_expands_nodesets(tmp_path, capsys) -> None:
    config_path = tmp_path / "workflow.jsonc"
    output_path = tmp_path / "graph.mmd"
    _write_nodeset_export_config(config_path)

    code = cli_main(["export-mermaid", "--config", str(config_path), "--output", str(output_path), "--expand-nodesets"])

    assert capsys.readouterr().out == ""
    assert code == 0
    output = output_path.read_text(encoding="utf-8")
    assert "flowchart TD" in output
    assert 'type_key: math.add_one' in output
    assert "composite__inner" in output


def test_cli_export_mermaid_reports_config_errors_as_health_report(tmp_path, capsys) -> None:
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
    config_path = tmp_path / "bad.jsonc"
    config_path.write_text('{\n  "pipeline": {"nodes": []},\n  "bad": [1,]\n}', encoding="utf-8")

    code = cli_main(["export-mermaid", "--config", str(config_path)])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["errors"][0]["rule_id"] == "CONFIG.JSON"
    assert payload["errors"][0]["source_location"]["line"] == 3
