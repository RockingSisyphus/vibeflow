from __future__ import annotations

from pathlib import Path

import pytest

from vibeflow.aot.builder import AotBuildError, BuildRequest, build_aot
from vibeflow.aot.emitter import emit_workflow_module
from vibeflow.aot.model import AotPlanError


def _plan(schema: object) -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "schema-fail-closed",
        "schemas": {"value.in": schema},
        "inputs": [
            {
                "key": "value.in",
                "type": "value.in",
                "required": True,
            }
        ],
        "outputs": [],
        "nodes": [],
        "routes": [],
        "order": [],
        "entries": [],
    }


def test_low_level_builder_rejects_unsupported_schema_before_toolchain(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(AotBuildError) as captured:
        build_aot(
            BuildRequest(
                plan=_plan(
                    {
                        "type": "number",
                        "not": {"const": 3},
                    }
                ),
                project_root=project,
                package_root=project,
                out_dir=tmp_path / "dist",
                target="node",
                profile="single-esm",
            )
        )

    assert captured.value.code == "VF_AOT_SCHEMA_UNSUPPORTED"
    assert "not" in str(captured.value)


def test_low_level_builder_rejects_lossy_integer_params_before_toolchain(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    plan = _plan({"type": "integer"})
    plan["nodes"] = [
        {
            "id": "value",
            "type_used": "example.value",
            "params": {"value": 9_007_199_254_740_992},
            "requirements": [],
            "providers": [],
            "is_terminal": True,
            "implementation": {
                "module": "./value.js",
                "export": "run",
                "language": "javascript",
            },
        }
    ]
    plan["order"] = ["value"]
    plan["entries"] = ["value"]

    with pytest.raises(AotBuildError) as captured:
        build_aot(
            BuildRequest(
                plan=plan,
                project_root=project,
                package_root=project,
                out_dir=tmp_path / "dist",
                target="node",
                profile="single-esm",
            )
        )

    assert captured.value.code == "VF_AOT_NUMBER_RANGE"
    assert "JavaScript's lossless range" in str(captured.value)


def test_low_level_builder_rejects_lossy_integer_schema_literal(
    tmp_path: Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()

    with pytest.raises(AotBuildError) as captured:
        build_aot(
            BuildRequest(
                plan=_plan(
                    {
                        "type": "integer",
                        "const": 9_007_199_254_740_992,
                    }
                ),
                project_root=project,
                package_root=project,
                out_dir=tmp_path / "dist",
                target="node",
                profile="single-esm",
            )
        )

    assert captured.value.code == "VF_AOT_NUMBER_RANGE"


def test_direct_emitter_rejects_lossy_integer_without_builder() -> None:
    plan = _plan(
        {
            "type": "integer",
            "const": 9_007_199_254_740_992,
        }
    )

    with pytest.raises(AotPlanError) as captured:
        emit_workflow_module(plan)

    assert captured.value.code == "VF_AOT_NUMBER_RANGE"
