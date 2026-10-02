"""Read Python Rule defaults without importing business implementations."""

from vibeflow.core.rules.builtin import project_quality_rule_defaults
from vibeflow.targets.python.quality.project_context import source_quality_policy
from vibeflow.tooling.application.python.project.effective_policy import resolve_effective_policy
from vibeflow.tooling.application.python.project.policy import resolve_workspace_effective_policy


def source_rule_defaults(document, *, workspace=None):
    resolved = (resolve_workspace_effective_policy(workspace.policy, workspace_path=workspace.path)
                if workspace else resolve_effective_policy(document.data, config_path=document.path))
    errors = [finding.message for finding in resolved.findings if finding.severity == "error"]
    if errors:
        raise ValueError("; ".join(errors))
    policy = source_quality_policy(resolved.effective_policy.to_purity_policy())
    return project_quality_rule_defaults(policy)
