"""A canonical publication retires only superseded packages and rolls back failures."""

from pathlib import Path

import pytest

from distribution import build


def prepare(tmp_path, monkeypatch, *, same_version=False):
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "HISTORY_DIR", tmp_path / "archive")
    dist = tmp_path / "dist"
    dist.mkdir()
    old = dist / ("vibeflow-distribution-0.17.0.zip" if same_version else "vibeflow-distribution-0.15.2.zip")
    old.write_bytes(b"original release")
    work = dist / ".staging"
    work.mkdir()
    staged = work / "payload.zip"
    staged.write_bytes(b"new release")
    current = dist / "vibeflow-distribution-0.17.0.zip"
    return old, current, {current: (staged, work)}


@pytest.mark.parametrize("same_version", [False, True])
def test_canonical_zip_preserves_previous_bytes(tmp_path, monkeypatch, same_version):
    old, current, staging = prepare(tmp_path, monkeypatch, same_version=same_version)
    build._publish_latest_release_targets(staging, replace=True)
    assert current.read_bytes() == b"new release"
    assert [path.read_bytes() for path in (tmp_path / "archive").rglob("*.zip")] == [b"original release"]
    if old != current:
        assert not old.exists()


def test_history_collision_preserves_both_original_builds(tmp_path, monkeypatch):
    old, current, staging = prepare(tmp_path, monkeypatch)
    history = tmp_path / "archive" / old.name
    history.parent.mkdir()
    history.write_bytes(b"older build of same version")
    build._publish_latest_release_targets(staging, replace=True)
    assert history.read_bytes() == b"older build of same version"
    assert sorted(p.read_bytes() for p in history.parent.rglob("*.zip")) == [b"older build of same version", b"original release"]
    assert current.read_bytes() == b"new release"


def test_failed_history_publication_restores_current_and_previous(tmp_path, monkeypatch):
    old, current, staging = prepare(tmp_path, monkeypatch)
    replace = build.os.replace

    def fail_history(source, target):
        if Path(target).is_relative_to(tmp_path / "archive"):
            raise OSError("history publication failed")
        replace(source, target)

    monkeypatch.setattr(build.os, "replace", fail_history)
    with pytest.raises(OSError, match="history publication failed"):
        build._publish_latest_release_targets(staging, replace=True)
    assert old.read_bytes() == b"original release"
    assert not current.exists()
    assert not list((tmp_path / "archive").rglob("*.zip"))


def test_candidate_defaults_to_a_zip_beside_candidate_not_formal_dist(tmp_path):
    artifacts = build.build_release(tmp_path / "candidate", run_self_check=False)
    assert artifacts.directory == tmp_path / "candidate"
    assert artifacts.archive == tmp_path / build.ARCHIVE_NAME
    assert artifacts.archive.is_file()


def test_candidate_cannot_replace_only_the_canonical_zip(tmp_path):
    with pytest.raises(build.BuildDistributionError, match="matching canonical distribution directory"):
        build.build_release(tmp_path / "candidate", archive_dir=build.DEFAULT_ARCHIVE_DIR,
                            run_self_check=False)
    assert not (tmp_path / "candidate").exists()
