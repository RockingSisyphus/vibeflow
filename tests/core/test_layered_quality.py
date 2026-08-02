"""Contracts for the layered, user-project quality implementation."""

from __future__ import annotations

import ast
from pathlib import Path

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.core.quality import (
    ProjectQualityFacts,
    QualityPolicy,
    QualityThresholds,
    WorkflowQualityRequest,
    evaluate_project_quality,
    validate_workflow_quality,
)
from vibeflow.targets.javascript.quality import (
    JavascriptImplementationQualityFacts,
    JavascriptImportFact,
    validate_javascript_quality,
)
from vibeflow.targets.python.quality import PythonSource, analyze_python_source
from vibeflow.tooling.application.python.project.quality_scan import scan_code_quality


def test_health_and_source_quality_share_plain_finding_base() -> None:
    health = HealthFinding("TEST.HEALTH", "health", "warning")
    source_result = analyze_python_source(
        PythonSource(
            module="sample",
            relative_path="sample.py",
            source_path="/virtual/sample.py",
            text="def broken(:\n",
        )
    )
    quality = source_result.findings[0]

    assert isinstance(health, Finding)
    assert isinstance(quality, Finding)
    assert health.code == "TEST.HEALTH"
    assert quality.code == "QUALITY.SYNTAX.PYTHON"
    assert "code" not in health.to_dict()
    assert "code" not in quality.to_dict()


def test_core_quality_evaluates_only_target_extracted_facts() -> None:
    source = analyze_python_source(
        PythonSource(
            module="sample",
            relative_path="sample.py",
            source_path="/virtual/sample.py",
            text=(
                "def wide(a, b):\n"
                "    if a:\n"
                "        return b\n"
                "    return a\n"
            ),
        )
    )
    report = evaluate_project_quality(
        ProjectQualityFacts(root="/virtual", files=(source.file,)),
        QualityPolicy(
            thresholds=QualityThresholds(
                max_function_params=1,
                max_function_branches=0,
            )
        ),
    )

    assert report.status == "CONCERNS"
    assert {finding.rule_id for finding in report.findings} == {
        "QUALITY.FUNCTION.TOO_MANY_BRANCHES",
        "QUALITY.FUNCTION.TOO_MANY_PARAMS",
    }
    assert report.to_dict()["summary"]["files"] == 1


def test_workflow_quality_keeps_health_report_json_view() -> None:
    report = validate_workflow_quality(
        WorkflowQualityRequest(
            findings=(
                Finding(
                    code="TEST.WORKFLOW",
                    severity="error",
                    subject_type="node",
                    subject_id="node-a",
                    message="invalid",
                ),
            ),
            info={"workflow_id": "wf"},
        )
    )

    payload = report.to_dict()
    assert report.status == "FAIL"
    assert payload["errors"][0]["rule_id"] == "TEST.WORKFLOW"
    assert payload["errors"][0]["object_id"] == "node-a"
    assert payload["info"] == {"workflow_id": "wf"}


def test_python_target_owns_ast_and_side_effect_facts() -> None:
    result = analyze_python_source(
        PythonSource(
            module="sample",
            relative_path="sample.py",
            source_path="/virtual/sample.py",
            text="import requests\n\ndef run():\n    return requests.get('x')\n",
        ),
        check_side_effects=True,
    )

    assert result.file.imports == ("requests",)
    assert {finding.rule_id for finding in result.findings} == {
        "QUALITY.SIDE_EFFECT.CALL",
        "QUALITY.SIDE_EFFECT.IMPORT",
    }


def test_javascript_target_validates_completion_and_import_boundaries() -> None:
    findings = validate_javascript_quality(
        (
            JavascriptImplementationQualityFacts(
                implementation_id="math.add",
                kind="node",
                source_path="nodes/add.ts",
                target="browser",
                completion="immediate",
                declared_async=True,
                hidden_promise_work=True,
                imports=(
                    JavascriptImportFact(
                        specifier="./other-node",
                        destination_kind="node",
                        destination_id="math.other",
                    ),
                ),
            ),
        )
    )

    assert {finding.rule_id for finding in findings} == {
        "QUALITY.JAVASCRIPT.COMPLETION.IMMEDIATE_PROMISE",
        "QUALITY.JAVASCRIPT.IMPORT.BOUNDARY",
        "QUALITY.JAVASCRIPT.PROMISE.UNOWNED",
    }


def test_tooling_only_reads_files_and_adapts_target_facts(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "def wide(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(max_function_params=1),
    )

    assert [file.path for file in report.files] == ["module.py"]
    assert [finding.rule_id for finding in report.findings] == [
        "QUALITY.FUNCTION.TOO_MANY_PARAMS"
    ]


def test_core_quality_public_modules_do_not_import_targets_or_tooling() -> None:
    quality_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "vibeflow"
        / "core"
        / "quality"
    )
    for path in quality_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(
            imported.startswith("vibeflow.targets")
            or imported.startswith("vibeflow.tooling")
            for imported in imports
        ), (path, imports)
