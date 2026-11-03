"""Actual wheel/sdist installs and extracted distribution user workflows."""
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile

import pytest

from .support import ROOT, command, example, write


pytestmark=pytest.mark.delivery


def interpreter(directory):
    return directory / ("Scripts/python.exe" if os.name=="nt" else "bin/python")


@pytest.fixture(scope="module")
def installable_packages(tmp_path_factory):
    root=tmp_path_factory.mktemp("python-packages")
    source=root / "source";source.mkdir()
    for name in ("pyproject.toml","MANIFEST.in","LICENSE"):
        shutil.copy2(ROOT / name,source / name)
    shutil.copytree(ROOT / "src",source / "src",ignore=shutil.ignore_patterns("__pycache__","*.pyc","*.egg-info"))
    shutil.copytree(ROOT / "tools/workflow-viewer",source / "tools/workflow-viewer")
    command(sys.executable,"-B","-m","build","--outdir",root / "packages",cwd=source)
    wheelhouse=root / "build-dependencies"
    command(sys.executable,"-m","pip","--disable-pip-version-check","download","--dest",wheelhouse,
        "setuptools>=77","wheel>=0.43",cwd=root)
    return root


@pytest.mark.parametrize("format",["wheel","sdist"])
def test_installed_package_executes_without_checkout(installable_packages,tmp_path,format,toolchain):
    root=installable_packages
    venv=tmp_path / "environment"
    command(sys.executable,"-m","venv",venv,cwd=tmp_path)
    python=interpreter(venv)
    command(python,"-m","pip","--disable-pip-version-check","install","--no-index","--find-links",root / "build-dependencies",
        "setuptools","wheel",cwd=tmp_path,env={"PYTHONPATH":None})
    package=next((root / "packages").glob("*.whl" if format=="wheel" else "*.tar.gz"))
    command(python,"-m","pip","--disable-pip-version-check","install","--no-deps","--no-index","--no-build-isolation",package,
        cwd=tmp_path,env={"PYTHONPATH":None})
    command(python,"-B","-m","vibeflow","--help",cwd=tmp_path,env={"PYTHONPATH":None})
    work=example(tmp_path / "workspace","python/minimal")
    target=tmp_path / "bundle"
    command(python,"-B","-m","vibeflow","build","--workspace",work / "vibeflow_config.jsonc","--config",
        work / "project/configs/config_with_imports.jsonc","--out-dir",target,cwd=tmp_path,env={"PYTHONPATH":None})
    shutil.rmtree(work)
    request=write(tmp_path / "request.json",{})
    result=command(python,"-B",ROOT / "tests/e2e/applications/python_run.py","bundle",target,request,tmp_path / "runs",
        cwd=tmp_path,env={"PYTHONPATH":None})
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["outputs"]=={"value.out":5}
    js=example(tmp_path / "javascript","javascript/minimal",toolchain)
    built=command(python,"-B","-m","vibeflow","build","--workspace",js / "vibeflow_config.jsonc","--config",
        js / "project/configs/greeting.jsonc","--target","node","--profile","single-esm","--out-dir",tmp_path / "js-bundle",
        cwd=tmp_path,env={"PYTHONPATH":None})
    shutil.rmtree(js)
    request=write(tmp_path / "js-request.json",{"initial":{"name":"Ada"},"mode":"async","session":True})
    result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",json.loads(built.stdout)["entry"],request,cwd=tmp_path)
    payload=json.loads(next(line[7:] for line in result.stdout.splitlines() if line.startswith("RESULT ")))
    assert payload["output"]=={"greeting":"Hello, Ada! (2026-01-02T03:04:05Z)"}


@pytest.fixture(scope="module")
def distribution_archives(tmp_path_factory):
    root=tmp_path_factory.mktemp("distribution-candidate")
    command(sys.executable,"-B",ROOT / "distribution/build.py","--output-dir",root / "collaborative",
        "--autonomous-output-dir",root / "autonomous","--archive-dir",root / "archives",cwd=ROOT,env={"PYTHONPATH":None},timeout=180)
    archives=list((root / "archives").glob("*.zip"))
    assert len(archives)==2,archives
    # All subsequent checks use ZIPs; the original candidate trees are gone.
    shutil.rmtree(root / "collaborative");shutil.rmtree(root / "autonomous")
    return archives


@pytest.mark.parametrize("profile",["collaborative","autonomous"])
def test_extracted_profile_install_rename_run_and_deploy(distribution_archives,tmp_path,toolchain,profile):
    archive=next(path for path in distribution_archives if ("autonomous" in path.name)==(profile=="autonomous"))
    with zipfile.ZipFile(archive) as package:package.extractall(tmp_path / "extract")
    work=next((tmp_path / "extract").iterdir())
    metadata=json.loads((work / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    assert metadata["development_profile"]==profile
    python_root=work / "renamed_python";javascript_root=work / "renamed_javascript"
    (work / "python_project").rename(python_root);(work / "javascript_project").rename(javascript_root)
    workspace=json.loads((work / "vibeflow_config.jsonc").read_text(encoding="utf-8"))
    for item in workspace["roots"]:
        item["path"]={"python_project":"renamed_python","javascript_project":"renamed_javascript"}[item["path"]]
        item["id"]="custom_"+item["id"]
    write(work / "vibeflow_config.jsonc",workspace)
    command(sys.executable,"-B",work / "run.py","verify-kernel",cwd=tmp_path,env={"PYTHONPATH":None})
    (javascript_root / "node_modules").symlink_to(toolchain / "node_modules",target_is_directory=True)
    for app in (python_root,javascript_root):
        command(sys.executable,"-B",work / "run.py","review","--config",app / "configs/main.jsonc",
            cwd=tmp_path,env={"PYTHONPATH":None})
        command(sys.executable,"-B",work / "run.py","validate","--config",app / "configs/main.jsonc","--json",
            cwd=tmp_path,env={"PYTHONPATH":None})
    target=tmp_path / "deployed"
    initial=tmp_path / "initial.json";shutil.copy2(python_root / "probe_input.json",initial)
    command(sys.executable,"-B",work / "run.py","build","--config",python_root / "configs/main.jsonc","--out-dir",target,
        cwd=tmp_path,env={"PYTHONPATH":None})
    built=command(sys.executable,"-B",work / "run.py","build","--config",javascript_root / "configs/main.jsonc",
        "--target","node","--profile","esm-module","--out-dir",javascript_root / "build/node",cwd=tmp_path,env={"PYTHONPATH":None})
    probe=command("node",javascript_root / "scripts/workflow_execution_probe.mjs",cwd=work,env={"PYTHONPATH":None})
    assert json.loads(probe.stdout)["status"]=="PASS"
    deployed_javascript=tmp_path / "javascript-bundle"
    shutil.copytree(javascript_root / "build/node",deployed_javascript)
    js_initial=json.loads((javascript_root / "probe_input.json").read_text(encoding="utf-8"))
    js_request=write(tmp_path / "javascript-request.json",{"initial":js_initial})
    shutil.rmtree(tmp_path / "extract")
    deployed_result=command("node",ROOT / "tests/e2e/applications/javascript_run.mjs",deployed_javascript / "workflow.js",js_request,cwd=tmp_path)
    output=json.loads(next(line[7:] for line in deployed_result.stdout.splitlines() if line.startswith("RESULT ")))["output"]
    assert output == {"response":js_initial["request"]},output
    result=command(sys.executable,"-B",target / "run.py","run","--input",initial,"--runtime-profile","train",
        "--run-root",tmp_path / "runs",cwd=tmp_path,env={"PYTHONPATH":None})
    assert json.loads(result.stdout)["status"] in {"PASS","CONCERNS"}
