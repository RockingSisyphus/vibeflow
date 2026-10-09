from __future__ import annotations

from pathlib import Path

import pytest

from vibeflow.targets.javascript.build.toolchain import AotToolchainError, probe_toolchain


@pytest.mark.parametrize("lock_name", ["pnpm-lock.yaml", "yarn.lock"])
def test_probe_reports_missing_dependencies_independently_of_lock_style(
    tmp_path: Path,
    lock_name: str,
) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / lock_name).write_text(
        "typescript: 7.0.1\nesbuild: 0.28.0\n",
        encoding="utf-8",
    )

    with pytest.raises(AotToolchainError) as captured:
        probe_toolchain(tmp_path)

    assert captured.value.code == "VF_TOOLCHAIN_MISSING"


def test_probe_reports_missing_dependencies_with_multiple_lockfiles(
    tmp_path: Path,
) -> None:
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "package-lock.json").write_text("{}\n", encoding="utf-8")
    (tmp_path / "yarn.lock").write_text("", encoding="utf-8")

    with pytest.raises(AotToolchainError) as captured:
        probe_toolchain(tmp_path)

    assert captured.value.code == "VF_TOOLCHAIN_MISSING"
