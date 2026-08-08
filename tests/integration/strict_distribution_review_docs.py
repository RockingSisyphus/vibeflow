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

from distribution.build import build_distribution


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
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
    for scope in ("none", "terminal", "python_io", "global_state", "trusted"):
        assert scope in lowered, (layer, scope)
    assert "effect_scope" in text, layer
    assert "flow_kind=io" in text or "flow_kind = io" in lowered, layer
    assert "external=True" in text, layer
    assert "trusted" in lowered, layer
    assert "delegate-cli" in lowered, layer
    assert "cli.argv" in text and "cli.exit_code" in text, layer
    assert "vibeflow.log" in text, layer


def _assert_global_state_protocol(layer: str, text: str) -> None:
    lowered = text.lower()
    for marker in (
        "flow_kind=global_state",
        "effect_scope=global_state",
        "runtime_dispatch",
        "callback",
        "execution_lock",
        "exclusive",
        "try/finally",
        "detached",
        "result_key",
        "vibeflow.workflow.v4",
        "vibeflow.workflow.v3",
        "target.feature.unsupported",
        "cloud",
        "lock_wait",
        "lock_acquired",
        "lock_released",
        "global_state_may_have_changed",
    ):
        assert marker in lowered, (layer, marker)
    assert "execution domain" in lowered or "执行域" in text, layer
    assert "pipeline.execution_lock" in text, layer
    assert (
        "pipeline.nodes[].execution_lock" in text
        or ("调用点" in text and "execution_lock" in text)
    ), layer
    assert "vibeflow." in text and "保留" in text, layer
    assert "Provider" in text, layer
    assert "文件" in text and "环境变量" in text, layer
    assert "subprocess" in lowered and "动态 import" in text and "ffi" in lowered, layer
    assert "graph.execution_lock.global_state_uncoordinated" in lowered, layer
    assert "node.effect.runtime_dispatch.undeclared" in lowered, layer
    same_key = any(
        marker in lowered
        for marker in ("同名", "相同 key", "同 key", "same key", "identical key")
    )
    different_key = any(
        marker in lowered
        for marker in ("异名", "不同 key", "异 key", "different key")
    )
    assert same_key and different_key, layer
    assert re.search(r"(?:不|不会|不再).{0,32}自动.{0,16}(?:锁|互斥)", text), layer
    assert re.search(r"(?:不|不会|都不).{0,48}自动恢复", text), layer
    assert "rollback" in lowered, layer
    assert re.search(r"(?:不授予|不增加|不提供|不取得).{0,24}权限", text), layer
    assert "禁止" in text and "detached" in lowered, layer
    assert "join" in lowered, layer


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
    assert rendered_readme == source_readme

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
    assert not any(
        path.name.startswith(("14_", "15_"))
        for path in (built_distribution / "kernel" / "docs").glob("*.md")
    )

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
    all_published_docs.add("kernel/docs/11_JS_TS与Web_AOT构建指南.md")
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
            "python_project/configs/main.jsonc",
        ],
        cwd=built_distribution,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert validation.returncode == 0, validation.stderr or validation.stdout


def test_distribution_publishes_canonical_resources(
    built_distribution: Path,
) -> None:
    package_data = tomllib.loads(
        (REPOSITORY_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )["tool"]["setuptools"]["package-data"]["vibeflow"]
    assert {
        "targets/javascript/resources/*.mjs",
        "tooling/project/schema/*.schema.json",
    } <= set(package_data)
    assert "aot/resources/*.mjs" not in package_data
    assert "resources/schema/*.schema.json" not in package_data

    root = resources.files("vibeflow")
    canonical_paths = (
        *(
            f"tooling/project/schema/{name}"
            for name in (
                "config.schema.json",
                "health_report.schema.json",
                "node.schema.json",
                "nodeset.schema.json",
                "policy.schema.json",
            )
        ),
        *(
            f"targets/javascript/resources/{name}"
            for name in ("runtime_helpers.mjs", "toolchain_driver.mjs")
        ),
    )

    archive_path = built_distribution / "kernel" / "vibeflow-kernel.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        for canonical in canonical_paths:
            canonical_resource = root.joinpath(canonical)
            assert canonical_resource.is_file()
            expected = canonical_resource.read_bytes()
            assert expected
            canonical_archive = f"vibeflow/{canonical}"
            assert canonical_archive in names
            assert archive.read(canonical_archive) == expected


def test_published_guides_are_project_neutral_and_use_public_import_surfaces(
    built_distribution: Path,
) -> None:
    paths = (
        *(PUBLISHED_DOCS_ROOT.glob("*.md")),
        TEMPLATE_ROOT / "README.md",
        TEMPLATE_ROOT / "AGENTS.md",
        built_distribution / "README.md",
        built_distribution / "AGENTS.md",
        *(built_distribution / "kernel" / "docs").glob("*.md"),
    )
    text = _read_combined(tuple(paths))

    assert not re.search(
        r"tavern|酒馆|角色卡|gensokyo|tavernbridge|tavern adapter|\bERA\b",
        text,
        flags=re.IGNORECASE,
    )
    assert not re.search(
        r"\b(?:from\s+vibeflow\s+import\b|"
        r"(?:from|import)\s+vibeflow\."
        r"(?:aot|runtime|portable|config|health|purity|devtools|rendering|workspace)\b)",
        text,
    )


def test_distribution_template_has_isolated_python_and_javascript_roots(
    built_distribution: Path,
) -> None:
    python_project = built_distribution / "python_project"
    javascript_project = built_distribution / "javascript_project"
    python_config = json.loads(
        (python_project / "vibeflow_project.jsonc").read_text(encoding="utf-8")
    )
    assert python_config["project_target"] == "python"
    assert "registry" in python_config
    assert "descriptors" not in python_config
    assert "javascript" not in python_config

    config = json.loads(
        (javascript_project / "vibeflow_project.jsonc").read_text(encoding="utf-8")
    )
    assert config["project_target"] == "javascript"
    assert config["descriptors"] == {
        "nodes": ["manifests/nodes"],
        "base_lib": ["manifests/base_lib"],
        "data_schemas": ["manifests/data"],
        "capabilities": ["manifests/capabilities"],
        "host_extensions": ["manifests/host_extensions"],
        "plugins": ["manifests/plugins"],
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
        "manifests/plugins",
        "host_extensions",
    ):
        assert (javascript_project / relative).is_dir()
    assert (javascript_project / "package.json").is_file()
    assert (javascript_project / "package-lock.json").is_file()
    package = json.loads(
        (javascript_project / "package.json").read_text(encoding="utf-8")
    )
    assert package["name"] == "vibeflow-javascript-example"
    assert "imports" not in package
    assert not (javascript_project / "node_modules").exists()
    assert not (javascript_project / "negative").exists()
    assert not any(
        path.name.startswith(("invalid_", "negative_"))
        for path in (javascript_project / "configs").glob("*.jsonc")
    )
    template_readme = (built_distribution / "README.md").read_text(
        encoding="utf-8"
    )
    assert "javascript_project/configs/linear.jsonc" in template_readme
    assert "python run.py build --config python_project/" not in template_readme


def test_distribution_uses_the_two_example_roots_without_repository_sandbox(
    built_distribution: Path,
) -> None:
    assert not (built_distribution / "sandbox").exists()
    assert (built_distribution / "python_project/configs/main.jsonc").is_file()
    assert (
        built_distribution / "javascript_project/configs/linear.jsonc"
    ).is_file()
    assert (
        built_distribution
        / "javascript_project/configs/browser_permanent_port_host.jsonc"
    ).is_file()
    assert (
        built_distribution / "javascript_project/ARCHITECTURE.jsonc"
    ).is_file()

    manifest_paths = {
        line.split("  ", 1)[1]
        for line in (
            built_distribution / "kernel" / "MANIFEST.sha256"
        ).read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    assert not any(path.startswith("sandbox/") for path in manifest_paths)

    published_aot_guide = (
        built_distribution
        / "kernel"
        / "docs"
        / "11_JS_TS与Web_AOT构建指南.md"
    ).read_text(encoding="utf-8")
    assert "javascript_project/" in published_aot_guide
    assert "不复制整套源码仓库 Sandbox" in published_aot_guide


def test_javascript_guide_recommends_project_owned_quality_tools(
    built_distribution: Path,
) -> None:
    source = (REPOSITORY_ROOT / "docs/js_aot_build.md").read_text(
        encoding="utf-8"
    )
    published = (
        built_distribution
        / "kernel/docs/11_JS_TS与Web_AOT构建指南.md"
    ).read_text(encoding="utf-8")
    for command in (
        "npx tsc --noEmit",
        "npx eslint .",
        "npx vitest run",
        "npx playwright test",
    ):
        assert command in source
        assert command in published
    assert "不会自动运行" in source


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


def test_developer_published_and_ai_guides_share_the_global_state_protocol(
    built_distribution: Path,
) -> None:
    development_layer = _read_combined(
        (
            REPOSITORY_ROOT / "README.md",
            REPOSITORY_ROOT / "README.en.md",
            REPOSITORY_ROOT / "docs" / "kernel_target_vision.md",
            REPOSITORY_ROOT / "docs" / "kernel_development_guide.md",
            REPOSITORY_ROOT / "docs" / "developer_guide.md",
            REPOSITORY_ROOT / "docs" / "js_aot_build.md",
        )
    )
    source_user_layer = _read_combined(
        (
            TEMPLATE_ROOT / "README.md",
            *(sorted(PUBLISHED_DOCS_ROOT.glob("*.md"))),
            REPOSITORY_ROOT / "docs" / "developer_guide.md",
            REPOSITORY_ROOT / "docs" / "js_aot_build.md",
        )
    )
    built_user_layer = _read_combined(
        (
            built_distribution / "README.md",
            *(sorted((built_distribution / "kernel" / "docs").glob("*.md"))),
        )
    )
    for layer, text in (
        ("VibeFlow development documentation", development_layer),
        ("distribution source user documentation", source_user_layer),
        ("built distribution user documentation", built_user_layer),
    ):
        _assert_global_state_protocol(layer, text)

    prompt_paths = (
        TEMPLATE_ROOT / "AGENTS.md",
        PUBLISHED_DOCS_ROOT / "08_给AI开发者的约束清单.md",
        built_distribution / "AGENTS.md",
        built_distribution / "kernel" / "docs" / "08_给AI开发者的约束清单.md",
    )
    for prompt_path in prompt_paths:
        _assert_global_state_protocol(
            f"AI prompt {prompt_path}",
            prompt_path.read_text(encoding="utf-8"),
        )


def test_built_distribution_architecture_exposes_execution_lock_facts(
    built_distribution: Path,
) -> None:
    for architecture_path in (
        built_distribution / "python_project" / "ARCHITECTURE.jsonc",
        built_distribution / "javascript_project" / "ARCHITECTURE.jsonc",
    ):
        text = architecture_path.read_text(encoding="utf-8")
        for marker in (
            '"effect_scope"',
            '"runtime_dispatch"',
            '"execution_lock"',
            '"effective_execution_lock"',
            '"contains_global_state"',
        ):
            assert marker in text, (architecture_path, marker)
        assert '"root_exclusive"' not in text, architecture_path

    javascript_guide = (
        built_distribution
        / "kernel"
        / "docs"
        / "11_JS_TS与Web_AOT构建指南.md"
    ).read_text(encoding="utf-8")
    assert 'implemented `flow_kind="global_state"`' in javascript_guide
    assert "TARGET.FEATURE.UNSUPPORTED" in javascript_guide
    assert "vibeflow.workflow.v4" in javascript_guide
    assert "vibeflow.workflow.v3" in javascript_guide


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
