"""Language-neutral result scope metadata for honest public reporting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CoverageItem:
    id: str
    label: str

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "label": self.label}


_COVERAGE = {
    "config_registration": CoverageItem("config_registration", "配置和登记关系"),
    "node_contract_shape": CoverageItem("node_contract_shape", "节点契约形状"),
    "data_reachability": CoverageItem("data_reachability", "数据可达性"),
    "control_flow": CoverageItem("control_flow", "控制流"),
    "effect_boundaries": CoverageItem("effect_boundaries", "副作用边界"),
    "project_structure": CoverageItem("project_structure", "项目结构"),
    "source_quality": CoverageItem("source_quality", "源码质量与依赖结构"),
    "target_build": CoverageItem("target_build", "目标代码构建"),
    "data_schema": CoverageItem("data_schema", "Data Schema 与生成类型"),
    "module_boundaries": CoverageItem("module_boundaries", "模块与 Target 边界"),
    "async_ownership": CoverageItem("async_ownership", "异步任务与 Promise 所有权"),
    "architecture_freshness": CoverageItem("architecture_freshness", "架构文档新鲜度"),
    "review_artifact": CoverageItem("review_artifact", "正式审核产物生成"),
    "workflow_started": CoverageItem("workflow_started", "工作流成功启动"),
    "execution_order": CoverageItem("execution_order", "节点按编译计划执行"),
    "declared_outputs": CoverageItem("declared_outputs", "声明的最终输出已经产生"),
    "structural_runtime": CoverageItem("structural_runtime", "执行中没有结构性错误"),
}

_NOT_CHECKED = (
    CoverageItem("business_correctness", "业务结果正确性"),
    CoverageItem("requirements_conformance", "项目需求符合性"),
    CoverageItem("external_semantics", "外部接口业务语义"),
    CoverageItem("domain_data_correctness", "领域数据正确性"),
)

_SCOPE_PREFIX = {
    "vibeflow_structure": "VIBEFLOW_STRUCTURE",
    "vibeflow_quality": "VIBEFLOW_QUALITY",
    "vibeflow_build": "VIBEFLOW_BUILD",
    "vibeflow_review_artifact": "VIBEFLOW_REVIEW_ARTIFACT",
    "vibeflow_workflow_execution": "VIBEFLOW_WORKFLOW_EXECUTION",
}

_SCOPE_TITLE = {
    "vibeflow_structure": "VibeFlow 结构检查",
    "vibeflow_quality": "VibeFlow 项目质量检查",
    "vibeflow_build": "VibeFlow 构建",
    "vibeflow_review_artifact": "VibeFlow 审核产物生成",
    "vibeflow_workflow_execution": "VibeFlow 工作流执行",
}

DEFAULT_CHECKS = {
    "vibeflow_structure": (
        "config_registration",
        "node_contract_shape",
        "data_reachability",
        "control_flow",
        "effect_boundaries",
        "project_structure",
    ),
    "vibeflow_quality": ("project_structure", "source_quality", "effect_boundaries"),
    "vibeflow_build": (
        "config_registration",
        "node_contract_shape",
        "data_reachability",
        "control_flow",
        "effect_boundaries",
        "data_schema",
        "module_boundaries",
        "async_ownership",
        "target_build",
    ),
    "vibeflow_review_artifact": (
        "config_registration",
        "node_contract_shape",
        "data_reachability",
        "control_flow",
        "effect_boundaries",
        "architecture_freshness",
        "review_artifact",
    ),
    "vibeflow_workflow_execution": (
        "workflow_started",
        "execution_order",
        "declared_outputs",
        "structural_runtime",
    ),
}


def result_scope_payload(
    validation_scope: str,
    status: str,
    *,
    checked_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Return additive public result metadata for one completed command."""

    if validation_scope not in _SCOPE_PREFIX:
        raise ValueError(f"unknown validation scope: {validation_scope}")
    normalized_status = str(status).upper()
    ids = tuple(
        DEFAULT_CHECKS[validation_scope] if checked_ids is None else checked_ids
    )
    unknown = tuple(item for item in ids if item not in _COVERAGE)
    if unknown:
        raise ValueError(f"unknown coverage ids: {', '.join(unknown)}")
    title = _SCOPE_TITLE[validation_scope]
    outcome = {
        "PASS": "通过",
        "CONCERNS": "完成，但存在关注项",
        "FAIL": "失败",
        "ERROR": "无法完成",
    }.get(normalized_status, normalized_status)
    return {
        "result_code": f"{_SCOPE_PREFIX[validation_scope]}_{normalized_status}",
        "validation_scope": validation_scope,
        "summary": f"{title}{outcome}",
        "checked": [_COVERAGE[item].to_dict() for item in ids],
        "not_checked": [item.to_dict() for item in _NOT_CHECKED],
    }


def add_result_scope(
    payload: Mapping[str, object],
    validation_scope: str,
    *,
    checked_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    result = dict(payload)
    if "summary" in result and not isinstance(result["summary"], str):
        result.setdefault("details_summary", result["summary"])
    result.update(
        result_scope_payload(
            validation_scope,
            str(payload.get("status", "ERROR")),
            checked_ids=checked_ids,
        )
    )
    return result


def format_result_scope(payload: Mapping[str, object]) -> str:
    """Render result scope without implying business validation."""

    result_code = str(payload.get("result_code", ""))
    lines = [f"{payload.get('summary', '')} ({result_code})"]
    lines.extend(("", "已检查："))
    lines.extend(
        f"- {item.get('label', '')}"
        for item in payload.get("checked", ())
        if isinstance(item, Mapping)
    )
    lines.extend(("", "未检查："))
    lines.extend(
        f"- {item.get('label', '')}"
        for item in payload.get("not_checked", ())
        if isinstance(item, Mapping)
    )
    return "\n".join(lines)


__all__ = [
    "CoverageItem",
    "DEFAULT_CHECKS",
    "add_result_scope",
    "format_result_scope",
    "result_scope_payload",
]
