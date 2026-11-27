"""Exercise the Chinese arithmetic example through review, build and its CLI."""

import json
import sys

import pytest

from .support import cli, command, example


@pytest.fixture(scope="module")
def reviewed_project(tmp_path_factory):
    work = example(tmp_path_factory.mktemp("two-workflow-formula") / "source", "python/two_workflow_formula")
    for title in ("计算相邻整数乘积", "计算完整公式", "独立计算平方与差距"):
        reviewed = json.loads(cli(
            work, "review", "--workspace", work / "vibeflow_config.jsonc",
            "--config", work / "project/configs" / f"{title}.jsonc",
        ).stdout)
        assert reviewed["published"] and reviewed["status"] == "PASS", reviewed
    return work


@pytest.fixture(scope="module")
def formula_application(reviewed_project):
    work = reviewed_project
    builds = work.parent / "build"
    for title, name in (("计算相邻整数乘积", "product"), ("计算完整公式", "formula")):
        cli(work, "build", "--workspace", work / "vibeflow_config.jsonc",
            "--config", work / "project/configs" / f"{title}.jsonc", "--out-dir", builds / name)
    return work, builds


@pytest.fixture(scope="module")
def standalone_application(reviewed_project):
    work = reviewed_project
    builds = work.parent / "standalone"
    cli(work, "build", "--workspace", work / "vibeflow_config.jsonc",
        "--config", work / "project/configs/独立计算平方与差距.jsonc", "--out-dir", builds / "score")
    return work, builds


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        pytest.param(5, 2, (56, 6, 32, 94), id="positive-terms"),
        pytest.param(2, 5, (56, -6, 32, 82), id="swapped-inputs"),
        pytest.param(0, 0, (0, 0, 0, 0), id="zero-inputs"),
        pytest.param(-4, 1, (6, -10, 22, 18), id="negative-sum"),
        pytest.param(-3, 3, (0, -12, 24, 12), id="zero-sum-with-nonzero-inputs"),
    ],
)
def test_calculate_formula_across_two_workflows(formula_application, x, y, expected):
    work, builds = formula_application
    result = command(
        sys.executable, "-B", work / "calculate.py", "--build-dir", builds,
        "--x", x, "--y", y, cwd=work,
    )
    assert json.loads(result.stdout) == dict(zip(("乘积项", "差值项", "平方与差距项", "结果"), expected))


@pytest.mark.parametrize(("x", "y", "expected"), [(5, 2, 32), (-2, 5, 36), (0, 0, 0)])
def test_reused_nodeset_runs_without_the_other_workflows(standalone_application, tmp_path, x, y, expected):
    work, builds = standalone_application
    result = command(
        sys.executable, "-B", work / "calculate.py", "--build-dir", builds,
        "--square-gap-only", "--x", x, "--y", y, cwd=tmp_path,
    )
    assert json.loads(result.stdout) == {"平方与差距项": expected}
