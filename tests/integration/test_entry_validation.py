"""Real SDK/CLI checks cannot hide orphan calls behind named entry projection."""
import json

import pytest

from vibeflow.tooling.application.cli import main


SOURCES = {
    "python": '''from vibeflow.targets.python.sdk import Plugin,node
@node(node_type='vibeflow.node', id="boundary",flow_kind="terminal",contract={},rulesets=["vibeflow.process"])
class Boundary:
    def run_pure(self,inputs,params):return {}
@node(node_type='vibeflow.node', id="work",contract={},rulesets=["vibeflow.process"])
class Work:
    def run_pure(self,inputs,params):return {}
''',
    "javascript": '''import {definePlugin,defineNode} from "@vibeflow/plugin";
export const boundary=defineNode({"node_type":"vibeflow.node",id:"boundary",flow_kind:"terminal",contract:{},rulesets:["vibeflow.process"],run(){return {};}});
export const work=defineNode({"node_type":"vibeflow.node",id:"work",contract:{},rulesets:["vibeflow.process"],run(){return {};}});
''',
}


@pytest.mark.parametrize("target", ["python", "javascript"])
@pytest.mark.parametrize("orphan_type", ["boundary", "work"])
def test_validate_and_build_reject_calls_outside_every_entry(tmp_path, capsys, target, orphan_type):
    if target == "python":
        from tests.targets.python.test_code_plugins import project
    else:
        from tests.targets.javascript.test_code_plugins import project
    workspace, config = project(tmp_path, SOURCES[target])
    data = json.loads(config.read_text())
    data["rulesets"] = ["vibeflow.workflow"]
    data["pipeline"] = {
        "nodes": [{"id": key, "definition_id": kind, "display_name": key, "description": key}
                  for key, kind in [("start", "boundary"), ("gui", "boundary"), ("core", "work"), ("end", "boundary")]],
        "edges": [["start", "core"], ["gui", "core"], ["core", "end"]],
        "entries": {"cli": {"start": "start"}, "gui": {"start": "gui"}},
    }
    config.write_text(json.dumps(data))
    args = ["--workspace", str(workspace.path), "--config", str(config)]
    assert main(["validate", *args, "--json"]) == 0, capsys.readouterr().out
    capsys.readouterr()
    data["pipeline"]["nodes"].append({"id": "orphan", "definition_id": orphan_type,
                                     "display_name": "Orphan", "description": "Not reachable from any entry"})
    config.write_text(json.dumps(data))
    for command, extra in [("validate", ["--json"]), ("build", ["--out-dir", str(tmp_path / "build")] +
                           (["--target", "node", "--profile", "single-esm"] if target == "javascript" else []))]:
        assert main([command, *args, *extra]) == 1
        report = json.loads(capsys.readouterr().out)
        if target == "python" and command == "build":
            assert report["result_code"] == "VIBEFLOW_BUILD_ERROR"
            report = json.loads(report["error"])
        diagnostics = report.get("diagnostics", report.get("errors", []))
        codes = {item.get("code", item.get("rule_id")) for item in diagnostics}
        assert {"GRAPH.FLOW.UNREACHABLE_FROM_START", "GRAPH.FLOW.ORPHAN_NODE"} <= codes, report
        assert not (tmp_path / "build").exists()
