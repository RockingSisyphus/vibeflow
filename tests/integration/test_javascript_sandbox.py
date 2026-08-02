from __future__ import annotations

from pathlib import Path

import pytest

from vibeflow.tooling.application.javascript_build import (
    ProjectBuildRequest,
    prepare_project_build,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = REPOSITORY_ROOT / "sandbox/javascript/integration"
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
    bindings = prepared.javascript_bindings
    assert bindings is not None
    assert tuple(call.path for call in bindings.calls) == tuple(
        (*block.path, node.id)
        for block in prepared.plan.blocks
        for node in block.nodes
    )
    assert set(bindings.base_libs.to_value()) == set(base_libs)
    assert set(bindings.capabilities.to_value()) == set(capabilities)
    assert bindings.import_policy.to_value() == prepared.import_policy
    assert "javascript_bindings" not in prepared.plan.to_dict()
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


@pytest.mark.parametrize(
    ("config_name", "expected_paths"),
    (
        (
            "nodeset.jsonc",
            (
                ("start",),
                ("arithmetic",),
                ("end",),
                ("arithmetic", "start"),
                ("arithmetic", "add"),
                ("arithmetic", "subtract"),
                ("arithmetic", "end"),
            ),
        ),
        (
            "loop.jsonc",
            (
                ("start",),
                ("loop",),
                ("end",),
                ("loop", "start"),
                ("loop", "increment"),
                ("loop", "end"),
            ),
        ),
        (
            "port_math.jsonc",
            (("receive",), ("calculate",), ("send",)),
        ),
    ),
)
def test_binding_shadow_paths_cover_composites_loops_and_io(
    tmp_path: Path,
    config_name: str,
    expected_paths: tuple[tuple[str, ...], ...],
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
    bindings = prepared.javascript_bindings
    assert bindings is not None
    assert tuple(call.path for call in bindings.calls) == expected_paths
    if config_name == "port_math.jsonc":
        receive = bindings.binding(("receive",))
        send = bindings.binding(("send",))
        assert receive.completion == "suspend"
        assert receive.executor == "event_loop"
        assert receive.capabilities[0].operations == ("receive",)
        assert send.completion == "immediate"
        assert send.executor == "current"
        assert send.capabilities[0].operations == ("send",)


def test_typescript_sandbox_toolchain_is_project_owned_and_locked() -> None:
    package = (PROJECT_ROOT / "package.json").read_text(encoding="utf-8")
    lock = (PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8")

    assert '"typescript": "7.0.2"' in package
    assert '"esbuild": "0.28.1"' in package
    assert '"lockfileVersion": 3' in lock
