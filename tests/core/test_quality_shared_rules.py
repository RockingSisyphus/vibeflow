from __future__ import annotations

from tests.fixtures.support.project_rules import evaluate_standard_project_quality

from dataclasses import replace

import pytest

from vibeflow.targets.shared.quality_support import (
    FileQuality,
    FunctionQuality,
    SourceQualityFacts,
    QualityPolicy,
    QualityThresholds,
)
from vibeflow.targets.shared.quality_support.implementation import (
    ImplementationLimits,
    ImplementationMetrics,
    analyze_call_graph,
)

from vibeflow.targets.shared.rule_support.implementation import check_node_implementation, check_base_lib_implementation, check_base_lib_dependency_chain


def _file(**changes) -> FileQuality:
    base = FileQuality(
        path="src/sample.py", module="src.sample", lines=1, bytes=1,
        function_count=0, class_count=0, public_api_count=0,
        branch_count=0, max_nesting_depth=0, imports=(), functions=(),
    )
    return replace(base, **changes)


@pytest.mark.parametrize(
    ("change", "value", "rule", "severity"),
    [
        ("lines", 450, "QUALITY.FILE.WARN_LINES", "warning"),
        ("lines", 500, "QUALITY.FILE.WARN_LINES", "warning"),
        ("lines", 501, "QUALITY.FILE.MAX_LINES", "error"),
        ("bytes", 60000, None, None),
        ("bytes", 60001, "QUALITY.FILE.MAX_BYTES", "error"),
        ("function_count", 41, "QUALITY.FILE.TOO_MANY_FUNCTIONS", "warning"),
        ("class_count", 21, "QUALITY.FILE.TOO_MANY_CLASSES", "warning"),
        ("public_api_count", 31, "QUALITY.FILE.TOO_WIDE_PUBLIC_API", "warning"),
        ("branch_count", 151, "QUALITY.FILE.TOO_MANY_BRANCHES", "warning"),
    ],
)
def test_shared_file_thresholds(change, value, rule, severity) -> None:
    report = evaluate_standard_project_quality(SourceQualityFacts(root="/tmp/quality", files=(_file(**{change: value}),)))
    matching = [item for item in report.findings if item.rule_id == rule] if rule else []
    if rule is None:
        assert report.status == "PASS"
    else:
        assert len(matching) == 1
        assert matching[0].severity == severity
        assert matching[0].source_location == {"path": "/tmp/quality/src/sample.py", "line": 1}
        assert matching[0].details == {
            "actual": value,
            "limit": getattr(QualityThresholds(), {
                "lines": "warn_file_lines" if severity == "warning" else "max_file_lines",
                "bytes": "max_file_bytes",
                "function_count": "max_functions_per_file",
                "class_count": "max_classes_per_file",
                "public_api_count": "max_public_api_per_file",
                "branch_count": "max_file_branches",
            }[change]),
        }
        assert report.status == ("FAIL" if severity == "error" else "CONCERNS")


@pytest.mark.parametrize(
    ("change", "value", "rule"),
    [
        ("lines", 81, "QUALITY.FUNCTION.MAX_LINES"),
        ("branches", 13, "QUALITY.FUNCTION.TOO_MANY_BRANCHES"),
        ("max_nesting_depth", 5, "QUALITY.FUNCTION.TOO_DEEP_NESTING"),
        ("param_count", 7, "QUALITY.FUNCTION.TOO_MANY_PARAMS"),
    ],
)
def test_shared_function_thresholds(change, value, rule) -> None:
    function = FunctionQuality("run", 7, 8, 2, 0, 0, 0, "fingerprint")
    file = _file(functions=(replace(function, **{change: value}),))
    report = evaluate_standard_project_quality(SourceQualityFacts(root="/tmp/quality", files=(file,)))
    finding = next(item for item in report.findings if item.rule_id == rule)
    assert finding.severity == "warning"
    assert finding.source_location["line"] == 7
    assert finding.details["actual"] == value
    assert report.status == "CONCERNS"


@pytest.mark.parametrize(
    ("length", "expected"),
    [(3, ()), (4, (("NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP", "warning"),)), (5, (("NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP", "error"),))],
)
def test_shared_node_chain_boundaries(length, expected) -> None:
    calls = {f"f{index}": (f"f{index + 1}",) if index + 1 < length else () for index in range(length)}
    chain = analyze_call_graph(calls, entry="f0")
    findings = check_node_implementation(ImplementationMetrics(call_chain=chain), ImplementationLimits())
    assert tuple((item.rule_id, item.severity) for item in findings) == expected
    if findings:
        assert findings[0].details["path"] == [f"f{index}" for index in range(length)]


@pytest.mark.parametrize("calls", [{"run": ("run",)}, {"run": ("helper",), "helper": ("run",)}])
def test_private_recursion_does_not_create_a_default_error(calls) -> None:
    findings = check_node_implementation(
        ImplementationMetrics(call_chain=analyze_call_graph(calls, entry="run")),
        ImplementationLimits(),
    )
    assert not any(item.rule_id == "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN" for item in findings)


@pytest.mark.parametrize(
    ("field", "metric"),
    [
        ("max_functions", "function_count"),
        ("max_branches", "branch_count"),
        ("max_nesting_depth", "max_nesting_depth"),
        ("max_params", "param_count"),
        ("max_contract_keys", "contract_key_count"),
    ],
)
def test_optional_node_complexity_limits(field, metric) -> None:
    metrics = ImplementationMetrics(**{metric: 2})
    assert not check_node_implementation(metrics, ImplementationLimits())
    assert not check_node_implementation(metrics, replace(ImplementationLimits(), **{field: 2}))
    findings = check_node_implementation(metrics, replace(ImplementationLimits(), **{field: 1}))
    assert [(item.rule_id, item.severity) for item in findings] == [(f"NODE.MAINTAINABILITY.COMPLEXITY_{field.upper()}", "error")]
    assert findings[0].details[metric] == 2


def test_shared_base_lib_source_size_boundaries() -> None:
    limits = ImplementationLimits()
    assert {item.severity for item in check_base_lib_implementation(ImplementationMetrics(source_lines=500, source_bytes=60000), limits)} == {"warning"}
    findings = check_base_lib_implementation(ImplementationMetrics(source_lines=501, source_bytes=60001), limits)
    assert {item.rule_id for item in findings} == {"BASE_LIB.SOURCE.MAX_LINES", "BASE_LIB.SOURCE.MAX_BYTES"}


def test_shared_node_source_size_boundaries() -> None:
    limits = ImplementationLimits(warn_source_lines=None, warn_source_bytes=None)
    assert not check_node_implementation(
        ImplementationMetrics(source_lines=500, source_bytes=60000), limits,
    )
    findings = check_node_implementation(
        ImplementationMetrics(source_lines=501, source_bytes=60001), limits,
    )
    assert {(item.rule_id, item.severity) for item in findings} == {
        ("NODE.PURITY.SOURCE_TOO_LARGE", "error"),
        ("NODE.PURITY.SOURCE_BYTES_TOO_LARGE", "error"),
    }
    by_rule = {item.rule_id: item for item in findings}
    assert by_rule["NODE.PURITY.SOURCE_TOO_LARGE"].details == {"lines": 501, "limit": 500}
    assert by_rule["NODE.PURITY.SOURCE_BYTES_TOO_LARGE"].details == {"bytes": 60001, "limit": 60000}
    warning = check_node_implementation(ImplementationMetrics(source_lines=450), ImplementationLimits())
    assert [(item.rule_id, item.severity) for item in warning] == [("NODE.PURITY.SOURCE_NEAR_LIMIT", "warning")]


@pytest.mark.parametrize(
    ("length", "severity"),
    [(4, None), (5, "warning"), (6, "warning"), (7, "error")],
)
def test_shared_base_lib_dependency_chain_boundary(length, severity) -> None:
    graph = {"node": ("lib1",)}
    graph.update({
        f"lib{index}": (f"lib{index + 1}",) if index + 1 < length else ()
        for index in range(1, length)
    })
    chain = analyze_call_graph(graph, entry="node")
    finding = check_base_lib_dependency_chain(chain, ImplementationLimits())
    assert (finding.severity if finding else None) == severity
    if finding:
        assert finding.rule_id == "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"
        assert finding.details["longest_chain"] == list(chain.path)
