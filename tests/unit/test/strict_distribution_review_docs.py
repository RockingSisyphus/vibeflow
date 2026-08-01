from __future__ import annotations

from importlib import resources
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
import zipfile

import pytest

from build_distribution import ROOT_README_GENERATED_AT_MARKER, build_distribution


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PACK_ROOT = REPOSITORY_ROOT / "distribution" / "kernel_development_pack"
TEMPLATE_ROOT = PACK_ROOT / "project_template"
PUBLISHED_DOCS_ROOT = PACK_ROOT / "docs"
REVIEW_DOC_NAMES = (
    "00_内核目的与项目结构.md",
    "01_Node开发规范.md",
    "03_Config与Pipeline规范.md",
    "05_BaseLib与外部依赖规范.md",
    "07_启动命令与报告.md",
    "08_给AI开发者的约束清单.md",
)


@pytest.fixture(scope="module")
def built_distribution(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("review-docs") / "distribution"
    build_distribution(output, run_self_check=False)
    return output


def _read_combined(paths: tuple[Path, ...]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def _assert_review_protocol(layer: str, text: str) -> None:
    lowered = text.lower()
    assert "greenfield" in lowered, layer
    assert "existing" in lowered, layer
    assert "真实 source" in text or "real source" in lowered, layer
    assert "复用 / 修改 / 删除 / 新增" in text, layer
    assert "run.py review" in text, layer
    assert "fail-closed" in lowered or "fails closed" in lowered, layer
    assert (
        re.search(r"后续(?:消息中|一条)?明确.{0,16}(?:批准|确认|消息)", text)
        or all(word in lowered for word in ("explicit", "later", "approval"))
    ), layer
    assert (
        "不是公开审核入口" in text
        or "不得直接调用 Mermaid CLI/mmdc" in text
        or "not a public review entry" in lowered
    ), layer
    assert "flow_kind" in text, layer
    for scope in ("none", "terminal", "python_io", "trusted"):
        assert scope in lowered, (layer, scope)
    assert "effect_scope" in text, layer
    assert "flow_kind=io" in text or "flow_kind = io" in lowered, layer
    assert "external=True" in text, layer
    assert "trusted" in lowered, layer
    assert "delegate-cli" in lowered, layer
    assert "cli.argv" in text and "cli.exit_code" in text, layer
    assert "vibeflow.log" in text, layer


def test_distribution_copies_review_docs_and_preserves_customizable_root_guides(
    built_distribution: Path,
    tmp_path: Path,
) -> None:
    generated_agents = built_distribution / "AGENTS.md"
    generated_readme = built_distribution / "README.md"
    assert generated_agents.read_bytes() == (TEMPLATE_ROOT / "AGENTS.md").read_bytes()

    source_readme = (TEMPLATE_ROOT / "README.md").read_text(encoding="utf-8")
    rendered_readme = generated_readme.read_text(encoding="utf-8")
    project_version = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    version_line = f"版本：{project_version}"
    assert source_readme.splitlines().count(version_line) == 1
    assert rendered_readme.splitlines().count(version_line) == 1
    generated_at_lines = [
        line for line in rendered_readme.splitlines() if line.startswith("生成时间：")
    ]
    assert len(generated_at_lines) == 1
    assert rendered_readme == source_readme.replace(
        ROOT_README_GENERATED_AT_MARKER,
        generated_at_lines[0],
    )

    for name in REVIEW_DOC_NAMES:
        assert (built_distribution / "kernel" / "docs" / name).read_bytes() == (
            PUBLISHED_DOCS_ROOT / name
        ).read_bytes()
    assert (
        built_distribution / "kernel" / "docs" / "10_Kernel能力与项目开发指南.md"
    ).read_bytes() == (REPOSITORY_ROOT / "docs" / "developer_guide.md").read_bytes()
    assert (
        built_distribution / "kernel" / "docs" / "11_JS_TS与Web_AOT构建指南.md"
    ).read_bytes() == (REPOSITORY_ROOT / "docs" / "js_aot_build.md").read_bytes()
    assert (
        built_distribution
        / "kernel"
        / "docs"
        / "14_JS_TS节点与Web_AOT构建计划.md"
    ).read_bytes() == (
        REPOSITORY_ROOT / "docs" / "14_JS_TS节点与Web_AOT构建计划.md"
    ).read_bytes()
    assert (
        built_distribution
        / "kernel"
        / "docs"
        / "15_长期工作流与原生IO改造计划.md"
    ).read_bytes() == (
        REPOSITORY_ROOT / "docs" / "15_长期工作流与原生IO改造计划.md"
    ).read_bytes()

    manifest_lines = (
        built_distribution / "kernel" / "MANIFEST.sha256"
    ).read_text(encoding="utf-8").splitlines()
    manifest_paths = {
        line.split("  ", 1)[1]
        for line in manifest_lines
        if line.strip()
    }
    all_published_docs = {
        f"kernel/docs/{path.name}"
        for path in PUBLISHED_DOCS_ROOT.glob("*.md")
    }
    all_published_docs.add("kernel/docs/10_Kernel能力与项目开发指南.md")
    all_published_docs.update(
        {
            "kernel/docs/11_JS_TS与Web_AOT构建指南.md",
            "kernel/docs/14_JS_TS节点与Web_AOT构建计划.md",
            "kernel/docs/15_长期工作流与原生IO改造计划.md",
        }
    )
    assert all_published_docs <= manifest_paths
    assert "AGENTS.md" not in manifest_paths
    assert "README.md" not in manifest_paths

    customizable = tmp_path / "customizable"
    shutil.copytree(built_distribution, customizable)
    (customizable / "AGENTS.md").write_text("# Custom agent guidance\n", encoding="utf-8")
    (customizable / "README.md").write_text("# Custom project readme\n", encoding="utf-8")
    verification = subprocess.run(
        [sys.executable, "run.py", "verify-kernel"],
        cwd=customizable,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert verification.returncode == 0, verification.stderr


def test_built_distribution_template_is_canonical_and_validates(
    built_distribution: Path,
) -> None:
    validation = subprocess.run(
        [
            sys.executable,
            "run.py",
            "validate",
            "--config",
            "project/configs/main.jsonc",
        ],
        cwd=built_distribution,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr or validation.stdout


def test_distribution_publishes_aot_driver_as_package_resource(
    built_distribution: Path,
) -> None:
    package_data = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["tool"]["setuptools"]["package-data"]["vibeflow"]
    assert "aot/resources/*.mjs" in package_data

    packaged_driver = resources.files("vibeflow.aot.resources").joinpath(
        "toolchain_driver.mjs"
    )
    assert packaged_driver.is_file()
    driver_bytes = packaged_driver.read_bytes()
    assert driver_bytes

    archive_path = built_distribution / "kernel" / "vibeflow-kernel.zip"
    with zipfile.ZipFile(archive_path) as archive:
        archived_driver = "vibeflow/aot/resources/toolchain_driver.mjs"
        assert archived_driver in archive.namelist()
        assert archive.read(archived_driver) == driver_bytes


def test_distribution_template_declares_js_resources_without_installing_dependencies(
    built_distribution: Path,
) -> None:
    project = built_distribution / "project"
    config = json.loads(
        (project / "vibeflow_project.jsonc").read_text(encoding="utf-8")
    )
    assert config["descriptors"] == {
        "nodes": ["manifests/nodes"],
        "base_lib": ["manifests/base_lib"],
        "data_schemas": ["manifests/data"],
        "capabilities": ["manifests/capabilities"],
        "host_extensions": ["manifests/host_extensions"],
    }
    assert config["javascript"] == {
        "package_root": ".",
        "external_packages": [],
    }
    for relative in (
        "manifests/nodes",
        "manifests/base_lib",
        "manifests/data",
        "manifests/capabilities",
        "manifests/host_extensions",
        "host_extensions",
    ):
        assert (project / relative).is_dir()
    assert not (project / "package.json").exists()
    assert not (project / "node_modules").exists()
    template_readme = (built_distribution / "README.md").read_text(
        encoding="utf-8"
    )
    assert "project/configs/<js-workflow>.jsonc" in template_readme
    assert (
        "python run.py build --config project/configs/main.jsonc"
        not in template_readme
    )


def test_distribution_publishes_runnable_typescript_sandbox_without_generated_files(
    built_distribution: Path,
) -> None:
    source = REPOSITORY_ROOT / "examples" / "typescript_sandbox"
    published = built_distribution / "examples" / "typescript_sandbox"
    expected_files = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_file()
        and not {
            "__pycache__",
            ".pytest_cache",
            "runs",
            "reports",
            "node_modules",
        }.intersection(path.relative_to(source).parts)
        and not path.name.endswith(".pyc")
    }
    actual_files = {
        path.relative_to(published).as_posix()
        for path in published.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert (published / "project" / "package.json").is_file()
    assert (published / "project" / "package-lock.json").is_file()
    for excluded in ("node_modules", "reports", "runs", "__pycache__"):
        assert not any(path.name == excluded for path in published.rglob("*"))

    manifest_paths = {
        line.split("  ", 1)[1]
        for line in (
            built_distribution / "kernel" / "MANIFEST.sha256"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert {
        f"examples/typescript_sandbox/{relative}"
        for relative in actual_files
    } <= manifest_paths
    published_aot_guide = (
        built_distribution
        / "kernel"
        / "docs"
        / "11_JS_TS与Web_AOT构建指南.md"
    ).read_text(encoding="utf-8")
    assert "kernel/vibeflow-kernel.zip" in published_aot_guide
    assert (
        "python examples/typescript_sandbox/run_all.py --skip-browser"
        in published_aot_guide
    )

    kernel_probe = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            (
                "import sys; sys.path.insert(0, sys.argv[1]); "
                "import sandbox_support, vibeflow; print(vibeflow.__file__)"
            ),
            str(published),
        ],
        cwd=built_distribution,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert kernel_probe.returncode == 0, kernel_probe.stderr
    assert str(
        built_distribution / "kernel" / "vibeflow-kernel.zip"
    ) in kernel_probe.stdout

    help_result = subprocess.run(
        [
            sys.executable,
            "-s",
            str(published / "run_all.py"),
            "--help",
        ],
        cwd=built_distribution,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr or help_result.stdout
    assert "--skip-browser" in help_result.stdout


def test_developer_published_and_ai_guides_share_the_review_protocol(
    built_distribution: Path,
) -> None:
    development_layer = _read_combined(
        (
            REPOSITORY_ROOT / "README.md",
            REPOSITORY_ROOT / "README.en.md",
            REPOSITORY_ROOT / "docs" / "README.md",
            REPOSITORY_ROOT / "docs" / "kernel_target_vision.md",
            REPOSITORY_ROOT / "docs" / "kernel_development_guide.md",
            REPOSITORY_ROOT / "docs" / "developer_guide.md",
        )
    )
    published_user_layer = _read_combined(
        (
            built_distribution / "README.md",
            *(
                built_distribution / "kernel" / "docs" / name
                for name in REVIEW_DOC_NAMES[:-1]
            ),
            built_distribution / "kernel" / "docs" / "10_Kernel能力与项目开发指南.md",
        )
    )
    published_ai_layer = _read_combined(
        (
            built_distribution / "AGENTS.md",
            built_distribution / "kernel" / "docs" / REVIEW_DOC_NAMES[-1],
        )
    )

    for layer, text in (
        ("VibeFlow development documentation", development_layer),
        ("published user documentation", published_user_layer),
        ("published AI guidance", published_ai_layer),
    ):
        _assert_review_protocol(layer, text)


def test_review_docs_reject_old_public_renderer_and_io_permission_wording(
    built_distribution: Path,
) -> None:
    source_paths = (
        REPOSITORY_ROOT / "README.md",
        REPOSITORY_ROOT / "README.en.md",
        REPOSITORY_ROOT / "docs" / "kernel_target_vision.md",
        REPOSITORY_ROOT / "docs" / "kernel_development_guide.md",
        REPOSITORY_ROOT / "docs" / "developer_guide.md",
        PACK_ROOT / "README.md",
        TEMPLATE_ROOT / "README.md",
        TEMPLATE_ROOT / "AGENTS.md",
        *(PUBLISHED_DOCS_ROOT / name for name in REVIEW_DOC_NAMES),
    )
    contents = _read_combined(source_paths)
    forbidden_wording = (
        "SVG 图使用 Mermaid CLI 渲染",
        "详细审查 SVG 必须用 `python run.py svg",
        "详细审查 SVG 必须由 `python run.py svg",
        "外部输入输出必须建模为 `io`、`data_store`、`document` 类型节点，"
        "或明确的 `external=True` 节点",
        "外部读写必须由显式 `io` / `data_store` / `document` / "
        "`external=True` 节点",
    )
    for wording in forbidden_wording:
        assert wording not in contents

    assert not any(built_distribution.rglob("*.provenance.json"))
    manifest = (built_distribution / "kernel" / "MANIFEST.sha256").read_text(
        encoding="utf-8"
    )
    assert ".provenance.json" not in manifest
