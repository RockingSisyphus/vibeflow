"""Real argv, stdin, file readers/writers and delegated console behavior."""
import shutil
import sys

import pytest

from .support import cli, command, example


@pytest.mark.parametrize("reader,deploy", [
    ("yaml", False), ("pathlib", False), ("streams", False),
    pytest.param("pathlib", True, id="relocated-bundle"),
])
def test_delegate_cli_files_stdin_and_exact_console(tmp_path,reader,deploy):
    work=example(tmp_path / "source","python/cli_addition")
    config=work / f"project/configs/{reader}.jsonc"
    output=tmp_path / "sum.txt"
    left=work / "project/data" / ("numbers.yaml" if reader=="yaml" else "left.txt")
    right=work / "project/data/right.txt"
    exported=cli(work,"export-architecture","--workspace",work / "vibeflow_config.jsonc","--config",config,
        "--output",tmp_path / "ARCHITECTURE.jsonc")
    assert not output.exists() and "sum=" not in exported.stdout
    if deploy:
        bundle = tmp_path / "built"
        cli(work, "build", "--workspace", work / "vibeflow_config.jsonc", "--config", config, "--out-dir", bundle)
        relocated = bundle.rename(tmp_path / "relocated")
        left = shutil.copyfile(left, tmp_path / left.name)
        right = shutil.copyfile(right, tmp_path / right.name)
        shutil.rmtree(work)
        launcher = [relocated / "run.py", "delegate-cli"]
    else:
        launcher = ["-m","vibeflow","delegate-cli","--workspace",work / "vibeflow_config.jsonc","--config",config]
    result=command(sys.executable,"-B",*launcher,"--run-root",tmp_path / "runs","--run-id",reader,
        "--","--left",left,"--right",right,"--output",output,"--verbose",cwd=tmp_path if deploy else work,
        stdin="4\n",env={"PYTHONPATH":None} if deploy else None)
    assert result.stdout=="sum=9\n"
    assert result.stderr==("writer=open\n" if reader=="streams" else "writer=pathlib\n")
    assert output.read_bytes()==b"9\n"
    kernel=(tmp_path / "runs" / reader / "vibeflow.log").read_text(encoding="utf-8")
    assert "CLI.DELEGATE.END" in kernel and "exit_code=0" in kernel
    assert all(text not in kernel for text in (str(left),str(right),str(output),"sum=9","writer=")),kernel
