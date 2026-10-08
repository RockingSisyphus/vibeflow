"""Standard workflow defaults belong to application composition."""
from copy import deepcopy

import pytest

from vibeflow.core.flow import GraphConfigError
from vibeflow.tooling.application.graph_defaults import with_workflow_rule_defaults
from vibeflow.tooling.project.graph_config import parse_graph_config


def graph_document():
    return {"pipeline": {"nodes": [{"id": "root", "type_used": "example.node", "display_name": "Call", "description": "An explicit call instance."}]},
            "nodesets": [
                {"type_key": "example.stage", "display_name": "Stage", "description": "An imported scope.",
                 "requires": [], "provides": [], "pipeline": {"nodes": [{"id": "child", "type_used": "example.node", "display_name": "Call", "description": "An explicit call instance."}]}},
                {"type_key": "example.planned", "display_name": "Planned", "description": "A planned scope.",
                 "requires": [], "provides": [], "status": "planned"}]}


def test_application_defaults_missing_root_imported_and_planned_scopes():
    document = graph_document()
    original = deepcopy(document)
    graph = parse_graph_config(document)
    assert graph.rulesets == ("vibeflow.workflow",)
    assert all(item.graph.rulesets == ("vibeflow.workflow",) for item in graph.nodesets.values())
    assert document == original


def test_application_preserves_explicit_empty_and_custom_selections():
    document = graph_document()
    document["rulesets"] = []
    document["nodesets"][0]["rulesets"] = ["example.review"]
    document["nodesets"][1]["rulesets"] = []
    graph = parse_graph_config(document)
    assert graph.rulesets == ()
    assert graph.nodesets["example.stage"].graph.rulesets == ("example.review",)
    assert graph.nodesets["example.planned"].graph.rulesets == ()


def test_defaults_recurse_only_through_known_definition_scopes():
    opaque = {"nodesets": [{"label": "ordinary user value"}]}
    document = {"pipeline": {"nodes": [{"id": "node", "type_used": "example.node", "params": opaque}],
                             "nodesets": [{"pipeline": {"nodesets": [{}]}}]}}
    original = deepcopy(document)
    configured = with_workflow_rule_defaults(document)
    nested = configured["pipeline"]["nodesets"][0]
    assert nested["rulesets"] == ("vibeflow.workflow",)
    assert nested["pipeline"]["nodesets"][0]["rulesets"] == ("vibeflow.workflow",)
    assert configured["pipeline"]["nodes"][0]["params"] == opaque
    assert "rulesets" not in configured["pipeline"]["nodes"][0]["params"]["nodesets"][0]
    assert document == original


@pytest.mark.parametrize("selection", [None, "example.review", ["example.review", "example.review"]])
@pytest.mark.parametrize("scope", ["root", "nodeset"])
def test_explicit_invalid_selections_reach_core_validation(selection, scope):
    document = graph_document()
    selected = document if scope == "root" else document["nodesets"][0]
    selected["rulesets"] = selection
    with pytest.raises(GraphConfigError, match="rulesets"):
        parse_graph_config(document)
