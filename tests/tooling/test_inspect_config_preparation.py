"""Low-level configuration inspection consumes one parse and native plan."""

import json

from vibeflow.tooling.application.python.cli import config


def document(*, cycle=False):
    return {"rulesets":["vibeflow.workflow"], "pipeline":{
        "nodes":[{"id":name,"definition_id":"audit." + name,"display_name":name,
            "description":"Planned terminal boundary.","status":"planned",
            "flow_kind":"terminal","requires":[],"provides":[]} for name in ("start","end")],
        "edges":[["start","end"], *([["end","start"]] if cycle else [])]}}


def test_registered_inspection_reuses_one_prepared_graph(tmp_path, monkeypatch):
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
    path = tmp_path / "workflow.jsonc"
    path.write_text(json.dumps(document()), encoding="utf-8")
    counts = {"parse":0,"compile":0}
    def counted(name, function):
        def call(*args, **kwargs):
            counts[name] += 1
            return function(*args, **kwargs)
        return call
    from vibeflow.tooling.project import graph_config
    monkeypatch.setattr(graph_config,"parse_graph_config",counted("parse",graph_config.parse_graph_config))
    monkeypatch.setattr(config.GraphCompiler,"compile_with_findings",counted("compile",config.GraphCompiler.compile_with_findings))
    payload, code = config.inspect_config_payload(path)
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    assert [item["code"] for item in payload["health"]["warnings"]] == ["GRAPH.PLANNED.NODE","GRAPH.PLANNED.NODE"]
    assert payload["config"]["effective_edges"] == [{"from":"start","to":"end","when":""}]
    assert counts == {"parse":1,"compile":1}


def test_registered_inspection_keeps_native_failure_details(tmp_path):
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
    path = tmp_path / "workflow.jsonc"
    path.write_text(json.dumps(document(cycle=True)), encoding="utf-8")
    expected = config.validate_config_path(path)
    payload, code = config.inspect_config_payload(path)
    assert code == 1
    assert payload == {"health":expected.to_dict()}
    error, = payload["health"]["errors"]
    assert error["rule_id"] == "GRAPH.CYCLE.FORBIDDEN"
    assert error["severity"] == "error"
    assert error["details"]["members"] == ["end","start"]


def test_inspection_retains_config_parse_failure(tmp_path):
    from tests.fixtures.support.projects import register_root
    register_root(tmp_path)
    path = tmp_path / "workflow.jsonc"
    path.write_text('{"pipeline":', encoding="utf-8")
    expected = config.validate_config_path(path)
    payload, code = config.inspect_config_payload(path)
    assert code == 1
    assert payload == {"health":expected.to_dict()}
    assert payload["health"]["errors"][0]["source_location"]["path"] == str(path)
