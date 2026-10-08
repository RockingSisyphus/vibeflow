"""Native planned-file findings requested by a selected workflow Rule."""
from vibeflow.core.findings import HealthFinding
from vibeflow.core.quality.workflow_rules.planned import behavior_details
from vibeflow.targets.python.project.planned_files import validate_python_stub_file


def python_stub_findings(request):
    warning = HealthFinding(rule_id="GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY", severity="warning",
        object_type=request.object_type, object_id=request.object_id, failure_layer="topology",
        message=f"{request.object_type} '{request.object_id}' uses planned python_stub for development tests only",
        suggested_fix_type="replace_stub_with_implementation", details=behavior_details(request.behavior))
    return (warning, *validate_python_stub_file(request.behavior, project_root=request.project_root,
        object_type=request.object_type, object_id=request.object_id))
