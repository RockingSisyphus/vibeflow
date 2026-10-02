"""Declaration conflicts and lazy imports use the formal Python entrypoints."""

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


@pytest.mark.parametrize("kind", ["rule", "ruleset"])
def test_cross_root_resource_conflicts_are_formal_diagnostics_with_both_origins(project, capsys, kind):
    other = project.root / "other"
    resources = other / "resources"
    resources.mkdir(parents=True)
    original = project.project / ("bundle/rules/provider.jsonc" if kind == "rule" else "bundle/rulesets/graph.jsonc")
    document = project.read(original)
    document["description"] = "A conflicting declaration in another project root."
    conflict = resources / "conflict.jsonc"
    project.write(conflict, document)
    if kind == "rule":
        (other / "rules").mkdir()
        (other / "rules/provider.py").write_text((project.project / "rules/provider.py").read_text())
    project.write(other / "vibeflow_project.jsonc", {"project_target": "python", "descriptors": {kind + "s": ["resources"]}})
    workspace = project.read(project.workspace)
    workspace["roots"].append({"id": "other-python", "path": "other"})
    project.write(project.workspace, workspace)
    code, payload = call(capsys, ["validate", *project.common_arguments(), "--json"])
    assert code == 1, payload
    finding = next(item for item in payload["errors"] if item["code"] == "RULE.RESOURCE.CONFLICT")
    assert finding["details"]["resource_id"] == document["id"]
    assert finding["details"]["source"] == str(conflict)
    assert finding["details"]["previous_source"] == str(original)
    assert finding["source_location"] == {"path": str(conflict), "line": 1, "column": 1}
    assert not project.events()


def test_parameterized_import_call_rule_keeps_real_workflow_facts_at_lazy_binding(project, capsys):
    provider = project.project / "rules/provider.py"
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
    descriptor = project.project / "bundle/nodes/calculate.jsonc"
    document = project.read(descriptor)
    document["contract"]["params_schema"] = {"factor": {"type": "integer"}}
    document["contract"]["params_defaults"] = {"factor": 2}
    project.write(descriptor, document)
    config = project.read(project.config)
    config["pipeline"]["nodes"][1]["config"] = {"factor": 5}
    project.write(project.config, config)
    business = project.root / "business-result.txt"
    source = project.project / "rule_graph_nodes.py"
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
        "all_calls": ["start", "calculate", "end"]} for item in proofs)
    assert business.read_text() == "7"
