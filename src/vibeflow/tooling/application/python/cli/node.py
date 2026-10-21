"""Inspect canonical Node declarations without importing their implementations."""
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.tooling.project.workspace_loader import load_project_workspace
from vibeflow.tooling.application.python.project.declarations import declared_python_registry, collect_node_source_context
from vibeflow.targets.python.quality.rule_adapter import execute_python_node_rules
from vibeflow.targets.python.project.policy import default_effective_policy
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document
from vibeflow.targets.python.project.check_session import python_check_scope
from vibeflow.tooling.application.python.reports import config_load_error_report


def inspect_node_payload(*, node_id, config_path, module_path=None, class_name=None):
    try:
        document = load_config_document(config_path)
        policy = default_effective_policy()
        workspace = load_project_workspace(config_path)
        registry = declared_python_registry(workspace, config_path)
        descriptor = registry.descriptor(node_id)
        path, symbol, _, _ = registry.source_locations[node_id]
        if module_path is not None and module_path.resolve() != path:
            raise ValueError(f"declared node '{node_id}' uses source {path}")
        if class_name is not None and class_name != symbol:
            raise ValueError(f"declared node '{node_id}' exports {symbol}")
        with python_check_scope(registry):
            sources = collect_node_source_context(registry,(node_id,))
            imports = execute_python_node_rules(registry,sources,phase="import",purity_policy=policy.to_purity_policy())
            result = execute_python_node_rules(registry,sources,purity_policy=policy.to_purity_policy())
        errors = tuple(item for item in (*imports.findings,*result.findings) if item.severity == "error")
        warnings = tuple(item for item in (*imports.findings,*result.findings) if item.severity in {"warning","info"})
        report = HealthReport(status="FAIL" if errors else "CONCERNS" if warnings else "PASS", errors=errors, warnings=warnings,
            info={"rule_executions":[item.to_dict() for item in result.executions]}, effective_policy=policy.to_dict())
        metrics = dict(result.node_metrics.get(node_id,{}))
        dependency = {"imported_modules":metrics.get("imported_base_lib_modules",()),
            "longest_chain_length":metrics.get("max_dependency_chain_length",0),"longest_chain":metrics.get("max_dependency_chain",()),"recursive_chains":()}
        return {"health":report.to_dict(),"base_lib_dependency_chain":dependency,"node": {**descriptor.to_dict(),"class_name":symbol,
            "effect_scope":result.effect_scopes[node_id], "metrics":metrics,
            "source":{"path":str(path)}}}, 1 if errors else 0
    except ConfigLoadError as exc:
        return {"health":config_load_error_report(exc, object_type="config", object_id=str(config_path)).to_dict()}, 1
    except (OSError,ImportError,AttributeError,TypeError,ValueError) as exc:
        report = HealthReport(status="ERROR", errors=(HealthFinding(rule_id="NODE.INSPECT.LOAD_ERROR", severity="error",
            object_type="node", object_id=node_id, failure_layer="source", message=str(exc)),))
        return {"health":report.to_dict()},1

__all__ = ["inspect_node_payload"]
