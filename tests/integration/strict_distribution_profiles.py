from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

import distribution.build as distribution_builder
from distribution.profile_config import DistributionProfileError, load_distribution_profiles


def _profile_payload() -> dict[str, object]:
    return {
        "schema": "vibeflow.distribution-profiles.v1",
        "document_sets": {"common": ["docs/doc.md"]},
        "profiles": {
            "collaborative": {
                "prompt_fragments": ["distribution/prompts/prompt.md"],
                "document_sets": ["common"],
                "agent_protocol": {
                    "change_inventory": "required",
                    "planned_review": True,
                    "human_approval_gate": True,
                    "required_review_artifact": "expanded_svg",
                },
                "agent_automation": {
                    "refresh_architecture": True,
                    "validate": True,
                    "quality": True,
                    "build": True,
                    "workflow_execution_probe": True,
                },
            },
            "autonomous": {
                "prompt_fragments": ["distribution/prompts/prompt.md"],
                "document_sets": ["common"],
                "agent_protocol": {
                    "change_inventory": "optional",
                    "planned_review": False,
                    "human_approval_gate": False,
                    "required_review_artifact": "on_demand",
                },
                "agent_automation": {
                    "refresh_architecture": True,
                    "validate": True,
                    "quality": True,
                    "build": True,
                    "workflow_execution_probe": True,
                },
            },
        },
    }


def _write_profiles(tmp_path: Path, payload: dict[str, object]) -> Path:
    repository = tmp_path / "repository"
    (repository / "distribution/prompts").mkdir(parents=True)
    (repository / "docs").mkdir()
    (repository / "distribution/prompts/prompt.md").write_text("prompt\n", encoding="utf-8")
    (repository / "docs/doc.md").write_text("doc\n", encoding="utf-8")
    path = repository / "distribution/profiles.jsonc"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(schema="unknown"),
        lambda payload: payload.update(core={"override": True}),
        lambda payload: payload["profiles"]["autonomous"].update(document_sets=["missing"]),
        lambda payload: payload["profiles"]["autonomous"]["agent_protocol"].update(human_approval_gate=True),
        lambda payload: payload["profiles"]["autonomous"].update(prompt_fragments=["outside.md"]),
    ],
)
def test_profile_configuration_fails_closed(tmp_path: Path, mutate) -> None:
    payload = _profile_payload()
    mutate(payload)
    with pytest.raises(DistributionProfileError):
        load_distribution_profiles(_write_profiles(tmp_path, payload))


def test_release_set_shares_kernel_templates_and_machine_policy(tmp_path: Path) -> None:
    release = distribution_builder.build_release_set(
        tmp_path / "collaborative",
        autonomous_output=tmp_path / "autonomous",
        archive_dir=tmp_path / "archive",
        run_self_check=False,
    )
    collaborative = release.collaborative.directory
    autonomous = release.autonomous.directory
    for relative in (
        "kernel/vibeflow-kernel.zip",
        "python_project",
        "javascript_project",
        "vibeflow_config.jsonc",
    ):
        left = collaborative / relative
        right = autonomous / relative
        if left.is_dir():
            left_files = {path.relative_to(left): path.read_bytes() for path in left.rglob("*") if path.is_file()}
            right_files = {path.relative_to(right): path.read_bytes() for path in right.rglob("*") if path.is_file()}
            assert left_files == right_files
        else:
            assert left.read_bytes() == right.read_bytes()
    assert hashlib.sha256((collaborative / "kernel/vibeflow-kernel.zip").read_bytes()).digest() == hashlib.sha256((autonomous / "kernel/vibeflow-kernel.zip").read_bytes()).digest()

    collaborative_metadata = json.loads((collaborative / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    autonomous_metadata = json.loads((autonomous / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    assert collaborative_metadata["development_profile"] == "collaborative"
    assert autonomous_metadata["development_profile"] == "autonomous"
    assert autonomous_metadata["agent_protocol"]["human_approval_gate"] is False
    autonomous_guidance = "\n".join(
        [
            (autonomous / "AGENTS.md").read_text(encoding="utf-8"),
            *((path.read_text(encoding="utf-8") for path in (autonomous / "kernel/docs").rglob("*.md"))),
        ]
    )
    assert "等待人类明确批准" not in autonomous_guidance
    assert "人机协同开发协议" not in autonomous_guidance
    assert "直接维护真实 source" in autonomous_guidance

    for artifacts in (release.collaborative, release.autonomous):
        extracted = tmp_path / f"extracted-{artifacts.directory.name}"
        with zipfile.ZipFile(artifacts.archive) as archive:
            archive.extractall(extracted)
        archived_root = extracted / distribution_builder.ARCHIVE_ROOT_NAME
        distribution_builder._verify_distribution_document_links(archived_root)


def test_distribution_document_links_are_resolved_from_published_locations(
    tmp_path: Path,
) -> None:
    distribution = tmp_path / "distribution"
    docs = distribution / "kernel/docs/user"
    docs.mkdir(parents=True)
    (distribution / "README.md").write_text("# Package\n", encoding="utf-8")
    (distribution / "AGENTS.md").write_text(
        "[User guide](kernel/docs/user/guide.md)\n",
        encoding="utf-8",
    )
    (docs / "guide.md").write_text("[Peer](peer.md)\n", encoding="utf-8")
    (docs / "peer.md").write_text("# Peer\n", encoding="utf-8")
    distribution_builder._verify_distribution_document_links(distribution)

    (docs / "guide.md").write_text(
        "[Development-tree path](docs/user/peer.md)\n",
        encoding="utf-8",
    )
    with pytest.raises(
        distribution_builder.BuildDistributionError,
        match="missing in the package",
    ):
        distribution_builder._verify_distribution_document_links(distribution)


def test_release_set_publication_rolls_back_all_four_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = (tmp_path / "collaborative", tmp_path / "autonomous")
    archives = (
        tmp_path / "archive" / distribution_builder.ARCHIVE_NAME,
        tmp_path / "archive" / distribution_builder.AUTONOMOUS_ARCHIVE_NAME,
    )
    for path, content in zip(outputs, ("old collaborative", "old autonomous"), strict=True):
        path.mkdir(parents=True)
        (path / "marker").write_text(content, encoding="utf-8")
    for path, content in zip(archives, (b"old collaborative zip", b"old autonomous zip"), strict=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    real_replace = os.replace
    publication_count = 0

    def fail_during_publication(source, target):
        nonlocal publication_count
        source_path = Path(source)
        if source_path.name in {"payload", *[path.name for path in archives]}:
            publication_count += 1
            if publication_count == 3:
                raise OSError("injected release-set publication failure")
        return real_replace(source, target)

    monkeypatch.setattr(distribution_builder.os, "replace", fail_during_publication)
    with pytest.raises(OSError, match="injected"):
        distribution_builder.build_release_set(
            outputs[0],
            autonomous_output=outputs[1],
            archive_dir=tmp_path / "archive",
            run_self_check=False,
        )
    assert (outputs[0] / "marker").read_text(encoding="utf-8") == "old collaborative"
    assert (outputs[1] / "marker").read_text(encoding="utf-8") == "old autonomous"
    assert archives[0].read_bytes() == b"old collaborative zip"
    assert archives[1].read_bytes() == b"old autonomous zip"
