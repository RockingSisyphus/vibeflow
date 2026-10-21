"""Declaration conflicts and lazy imports use the formal Python entrypoints."""
from tests.fixtures.support.plugins import resource as resource_ref, write_plugin

import json
import sys

import pytest

from tests.fixtures.support.rule_sandbox import create_rule_graph_sandbox
from vibeflow.tooling.application.cli import main


@pytest.fixture
def project(tmp_path):
    sandbox = create_rule_graph_sandbox(tmp_path, "python")
    yield sandbox
    sys.modules.pop("rule_graph_nodes", None)


def call(capsys, arguments):
    code = main(arguments)
    return code, json.loads(capsys.readouterr().out)


def test_another_roots_private_plugin_cannot_be_selected(project, capsys):
    config = project.read(project.config)
    config["plugins"].append({"root":"other-python", "source":{"kind":"file","ref":"plugins/private/plugin.py"}})
    project.write(project.config, config)
    code, payload = call(capsys,["validate",*project.common_arguments(),"--json"])
    assert code == 1, payload
    assert "root" in json.dumps(payload)
    assert not project.events()


def test_parameterized_import_call_rule_keeps_real_workflow_facts_at_lazy_binding(project, capsys):
    provider = project.project / "plugins/code_plugin/rules/provider.py"
    provider.write_text('''import json
from pathlib import Path

def check(context, inputs, params):
    call = context.require("call")
    proof = {"owner": call.owner, "call": call.node_id, "factor": call.params["factor"],
        "all_calls": [item.node_id for item in context.require("source_context").calls]}
    with Path(params["marker"]).open("a") as output:
        output.write(json.dumps(proof) + "\\n")
    return {"records": {"numbers": {"type_id": "example.numbers.v1", "value": [proof["factor"]]}}}
''')
    graph = project.read(project.graph_resource)
    graph["entrypoints"] = {"import": ["checker"], "static": [], "run": []}
    project.write(project.graph_resource, graph)
    descriptor = resource_ref(project.project, 'node', 'example.calculate')
    document = project.read(descriptor)
    document["contract"]["params_schema"] = {"factor": {"type": "integer"}}
    document["contract"]["params_defaults"] = {"factor": 2}
    project.write(descriptor, document)
    config = project.read(project.config)
    config["pipeline"]["nodes"][1]["config"] = {"factor": 5}
    project.write(project.config, config)
    business = project.root / "business-result.txt"
    source = project.project / "nodes/rule_graph_nodes.py"
    source.write_text("from pathlib import Path\n" + source.read_text().replace(
        '        return {"result": inputs["example.input"]["value"] * 2 + 1}',
        '        value = inputs["example.input"]["value"] * 2 + 1\n'
        f'        Path({str(business)!r}).write_text(str(value))\n'
        '        return {"result": value}'))
    code, payload = call(capsys, ["validate", *project.common_arguments(), "--json"])
    assert code == 0, payload
    assert not business.exists()
    project.marker.unlink()
    code, payload = call(capsys, ["run", *project.common_arguments(), "--input", str(project.root / "input.json"),
        "--run-root", str(project.root / "runs"), "--run-id", "actual"])
    assert code == 0, payload
    proofs = [item for item in project.events() if "factor" in item]
    assert proofs
    assert all(item == {"owner": "pipeline", "call": "calculate", "factor": 5,
        "all_calls": []} for item in proofs)
    assert business.read_text() == "7"
