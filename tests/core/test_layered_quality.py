"""Contracts for the layered, user-project quality implementation."""

from __future__ import annotations
from vibeflow.tooling.application.python.project.source_files import collect_root_source_facts, DEFAULT_EXCLUDED_DIRS
from vibeflow.targets.shared.quality_support import QualityPolicy

from tests.fixtures.support.project_rules import evaluate_standard_project_quality

import ast
from pathlib import Path

from vibeflow.core.findings import Finding, HealthFinding
from vibeflow.targets.shared.quality_support import (
    SourceQualityFacts,
    QualityPolicy,
    QualityThresholds,
    WorkflowQualityRequest,
    validate_workflow_quality,
)
from vibeflow.targets.python.quality import PythonSource, analyze_python_source



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
    assert health.to_dict()["code"] == "TEST.HEALTH"
    assert quality.to_dict()["code"] == "QUALITY.SYNTAX.PYTHON"


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
    report = evaluate_standard_project_quality(
        SourceQualityFacts(root="/virtual", files=(source.file,)),
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


def test_python_target_extracts_ast_facts_without_selecting_effect_rules() -> None:
    result = analyze_python_source(
        PythonSource(
            module="sample",
            relative_path="sample.py",
            source_path="/virtual/sample.py",
            text="import requests\n\ndef run():\n    return requests.get('x')\n",
        ),
    )

    assert result.file.imports == ("requests",)
    assert result.findings == ()




def test_tooling_only_reads_files_and_adapts_target_facts(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text(
        "def wide(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    report = evaluate_standard_project_quality(collect_root_source_facts(tmp_path), QualityPolicy(thresholds=QualityThresholds(max_function_params=1)))

    assert [file.path for file in report.files] == ["module.py"]
    assert [finding.rule_id for finding in report.findings] == [
        "QUALITY.FUNCTION.TOO_MANY_PARAMS"
    ]






def test_shared_quality_support_does_not_import_concrete_targets_or_tooling() -> None:
    quality_root = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "vibeflow"
        / "targets"
        / "shared"
        / "quality_support"
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
            imported.startswith("vibeflow.targets.python")
            or imported.startswith("vibeflow.targets.javascript")
            or imported.startswith("vibeflow.tooling")
            for imported in imports
        ), (path, imports)
