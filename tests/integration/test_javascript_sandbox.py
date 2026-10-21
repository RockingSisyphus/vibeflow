from __future__ import annotations

import os
import json
from pathlib import Path
import shutil

import pytest

from vibeflow.tooling.application.javascript.build import (
    ProjectBuildRequest,
    build_project_aot,
    prepare_project_build,
)
from vibeflow.targets.javascript.frontend.errors import AotBuildError, ProjectBuildError


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = REPOSITORY_ROOT / "sandbox/javascript/integration"
PROJECT_ROOT = SANDBOX_ROOT / "project"
WORKSPACE_PATH = SANDBOX_ROOT / "vibeflow_config.jsonc"


@pytest.fixture(scope="module")
def sandbox_project(tmp_path_factory) -> tuple[Path, Path]:
    toolchain = Path(os.environ.get("VIBEFLOW_TEST_TOOLCHAIN_ROOT", REPOSITORY_ROOT / "sandbox/javascript/minimal/project"))
    if not (toolchain / "node_modules/typescript").is_dir():
        pytest.skip("requires the pinned project-local TypeScript/esbuild toolchain")
    sandbox = tmp_path_factory.mktemp("javascript-sandbox") / "integration"
    shutil.copytree(SANDBOX_ROOT, sandbox, ignore=shutil.ignore_patterns("node_modules", "__pycache__", "*.pyc", ".artifacts"))
    project = sandbox / "project"
    (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    for specification in json.loads((project / "negative/symlinks.json").read_text(encoding="utf-8")):
        link = project / specification["path"]
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(project / specification["target"])
    return sandbox / "vibeflow_config.jsonc", project


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
    sandbox_project: tuple[Path, Path],
    config_name: str,
    base_libs: tuple[str, ...],
    capabilities: tuple[str, ...],
) -> None:
    workspace, project = sandbox_project
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=workspace,
            config=project / "configs" / config_name,
            out_dir=tmp_path / config_name,
            target="node",
            profile="single-esm",
        )
    )

    assert prepared.used_base_libs == base_libs
    assert prepared.used_capabilities == capabilities
    assert prepared.used_node_ids
    assert prepared.plan.blocks
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
    for block in prepared.plan.blocks:
        assert all(isinstance(input_spec.required, bool) for input_spec in block.inputs)


@pytest.mark.parametrize(
    ("config_name", "expected_code", "expected_line"),
    [
        ("direct_node_import.jsonc", "VF_IMPORT_NODE_TO_NODE", 1),
        ("undeclared_base_lib.jsonc", "VF_IMPORT_BASE_LIB", 1),
        ("dynamic_import.jsonc", "VF_IMPORT_DYNAMIC", 13),
        ("runtime_import.jsonc", "VF_IMPORT_OWNER", 1),
        ("symlink_import.jsonc", "VF_IMPORT_NODE_TO_NODE", 1),
    ],
)
def test_typescript_sandbox_selected_import_rules_reject_before_aot(
    tmp_path: Path,
    sandbox_project: tuple[Path, Path],
    config_name: str,
    expected_code: str,
    expected_line: int,
) -> None:
    workspace, project = sandbox_project
    output = tmp_path / config_name
    with pytest.raises(ProjectBuildError) as error:
        prepare_project_build(ProjectBuildRequest(
            workspace=workspace,
            config=project / "configs/negative" / config_name,
            out_dir=output,
            target="browser",
            profile="single-esm",
        ))
    finding = next(item for item in error.value.diagnostics if item["code"] == expected_code)
    assert finding["definition_id"] == ("vibeflow.import_side_effects" if expected_code == "VF_IMPORT_DYNAMIC" else "vibeflow.node_architecture")
    assert finding["source_location"]["path"] == str(project / "negative/nodes" / (Path(config_name).stem + ".ts"))
    assert finding["source_location"]["line"] == expected_line
    assert finding["details"]["source_owner"]["id"] == f"sandbox.invalid.{Path(config_name).stem}"
    if config_name == "symlink_import.jsonc":
        assert "VF_IMPORT_OWNER" not in {item["code"] for item in error.value.diagnostics}
    assert not output.exists()


@pytest.mark.parametrize(
    "config_name",
    ["node_builtin_browser.jsonc", "indirect_node_builtin.jsonc"],
)
def test_platform_module_failures_remain_native_when_rules_are_unselected(
    tmp_path: Path,
    sandbox_project: tuple[Path, Path],
    config_name: str,
) -> None:
    workspace, project = sandbox_project
    request = ProjectBuildRequest(
        workspace=workspace,
        config=project / "configs/negative" / config_name,
        out_dir=tmp_path / config_name,
        target="browser",
        profile="single-esm",
    )
    with pytest.raises(ProjectBuildError) as governed:
        prepare_project_build(request)
    assert any(item["definition_id"] in {"vibeflow.no_side_effects", "vibeflow.import_side_effects"}
               for item in governed.value.diagnostics)
    plugin = project / "nodes/code_plugin_declarations.ts"
    original = plugin.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    type_key = f"sandbox.invalid.{Path(config_name).stem}"
    index = next(index for index, line in enumerate(lines) if f'"id": "{type_key}"' in line)
    import re
    lines[index] = re.sub(r'"rulesets": \[[^\]]*\]', '"rulesets": []', lines[index])
    plugin.write_text("".join(lines), encoding="utf-8")
    try:
        prepared = prepare_project_build(request)
        assert prepared.used_node_ids == (f"sandbox.invalid.{Path(config_name).stem}", "sandbox.terminal")
        with pytest.raises(AotBuildError) as platform:
            build_project_aot(request)
        assert platform.value.code == "VF_ESBUILD"
        assert any(item["code"] == "ESBUILD" and "node:fs" in item["message"] for item in platform.value.diagnostics)
    finally:
        plugin.write_text(original, encoding="utf-8")


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
            (("receive_start",), ("receive",), ("calculate",), ("send",), ("send_end",)),
        ),
    ),
)
def test_binding_shadow_paths_cover_composites_loops_and_io(
    tmp_path: Path,
    sandbox_project: tuple[Path, Path],
    config_name: str,
    expected_paths: tuple[tuple[str, ...], ...],
) -> None:
    workspace, project = sandbox_project
    prepared = prepare_project_build(
        ProjectBuildRequest(
            workspace=workspace,
            config=project / "configs" / config_name,
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
