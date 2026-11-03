"""Real argv, stdin, file readers/writers and delegated console behavior."""
import sys

import pytest

from .support import cli, command, example


@pytest.mark.parametrize("reader",["yaml","pathlib","streams"])
def test_delegate_cli_files_stdin_and_exact_console(tmp_path,reader):
    work=example(tmp_path / "source","python/cli_addition")
    config=work / f"project/configs/{reader}.jsonc"
    output=tmp_path / "sum.txt"
    left=work / "project/data" / ("numbers.yaml" if reader=="yaml" else "left.txt")
    right=work / "project/data/right.txt"
    exported=cli(work,"export-architecture","--workspace",work / "vibeflow_config.jsonc","--config",config,
        "--output",tmp_path / "ARCHITECTURE.jsonc")
    assert not output.exists() and "sum=" not in exported.stdout
    result=command(sys.executable,"-B","-m","vibeflow","delegate-cli","--workspace",work / "vibeflow_config.jsonc",
        "--config",config,"--run-root",tmp_path / "runs","--run-id",reader,"--","--left",left,"--right",right,
        "--output",output,"--verbose",cwd=work,stdin="4\n")
    assert result.stdout=="sum=9\n"
    assert result.stderr==("writer=open\n" if reader=="streams" else "writer=pathlib\n")
    assert output.read_bytes()==b"9\n"
    kernel=(tmp_path / "runs" / reader / "vibeflow.log").read_text(encoding="utf-8")
    assert "CLI.DELEGATE.END" in kernel and "exit_code=0" in kernel
    assert all(text not in kernel for text in (str(left),str(right),str(output),"sum=9","writer=")),kernel
