"""Destructive developer commands only touch repositories created by this test."""
import json
from pathlib import Path
import os
import shutil
import sys

import pytest

from .support import ROOT, checker_command, command, write


@pytest.mark.parametrize("profile",["base","core","all"])
def test_checker_configuration_failure_has_real_exit_and_diagnostic(tmp_path,profile):
    result=checker_command(tmp_path / "missing",profile)
    assert result.returncode == 2
    payload=json.loads(result.stderr)
    assert payload["findings"][0]["code"] == "CHECKER_CONFIGURATION"
    assert payload["findings"][0]["severity"] == "error"
    assert payload["profile"] == profile


def test_checker_handles_unimportable_application_source(tmp_path):
    write(tmp_path / "src/vibeflow/__init__.py", "raise RuntimeError('application cannot be imported')\n")
    result=checker_command(tmp_path,"core")
    assert result.returncode == 0,result.stdout+result.stderr
    assert json.loads(result.stdout)["ok"]


@pytest.fixture
def own_repository(tmp_path):
    repository=tmp_path / "repository"
    repository.mkdir()
    for name in ("clean_workspace.py","audit_retired_architecture.py","process_supervision.py"):
        if (ROOT / "tools" / name).exists():
            destination=repository / "tools" / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copy2(ROOT / "tools" / name,destination)
    command("git","init","-q",cwd=repository)
    return repository


def test_cleaner_previews_then_removes_only_generated_inputs(own_repository):
    repository=own_repository
    removable=("build/result.json","src/example/__pycache__/cached.pyc","sandbox/python/demo/runs/log.txt",
        "temporary.egg-info/PKG-INFO","old-release.zip","outputs/data.csv")
    protected=("references/source/__pycache__/owned.pyc","archive/old.zip","dist/release.zip",
        "src/example/main.py","distribution/templates/input.json")
    for relative in (*removable,*protected):write(repository / relative,"sample")
    program=repository / "tools/clean_workspace.py"
    preview=command(sys.executable,"-B",program,cwd=repository)
    assert "WOULD_REMOVE" in preview.stdout
    assert all((repository / name).exists() for name in removable)
    done=command(sys.executable,"-B",program,"--apply",cwd=repository)
    assert "REMOVE" in done.stdout
    assert all(not (repository / name).exists() for name in removable)
    assert all((repository / name).is_file() for name in protected)
    assert "cleanup targets: 0" in command(sys.executable,"-B",program,cwd=repository).stdout


def test_cleaner_protects_tracked_source_and_external_symlink_target(own_repository,tmp_path):
    repository=own_repository
    source=write(repository / "build/tracked.py","VALUE=1\n")
    command("git","add","build/tracked.py",cwd=repository)
    refused=command(sys.executable,"-B",repository / "tools/clean_workspace.py","--apply",cwd=repository,success=False)
    assert refused.returncode != 0 and "tracked files" in refused.stdout+refused.stderr
    assert source.is_file()
    command("git","rm","--cached","build/tracked.py",cwd=repository)
    source.unlink();source.parent.rmdir()
    external=write(tmp_path / "external/valuable.txt","valuable")
    (repository / "build").symlink_to(external.parent,target_is_directory=True)
    refused=command(sys.executable,"-B",repository / "tools/clean_workspace.py","--apply",cwd=repository,success=False)
    assert refused.returncode == 0 and "REMOVE" in refused.stdout
    assert not (repository / "build").is_symlink()
    assert external.read_text(encoding="utf-8") == "valuable"


@pytest.mark.parametrize("workers",[1,2])
def test_runner_preserves_selection_and_isolation(tmp_path,workers):
    program=write(tmp_path / "test_selection_input.py",'''import json
from pathlib import Path
collection_directory=str(Path.cwd())

def test_tools_selected():
    Path(__file__).with_suffix('.json').write_text(json.dumps({
        'collection':collection_directory,'execution':str(Path.cwd())}),encoding='utf-8')

def test_other_unselected():
    raise AssertionError('The keyword selector must exclude this test.')
''')
    scratch=tmp_path / "runner"
    result=command(sys.executable,"-B",ROOT / "tools/run_tests.py","--workers",workers,
        "--scratch",scratch,"--","-k","tools",program,cwd=ROOT)
    assert "1 passed" in result.stdout,result.stdout+result.stderr
    report=json.loads(program.with_suffix('.json').read_text(encoding='utf-8'))
    for phase in ('collection','execution'):
        directory=Path(report[phase]).resolve()
        assert directory.is_relative_to(scratch.resolve()) and not directory.is_relative_to(ROOT),report
