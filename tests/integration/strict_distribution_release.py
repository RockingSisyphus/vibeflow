from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from xml.etree import ElementTree

import pytest

import distribution.build as distribution_builder


def _files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_release_publishes_deterministic_directory_and_single_root_archive(
    tmp_path: Path,
) -> None:
    first = distribution_builder.build_release(
        tmp_path / "first" / "distribution",
        archive_dir=tmp_path / "first" / "archives",
        run_self_check=False,
    )
    second = distribution_builder.build_release(
        tmp_path / "second" / "distribution",
        archive_dir=tmp_path / "second" / "archives",
        run_self_check=False,
    )

    assert _files(first.directory) == _files(second.directory)
    assert first.archive.read_bytes() == second.archive.read_bytes()
    metadata = json.loads((first.directory / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    assert metadata == {
        "agent_automation": {
            "build": True,
            "quality": True,
            "refresh_architecture": True,
            "validate": True,
            "workflow_execution_probe": True,
        },
        "agent_protocol": {
            "change_inventory": "required",
            "human_approval_gate": True,
            "planned_review": True,
            "required_review_artifact": "expanded_svg",
        },
        "development_profile": "collaborative",
        "kernel": {
            "archive": "kernel/vibeflow-kernel.zip",
            "sha256": hashlib.sha256(
                (first.directory / "kernel/vibeflow-kernel.zip").read_bytes()
            ).hexdigest(),
        },
        "roots": [
            {
                "id": "python-project",
                "path": "python_project",
                "project_target": "python",
            },
            {
                "id": "javascript-project",
                "path": "javascript_project",
                "project_target": "javascript",
            },
        ],
        "schema": "vibeflow.distribution.v2",
        "version": distribution_builder.VERSION,
    }
    javascript_project = first.directory / "javascript_project"
    project_config = json.loads(
        (javascript_project / "vibeflow_project.jsonc").read_text(
            encoding="utf-8"
        )
    )
    assert project_config["architecture"]["documents"] == [
        {
            "workflow": "configs/main.jsonc",
            "document": "ARCHITECTURE.jsonc",
        }
    ]
    architecture = (
        javascript_project / "ARCHITECTURE.jsonc"
    ).read_text(encoding="utf-8")
    assert '"project_target": "javascript"' in architecture
    assert str(first.directory) not in architecture
    assert '"type_used": "minimal.process_payload"' in architecture

    published_guidance = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            first.directory / "README.md",
            first.directory / "AGENTS.md",
            first.directory / "kernel/docs/overview.md",
            first.directory / "kernel/docs/user/workflow-and-config.md",
            first.directory / "kernel/docs/user/commands-and-results.md",
            first.directory / "kernel/docs/user/profiles/collaborative.md",
        )
    )
    for marker in (
        "effect_scope",
        "工作流执行探针",
        "业务结果",
        "planned",
        "人工批准",
    ):
        assert marker in published_guidance

    with zipfile.ZipFile(first.directory / "kernel/vibeflow-kernel.zip") as kernel:
        constants = kernel.read("vibeflow/core/constants.py")
        flow = kernel.read("vibeflow/core/flow.py")
        workflow_model = kernel.read("vibeflow/block_compiler/model.py")
    assert b'FLOW_KIND_GLOBAL_STATE = "global_state"' in constants
    assert b'EFFECT_SCOPE_GLOBAL_STATE = "global_state"' in constants
    assert b"class ExecutionLockSpec" in flow
    assert b'WORKFLOW_ABI_VERSION = "vibeflow.workflow.v4"' in workflow_model

    with zipfile.ZipFile(first.archive) as archive:
        names = archive.namelist()
        assert names[0] == "vibeflow-distribution/"
        assert {name.split("/", 1)[0] for name in names if name} == {
            "vibeflow-distribution"
        }
        assert all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in archive.infolist())
        archived_agents = archive.read("vibeflow-distribution/AGENTS.md").decode(
            "utf-8"
        )
        archived_config_guide = archive.read(
            "vibeflow-distribution/kernel/docs/user/commands-and-results.md"
        ).decode("utf-8")
        for marker in (
            "工作流执行探针",
            "业务结果",
        ):
            assert marker in archived_config_guide
        assert "kernel/docs/user/commands-and-results.md" in archived_agents

    extracted = tmp_path / "extracted"
    with zipfile.ZipFile(first.archive) as archive:
        archive.extractall(extracted)
    completed = subprocess.run(
        [sys.executable, "run.py", "verify-kernel"],
        cwd=extracted / "vibeflow-distribution",
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout


def test_distribution_renderer_reviews_minimal_javascript_workflow(
    tmp_path: Path,
) -> None:
    distribution = distribution_builder.build_distribution(
        tmp_path / "distribution",
        run_self_check=False,
    )
    for relative in (
        "javascript_project",
        "kernel/tools/mermaid-renderer",
    ):
        completed = subprocess.run(
            ["npm", "ci"],
            cwd=distribution / relative,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr or completed.stdout

    output = distribution / "reports/javascript-minimal.svg"
    completed = subprocess.run(
        [
            sys.executable,
            "run.py",
            "review",
            "--config",
            "javascript_project/configs/main.jsonc",
            "--output",
            str(output.relative_to(distribution)),
        ],
        cwd=distribution,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["status"] == "PASS"
    assert payload["result_code"] == "VIBEFLOW_REVIEW_ARTIFACT_PASS"
    assert payload["published"] is True
    root = ElementTree.parse(output).getroot()
    coverage = {
        (
            element.get("data-review-kind", ""),
            element.get("data-review-target", ""),
        )
        for element in root.iter()
        if "review-inline-fragment" in element.get("class", "").split()
    }
    assert ("workflow", "javascript-project") in coverage


@pytest.mark.parametrize("failure_call", [1, 2, 3, 4])
def test_release_pair_rolls_back_backup_and_publication_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    output = tmp_path / "published" / "distribution"
    archive = tmp_path / "archives" / "distribution.zip"
    output_staging_root = tmp_path / "published" / ".staging"
    archive_staging_root = tmp_path / "archives" / ".staging"
    staged_output = output_staging_root / "payload"
    staged_archive = archive_staging_root / "distribution.zip"
    output.mkdir(parents=True)
    archive.parent.mkdir(parents=True)
    output_staging_root.mkdir()
    archive_staging_root.mkdir()
    (output / "marker.txt").write_text("old-directory", encoding="utf-8")
    archive.write_bytes(b"old-archive")
    staged_output.mkdir()
    (staged_output / "marker.txt").write_text("new-directory", encoding="utf-8")
    staged_archive.write_bytes(b"new-archive")

    real_replace = os.replace
    calls = 0

    def failing_replace(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError(f"injected os.replace failure {failure_call}")
        real_replace(source, destination)

    monkeypatch.setattr(distribution_builder.os, "replace", failing_replace)

    with pytest.raises(OSError, match="injected os.replace failure"):
        distribution_builder._publish_release_pair(
            staged_output,
            staged_archive,
            output,
            archive,
            replace=True,
            output_staging_root=output_staging_root,
            archive_staging_root=archive_staging_root,
        )

    assert (output / "marker.txt").read_text(encoding="utf-8") == "old-directory"
    assert archive.read_bytes() == b"old-archive"


def test_release_keep_existing_checks_both_artifacts_before_building(
    tmp_path: Path,
) -> None:
    output = tmp_path / "distribution"
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    archive = archive_dir / distribution_builder.ARCHIVE_NAME
    archive.write_bytes(b"keep")

    with pytest.raises(distribution_builder.BuildDistributionError, match="archive already exists"):
        distribution_builder.build_release(
            output,
            archive_dir=archive_dir,
            replace=False,
            run_self_check=False,
        )

    assert not output.exists()
    assert archive.read_bytes() == b"keep"


@pytest.mark.parametrize(
    "overlap",
    ["output_contains_archive", "archive_contains_output", "same_path"],
)
def test_release_rejects_overlapping_paths_before_self_check_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    overlap: str,
) -> None:
    archive_dir = tmp_path / "archives"
    archive = archive_dir / distribution_builder.ARCHIVE_NAME
    if overlap == "output_contains_archive":
        output = archive_dir
    elif overlap == "archive_contains_output":
        output = archive / "distribution"
    else:
        output = archive
    self_checks: list[bool] = []
    mkdir_calls: list[Path] = []
    staging_calls: list[bool] = []

    def unexpected_mkdir(path: Path, *_args: object, **_kwargs: object) -> None:
        mkdir_calls.append(path)
        raise AssertionError("mkdir must not run for overlapping release paths")

    def unexpected_mkdtemp(**_kwargs: object) -> str:
        staging_calls.append(True)
        raise AssertionError("staging must not run for overlapping release paths")

    monkeypatch.setattr(
        distribution_builder,
        "_run_core_self_check",
        lambda: self_checks.append(True),
    )
    monkeypatch.setattr(distribution_builder.Path, "mkdir", unexpected_mkdir)
    monkeypatch.setattr(distribution_builder.tempfile, "mkdtemp", unexpected_mkdtemp)

    with pytest.raises(
        distribution_builder.BuildDistributionError,
        match="distribution output and archive paths must not overlap",
    ):
        distribution_builder.build_release(
            output,
            archive_dir=archive_dir,
            run_self_check=True,
        )

    assert self_checks == []
    assert mkdir_calls == []
    assert staging_calls == []
    assert not archive_dir.exists()
    assert not output.exists()
    assert not list(tmp_path.rglob("*.vibeflow-build-*"))


def test_built_launcher_loads_kernel_before_a_root_shadow_package(
    tmp_path: Path,
) -> None:
    output = tmp_path / "distribution"
    distribution_builder.build_distribution(output, run_self_check=False)
    shadow_package = output / "vibeflow"
    shadow_package.mkdir()
    (shadow_package / "__init__.py").write_text(
        'raise RuntimeError("distribution root shadow package was imported")\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "-I", "run.py", "verify-kernel"],
        cwd=output,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    assert completed.stdout == "kernel integrity: OK\n"


def test_staged_validation_failure_preserves_existing_release_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "distribution"
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    archive = archive_dir / distribution_builder.ARCHIVE_NAME
    output.mkdir()
    (output / "marker.txt").write_text("old-directory", encoding="utf-8")
    archive.write_bytes(b"old-archive")

    def fail_validation(_output: Path) -> None:
        raise distribution_builder.BuildDistributionError("injected staged failure")

    monkeypatch.setattr(
        distribution_builder,
        "_verify_staged_distribution",
        fail_validation,
    )

    with pytest.raises(
        distribution_builder.BuildDistributionError,
        match="injected staged failure",
    ):
        distribution_builder.build_release(
            output,
            archive_dir=archive_dir,
            run_self_check=False,
        )

    assert (output / "marker.txt").read_text(encoding="utf-8") == "old-directory"
    assert archive.read_bytes() == b"old-archive"
