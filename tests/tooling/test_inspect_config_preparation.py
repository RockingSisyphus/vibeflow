"""Low-level configuration inspection consumes one parse and native plan."""

import json

from vibeflow.tooling.application.python.cli import config


def document(*, cycle=False):
    return {"rulesets":["vibeflow.workflow"], "pipeline":{
        "nodes":[{"id":name,"type_used":"audit." + name,"display_name":name,
            "description":"Planned terminal boundary.","status":"planned",
            "flow_kind":"terminal","requires":[],"provides":[]} for name in ("start","end")],
        "edges":[["start","end"], *([["end","start"]] if cycle else [])]}}


def test_unowned_inspection_reuses_one_prepared_graph(tmp_path, monkeypatch):
    path = tmp_path / "workflow.jsonc"
    path.write_text(json.dumps(document()), encoding="utf-8")
    counts = {"load":0,"parse":0,"compile":0}
    def counted(name, function):
        def call(*args, **kwargs):
            counts[name] += 1
            return function(*args, **kwargs)
        return call
    monkeypatch.setattr(config,"load_config_document",counted("load",config.load_config_document))
    monkeypatch.setattr(config,"parse_graph_config",counted("parse",config.parse_graph_config))
    monkeypatch.setattr(config.GraphCompiler,"compile_with_findings",counted("compile",config.GraphCompiler.compile_with_findings))
    payload, code = config.inspect_config_payload(path)
    assert code == 0
    assert payload["health"]["status"] == "CONCERNS"
    assert [item["code"] for item in payload["health"]["warnings"]] == ["GRAPH.PLANNED.NODE","GRAPH.PLANNED.NODE"]
    assert payload["config"]["effective_edges"] == [{"from":"start","to":"end","when":""}]
    assert counts == {"load":1,"parse":1,"compile":1}


def test_unowned_inspection_keeps_native_failure_details(tmp_path):
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
    path = tmp_path / "workflow.jsonc"
    path.write_text('{"pipeline":', encoding="utf-8")
    expected = config.validate_config_path(path)
    payload, code = config.inspect_config_payload(path)
    assert code == 1
    assert payload == {"health":expected.to_dict()}
    assert payload["health"]["errors"][0]["source_location"]["path"] == str(path)
