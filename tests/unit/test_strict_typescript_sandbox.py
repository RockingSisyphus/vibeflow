from __future__ import annotations

from pathlib import Path

import pytest

from vibeflow.aot import ProjectBuildRequest, prepare_project_build


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = REPOSITORY_ROOT / "examples/typescript_sandbox"
PROJECT_ROOT = SANDBOX_ROOT / "project"
WORKSPACE_PATH = SANDBOX_ROOT / "vibeflow_config.jsonc"


@pytest.mark.parametrize(
    ("config_name", "base_libs", "capabilities"),
    [
        ("linear.jsonc", ("sandbox.math",), ()),
        ("optional_input.jsonc", ("sandbox.math",), ()),
        ("fanout_join.jsonc", ("sandbox.math",), ()),
        ("edge_roles.jsonc", ("sandbox.math",), ()),
        ("branch_join.jsonc", ("sandbox.math",), ()),
        ("nodeset.jsonc", ("sandbox.math",), ()),
        ("loop.jsonc", ("sandbox.math",), ()),
        ("loop_stop_when.jsonc", ("sandbox.math",), ()),
        ("loop_max_failure.jsonc", ("sandbox.math",), ()),
        ("nested_override.jsonc", ("sandbox.math",), ()),
        ("async_capability.jsonc", (), ("sandbox.storage",)),
        ("detached.jsonc", ("sandbox.math",), ("sandbox.audit",)),
        (
            "port_math.jsonc",
            ("sandbox.math",),
            ("vibeflow.port",),
        ),
        ("runtime_node_failure.jsonc", (), ()),
        ("runtime_output_failure.jsonc", (), ()),
    ],
)
def test_typescript_sandbox_positive_projects_prepare_real_aot_plans(
    tmp_path: Path,
    config_name: str,
    base_libs: tuple[str, ...],
    capabilities: tuple[str, ...],
) -> None:
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=WORKSPACE_PATH,
            config=PROJECT_ROOT / "configs" / config_name,
            out_dir=tmp_path / config_name,
            target="node",
            profile="single-esm",
        )
    )

    assert prepared.used_base_libs == base_libs
    assert prepared.used_capabilities == capabilities
    assert prepared.used_node_types
    assert prepared.payload["blocks"]
    for block in prepared.payload["blocks"]:
        assert all(
            isinstance(input_spec.get("required"), bool)
            for input_spec in block["inputs"]
        )


@pytest.mark.parametrize(
    "config_name",
    [
        "direct_node_import.jsonc",
        "undeclared_base_lib.jsonc",
        "dynamic_import.jsonc",
        "runtime_import.jsonc",
        "node_builtin_browser.jsonc",
    ],
)
def test_typescript_sandbox_negative_projects_prepare_for_import_audit(
    tmp_path: Path,
    config_name: str,
) -> None:
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=WORKSPACE_PATH,
            config=PROJECT_ROOT / "configs/negative" / config_name,
            out_dir=tmp_path / config_name,
            target="browser",
            profile="single-esm",
        )
    )

    assert prepared.used_node_types == (
        f"sandbox.invalid.{Path(config_name).stem}",
        "sandbox.terminal",
    )
    assert all(
        input_spec["required"] is True
        for input_spec in prepared.payload["inputs"]
    )


def test_typescript_sandbox_toolchain_is_project_owned_and_locked() -> None:
    package = (PROJECT_ROOT / "package.json").read_text(encoding="utf-8")
    lock = (PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8")

    assert '"typescript": "7.0.2"' in package
    assert '"esbuild": "0.28.1"' in package
    assert '"lockfileVersion": 3' in lock
