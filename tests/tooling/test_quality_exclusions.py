from __future__ import annotations

import json
from pathlib import Path

from vibeflow.tooling.application.cli import main as cli_main
from vibeflow.core.quality import (
    QualityStructureLimits,
    QualityThresholds,
)
from vibeflow.tooling.application.python.project.quality_scan import (
    DEFAULT_EXCLUDED_DIRS,
    scan_code_quality,
)


def _write_quality_fixture(root: Path) -> None:
    sources = {
        "purity/legacy.py": "def legacy():\n    return 1\n\n\n\n",
        "portable/legacy.py": "def legacy():\n    return 1\n\n\n\n",
        "targets/python/purity/canonical.py": (
            "def canonical_purity():\n    return 1\n\n\n\n"
        ),
        "block_compiler/canonical.py": (
            "def canonical_block_compiler():\n    return 1\n\n\n\n"
        ),
    }
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")


def test_root_exclusions_do_not_hide_same_named_canonical_packages(
    tmp_path: Path,
) -> None:
    _write_quality_fixture(tmp_path)
    report = scan_code_quality(
        tmp_path,
        thresholds=QualityThresholds(warn_file_lines=5),
        structure_limits=QualityStructureLimits(
            warn_root_code_files=20,
            max_root_code_files=30,
            warn_code_dirs=20,
            max_code_dirs=30,
            warn_code_files_per_dir=20,
            max_code_files_per_dir=30,
            warn_code_dir_depth=10,
            max_code_dir_depth=20,
            warn_child_code_dirs_per_dir=10,
            max_child_code_dirs_per_dir=20,
            warn_root_level_code_files=10,
            max_root_level_code_files=20,
            enforce_role_imports=False,
        ),
        excluded_dirs={
            *DEFAULT_EXCLUDED_DIRS,
            "./purity",
            "./portable",
        },
    )

    assert {item.path for item in report.files} == {
        "block_compiler/canonical.py",
        "targets/python/purity/canonical.py",
    }
    root_layout = report.structure_summary["root_layout"]
    assert root_layout["code_files"] == 2
    assert root_layout["code_dirs"] == 2
    assert root_layout["max_child_code_dirs_per_dir"] == 2
    warning_paths = {
        finding.object_id
        for finding in report.findings
        if finding.rule_id == "QUALITY.FILE.WARN_LINES"
    }
    assert warning_paths == {
        "block_compiler/canonical.py",
        "targets/python/purity/canonical.py",
    }


def test_quality_cli_accepts_repeated_top_level_exclusions(
    tmp_path: Path,
    capsys,
) -> None:
    _write_quality_fixture(tmp_path)

    code = cli_main(
        [
            "quality-check",
            "--project-target",
            "python",
            "--path",
            str(tmp_path),
            "--json",
            "--enable-structure-limits",
            "--exclude-dir",
            "purity",
            "--exclude-dir",
            "portable",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["files"] == 2
    assert {
        item["path"] for item in payload["files"]
    } == {
        "block_compiler/canonical.py",
        "targets/python/purity/canonical.py",
    }
    root_layout = payload["structure_summary"]["root_layout"]
    assert root_layout["code_files"] == 2
    assert root_layout["max_child_code_dirs_per_dir"] == 2


def test_quality_cli_exact_paths_exclude_files_and_directories_only_at_root(
    tmp_path: Path,
    capsys,
) -> None:
    sources = {
        "legacy.py": "VALUE = 'root'\n",
        "nested/legacy.py": "VALUE = 'nested'\n",
        "compat/hidden.py": "VALUE = 'root directory'\n",
        "nested/compat/visible.py": "VALUE = 'nested directory'\n",
    }
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    code = cli_main(
        [
            "quality-check",
            "--project-target",
            "python",
            "--path",
            str(tmp_path),
            "--json",
            "--enable-structure-limits",
            "--exclude-path",
            "legacy.py",
            "--exclude-path",
            "compat",
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert {item["path"] for item in payload["files"]} == {
        "nested/compat/visible.py",
        "nested/legacy.py",
    }
    root_layout = payload["structure_summary"]["root_layout"]
    assert root_layout["code_files"] == 2
    assert root_layout["max_child_code_dirs_per_dir"] == 1
