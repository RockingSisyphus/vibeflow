"""Actual coordination warnings and named locks survive analyzer retirement."""
import pytest
from vibeflow.targets.python.quality.workflow.validation import validate_graph_health
from vibeflow.tooling.project.graph_config import parse_graph_config


def _global_state_graph(*, lock_scope: str = ""):
    state_node = {
        "id": "state",
        "type_used": "sandbox.global_state_probe",
        "display_name": "Global State",
        "description": "Mutates audited process-local state.",
    }
    pipeline = {
        "nodes": [
            {
                "id": "start",
                "type_used": "test.start",
                "display_name": "Start",
                "description": "Starts the flow.",
            },
            state_node,
            {
                "id": "end",
                "type_used": "test.out_end",
                "display_name": "End",
                "description": "Ends after the state value is ready.",
            },
        ],
        "edges": [
            {"from": "start", "to": "state"},
            {"from": "state", "to": "end"},
        ],
        "outputs": [
            {
                "type": "value.out",
                "cardinality": "exactly_one",
                "display_name": "Value Output",
            }
        ],
    }
    if lock_scope == "root":
        pipeline["execution_lock"] = {"key": "test.callback.serial"}
    elif lock_scope == "node":
        state_node["execution_lock"] = {"key": "test.callback.serial"}
    return parse_graph_config({"pipeline": pipeline})



def _global_state_health(*, lock_scope: str = ""):
    from pathlib import Path
    from vibeflow.tooling.project.workspace_loader import load_project_workspace
    from vibeflow.tooling.application.python.project.declarations import declared_python_registry,collect_workflow_source_context
    from tests.fixtures.support.strict_support_runtime_nodes import OutEndNode,OutEndNode_DECLARATION,StartNode,StartNode_DECLARATION
    project=Path(__file__).resolve().parents[3]/"sandbox/python/integration/project"
    registry=declared_python_registry(load_project_workspace(project), project / "configs/pass_training_nodeset_object_flow.jsonc")
    registry.register(StartNode_DECLARATION,StartNode)
    registry.register(OutEndNode_DECLARATION,OutEndNode)
    graph=_global_state_graph(lock_scope=lock_scope)
    return validate_graph_health(graph,registry=registry,source_context=collect_workflow_source_context(registry,graph))



def test_unlocked_global_state_health_warning_is_advisory() -> None:
    health = _global_state_health()

    assert not health.errors
    warnings = [
        finding
        for finding in health.warnings
        if finding.rule_id
        == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
    ]
    assert len(warnings) == 1
    assert warnings[0].details["execution_lock"] is None



@pytest.mark.parametrize("lock_scope", ["root", "node"])
def test_effective_named_lock_suppresses_global_state_coordination_warning(
    lock_scope: str,
) -> None:
    health = _global_state_health(lock_scope=lock_scope)

    assert not health.errors
    assert not any(
        finding.rule_id
        == "GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED"
        for finding in health.warnings
    )
