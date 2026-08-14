from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
import zipfile

import pytest

from distribution.build import build_distribution
from distribution.profile_config import load_distribution_profiles


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def built_distribution(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output = tmp_path_factory.mktemp("review-docs") / "distribution"
    build_distribution(output, run_self_check=False)
    return output


def test_distribution_composes_collaborative_prompt_and_documents(
    built_distribution: Path,
) -> None:
    profile = load_distribution_profiles(
        REPOSITORY_ROOT / "distribution" / "profiles.jsonc"
    )["collaborative"]
    expected_prompt = "\n\n".join(
        path.read_text(encoding="utf-8").rstrip()
        for path in profile.prompt_fragments
    ) + "\n"
    assert (built_distribution / "AGENTS.md").read_text(encoding="utf-8") == expected_prompt

    docs_root = built_distribution / "kernel" / "docs"
    docs = sorted(path for path in docs_root.rglob("*.md") if path.name != "README.md")
    assert len(docs) == len(profile.documents)
    assert "人机协同" in (docs_root / "user/profiles/collaborative.md").read_text(encoding="utf-8")
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
    for marker in (
        "vibeflow.workflow.v4",
        "global_state",
        "execution_lock",
        "工作流执行探针",
        "业务结果正确性",
    ):
        assert marker in combined


def test_root_guides_remain_customizable_but_profile_docs_are_protected(
    built_distribution: Path,
    tmp_path: Path,
) -> None:
    customizable = tmp_path / "customizable"
    shutil.copytree(built_distribution, customizable)
    (customizable / "AGENTS.md").write_text("# Custom agent guidance\n", encoding="utf-8")
    (customizable / "README.md").write_text("# Custom project readme\n", encoding="utf-8")
    verification = subprocess.run(
        [sys.executable, "run.py", "verify-kernel"],
        cwd=customizable,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verification.returncode == 0, verification.stderr or verification.stdout

    protected = customizable / "kernel" / "docs" / "user" / "commands-and-results.md"
    protected.write_text("changed\n", encoding="utf-8")
    verification = subprocess.run(
        [sys.executable, "run.py", "verify-kernel"],
        cwd=customizable,
        text=True,
        capture_output=True,
        check=False,
    )
    assert verification.returncode == 2


def test_agent_prompt_is_a_document_router(built_distribution: Path) -> None:
    agents = (built_distribution / "AGENTS.md").read_text(encoding="utf-8")
    assert "```" not in agents
    for relative in re.findall(r"\]\((kernel/docs/[^)]+\.md)\)", agents):
        assert (built_distribution / relative).is_file(), relative
    for implementation_detail in (
        "NodeRegistry.register(",
        "createPlugin(context",
        "params_schema",
        "vibeflow.workflow.v4",
    ):
        assert implementation_detail not in agents


def test_active_documentation_has_no_duplicate_long_prose() -> None:
    documents = sorted((REPOSITORY_ROOT / "docs").rglob("*.md"))
    seen: dict[str, Path] = {}
    for path in documents:
        source = path.read_text(encoding="utf-8")
        source = re.sub(r"```.*?```", "", source, flags=re.DOTALL)
        for paragraph in source.split("\n\n"):
            lines = [line.strip() for line in paragraph.splitlines()]
            prose = " ".join(
                line for line in lines
                if line and not line.startswith(("#", "|", "- ["))
            )
            if len(prose) < 160:
                continue
            assert prose not in seen, f"duplicate prose in {seen.get(prose)} and {path}"
            seen[prose] = path


def test_document_index_covers_every_active_markdown() -> None:
    docs_root = REPOSITORY_ROOT / "docs"
    index = (docs_root / "README.md").read_text(encoding="utf-8")
    linked = {
        (docs_root / target).resolve()
        for target in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]+)?\)", index)
    }
    expected = {
        path.resolve()
        for path in docs_root.rglob("*.md")
        if path.name != "README.md"
    }
    assert linked == expected


def test_distribution_contains_only_user_facing_canonical_docs(
    built_distribution: Path,
) -> None:
    docs_root = built_distribution / "kernel" / "docs"
    assert (docs_root / "overview.md").is_file()
    assert (docs_root / "user/python-development.md").is_file()
    assert not (docs_root / "design").exists()
    assert not (docs_root / "maintainers").exists()
    assert not (docs_root / "user/profiles/autonomous.md").exists()
    assert not (REPOSITORY_ROOT / "distribution/profile_docs").exists()
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in docs_root.rglob("*.md")
    )
    for maintainer_detail in (
        "src/vibeflow/",
        "sandbox/",
        "quality/run.py",
        "distribution/build.py",
    ):
        assert maintainer_detail not in combined
    for stale_contract in (
        "CONTRACT.params_schema",
        "output_schema",
        "调用点 `requires` / `provides` 必须与",
    ):
        assert stale_contract not in combined


def test_distribution_has_two_isolated_minimal_projects(
    built_distribution: Path,
) -> None:
    python_project = built_distribution / "python_project"
    javascript_project = built_distribution / "javascript_project"
    python_config = json.loads((python_project / "vibeflow_project.jsonc").read_text(encoding="utf-8"))
    javascript_config = json.loads((javascript_project / "vibeflow_project.jsonc").read_text(encoding="utf-8"))
    assert python_config["project_target"] == "python"
    assert set(javascript_config["descriptors"]) == {"nodes", "data_schemas"}
    assert javascript_config["project_target"] == "javascript"

    for project in (python_project, javascript_project):
        workflow = json.loads((project / "configs" / "main.jsonc").read_text(encoding="utf-8"))
        nodes = workflow["pipeline"]["nodes"]
        assert [node["id"] for node in nodes] == [
            "start",
            "input_boundary",
            "process_payload",
            "output_boundary",
            "end",
        ]
        assert sum(node["id"] == "process_payload" for node in nodes) == 1
        assert (project / "ARCHITECTURE.jsonc").is_file()
    assert not (built_distribution / "sandbox").exists()
    assert not any((javascript_project / name).exists() for name in ("plugins", "host_extensions", "web"))


def test_minimal_projects_validate_and_python_probe_reports_scope(
    built_distribution: Path,
) -> None:
    for config in (
        "python_project/configs/main.jsonc",
        "javascript_project/configs/main.jsonc",
    ):
        completed = subprocess.run(
            [sys.executable, "run.py", "validate", "--config", config, "--json"],
            cwd=built_distribution,
            text=True,
            capture_output=True,
            check=False,
        )
        if config.startswith("javascript") and "VF_TOOLCHAIN_MISSING" in completed.stdout:
            continue
        assert completed.returncode == 0, completed.stderr or completed.stdout
        payload = json.loads(completed.stdout)
        assert payload["status"] in {"PASS", "CONCERNS"}
        assert payload["result_code"].startswith("VIBEFLOW_STRUCTURE_")

    run_root = built_distribution.parent / "probe-runs"
    completed = subprocess.run(
        [
            sys.executable,
            "run.py",
            "run",
            "--config",
            "python_project/configs/main.jsonc",
            "--input",
            "python_project/probe_input.json",
            "--run-root",
            str(run_root),
            "--run-id",
            "acceptance-probe",
        ],
        cwd=built_distribution,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    payload = json.loads(completed.stdout)
    assert payload["result_code"] == "VIBEFLOW_WORKFLOW_EXECUTION_PASS"
    assert {item["id"] for item in payload["checked"]} == {
        "workflow_started",
        "execution_order",
        "declared_outputs",
        "structural_runtime",
    }


def test_kernel_archive_and_architecture_are_profile_neutral(
    built_distribution: Path,
) -> None:
    metadata = json.loads((built_distribution / "DISTRIBUTION.json").read_text(encoding="utf-8"))
    kernel = built_distribution / metadata["kernel"]["archive"]
    assert hashlib.sha256(kernel.read_bytes()).hexdigest() == metadata["kernel"]["sha256"]
    with zipfile.ZipFile(kernel) as archive:
        model = archive.read("vibeflow/block_compiler/model.py")
    assert b'WORKFLOW_ABI_VERSION = "vibeflow.workflow.v4"' in model
    for project in ("python_project", "javascript_project"):
        text = (built_distribution / project / "ARCHITECTURE.jsonc").read_text(encoding="utf-8")
        assert '"effect_scope"' in text
        assert '"runtime_dispatch"' in text
        assert '"execution_lock"' in text
        assert '"contains_global_state"' in text
        assert str(built_distribution) not in text
