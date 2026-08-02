from __future__ import annotations

import builtins
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


QUALITY_ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(QUALITY_ROOT / "src"))

from vibeflow_quality.cli import main
from vibeflow_quality import profiles as profile_module
from vibeflow_quality.profiles import run_profile


class RepositoryFixture:
    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.write("src/vibeflow/__init__.py", "")
        for relative in profile_module._REQUIRED_DIRECTORIES:
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, source: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def codes(self, profile: str) -> list[str]:
        return [item.code for item in run_profile(self.fixture.root, profile).findings]

    def test_core_rejects_target_dependency(self) -> None:
        self.fixture.write(
            "src/vibeflow/core/model.py",
            "from vibeflow.targets.python import Runtime\n",
        )
        self.assertIn("LAYER_DEPENDENCY", self.codes("core"))

    def test_core_rejects_filesystem_io(self) -> None:
        self.fixture.write(
            "src/vibeflow/core/loader.py",
            "from pathlib import Path\n\ndef load():\n    return Path('x').read_text()\n",
        )
        codes = self.codes("core")
        self.assertIn("CORE_IO_CALL", codes)

    def test_block_compiler_rejects_target_dependency(self) -> None:
        self.fixture.write(
            "src/vibeflow/block_compiler/compile.py",
            "from vibeflow.targets.javascript import emitter\n",
        )
        self.assertIn("LAYER_DEPENDENCY", self.codes("block-compiler"))

    def test_targets_may_not_import_each_other(self) -> None:
        self.fixture.write(
            "src/vibeflow/targets/python/wrong.py",
            "from vibeflow.targets.javascript import emitter\n",
        )
        self.fixture.write(
            "src/vibeflow/targets/javascript/wrong.py",
            "from vibeflow.targets.python import runtime\n",
        )
        self.assertIn("LAYER_DEPENDENCY", self.codes("python-target"))
        self.assertIn("LAYER_DEPENDENCY", self.codes("javascript-target"))

    def test_import_graph_covers_function_and_type_checking_imports(self) -> None:
        self.fixture.write(
            "src/vibeflow/core/hidden_imports.py",
            """from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vibeflow.targets.python import runtime

def load():
    from vibeflow.targets.javascript import frontend
    return frontend
""",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "core").findings
            if item.code == "LAYER_DEPENDENCY"
        ]
        self.assertEqual(
            {item.details["target"] for item in findings},
            {
                "vibeflow.targets.javascript",
                "vibeflow.targets.python",
            },
        )

    def test_import_graph_covers_fixed_dynamic_imports(self) -> None:
        self.fixture.write(
            "src/vibeflow/core/dynamic_imports.py",
            """import importlib as loader
from importlib import import_module as load_module

def load():
    loader.import_module("vibeflow.targets.python.runtime")
    load_module("vibeflow.targets.javascript.frontend")
    __import__("vibeflow.targets.python.project")
""",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "core").findings
            if item.code == "LAYER_DEPENDENCY"
            and item.details.get("import_kind") == "dynamic"
        ]
        self.assertEqual(
            {item.details["target"] for item in findings},
            {
                "vibeflow.targets.javascript.frontend",
                "vibeflow.targets.python.project",
                "vibeflow.targets.python.runtime",
            },
        )

    def test_python_application_reports_shortest_cross_target_path(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/application/python/runner.py",
            """from vibeflow.tooling.project import long_path, short_path
""",
        )
        self.fixture.write(
            "src/vibeflow/tooling/project/long_path.py",
            "from vibeflow.tooling.project import middle\n",
        )
        self.fixture.write(
            "src/vibeflow/tooling/project/middle.py",
            "from vibeflow.targets.javascript import frontend\n",
        )
        self.fixture.write(
            "src/vibeflow/tooling/project/short_path.py",
            "from vibeflow.targets.javascript import frontend\n",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "python-target").findings
            if item.code == "APPLICATION_CROSS_TARGET"
            and item.subject_id == "vibeflow.tooling.application.python.runner"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].details["dependency_path"],
            [
                "vibeflow.tooling.application.python.runner",
                "vibeflow.tooling.project.short_path",
                "vibeflow.targets.javascript",
            ],
        )

    def test_javascript_application_reports_transitive_python_path(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/application/javascript/build.py",
            "from vibeflow.tooling.project import bridge\n",
        )
        self.fixture.write(
            "src/vibeflow/tooling/project/bridge.py",
            "from vibeflow.targets.python import compiler\n",
        )
        findings = [
            item
            for item in run_profile(
                self.fixture.root,
                "javascript-target",
            ).findings
            if item.code == "APPLICATION_CROSS_TARGET"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].details["dependency_path"],
            [
                "vibeflow.tooling.application.javascript.build",
                "vibeflow.tooling.project.bridge",
                "vibeflow.targets.python",
            ],
        )

    def test_target_profile_reports_transitive_cross_target_path(self) -> None:
        self.fixture.write(
            "src/vibeflow/targets/python/project/entry.py",
            "from vibeflow.core import bridge\n",
        )
        self.fixture.write(
            "src/vibeflow/core/bridge.py",
            "from vibeflow.targets.javascript import frontend\n",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "python-target").findings
            if item.code == "TRANSITIVE_LAYER_DEPENDENCY"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].details["dependency_path"],
            [
                "vibeflow.targets.python.project.entry",
                "vibeflow.core.bridge",
                "vibeflow.targets.javascript",
            ],
        )

    def test_base_rejects_transitive_neutral_tooling_target_dependency(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/project/neutral.py",
            "from vibeflow.tooling.project import helper\n",
        )
        self.fixture.write(
            "src/vibeflow/tooling/project/helper.py",
            """def load():
    from vibeflow.targets.python import runtime
    return runtime
""",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "base").findings
            if item.code == "NEUTRAL_TARGET_DEPENDENCY"
            and item.subject_id == "vibeflow.tooling.project.neutral"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(
            findings[0].details["dependency_path"],
            [
                "vibeflow.tooling.project.neutral",
                "vibeflow.tooling.project.helper",
                "vibeflow.targets.python",
            ],
        )

    def test_base_allows_explicit_target_application_boundary(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/application/cli/__init__.py",
            "from vibeflow.tooling.application.javascript import cli\n",
        )
        self.fixture.write(
            "src/vibeflow/tooling/application/javascript/cli.py",
            "from vibeflow.targets.javascript import build\n",
        )
        findings = run_profile(self.fixture.root, "base").findings
        self.assertFalse(
            any(
                item.code == "NEUTRAL_TARGET_DEPENDENCY"
                and item.subject_id == "vibeflow.tooling.application.cli"
                for item in findings
            )
        )

    def test_javascript_application_rejects_python_specific_symbol(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/application/javascript/build.py",
            "from vibeflow.core import NodeRegistry\n",
        )
        findings = run_profile(
            self.fixture.root,
            "javascript-target",
        ).findings
        matched = [
            item
            for item in findings
            if item.code == "JAVASCRIPT_APPLICATION_PYTHON_SYMBOL"
        ]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].details["symbol"], "NodeRegistry")

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for MJS syntax test")
    def test_javascript_profile_checks_mjs_syntax(self) -> None:
        self.fixture.write(
            "src/vibeflow/targets/javascript/resources/broken.mjs",
            "export const broken = ;\n",
        )
        self.assertIn("JS_SYNTAX", self.codes("javascript-target"))

    def test_base_finds_syntax_and_generated_content(self) -> None:
        self.fixture.write("src/vibeflow/core/broken.py", "def broken(:\n")
        (self.fixture.root / "output").mkdir()
        codes = self.codes("base")
        self.assertIn("PY_SYNTAX", codes)
        self.assertIn("GENERATED_ARTIFACT", codes)

    def test_base_allows_formal_release_directories(self) -> None:
        (self.fixture.root / "dist/vibeflow-distribution").mkdir(parents=True)
        (self.fixture.root / "archive").mkdir()
        self.assertNotIn("GENERATED_ARTIFACT", self.codes("base"))

    def test_base_checks_document_links_and_stale_release_text(self) -> None:
        self.fixture.write(
            "docs/guide.md",
            "VibeFlow 0.10.0 used [a missing guide](missing.md).\n",
        )
        findings = run_profile(self.fixture.root, "base").findings
        self.assertEqual(
            {
                item.code
                for item in findings
                if item.subject_id == "docs/guide.md"
            },
            {"DOCUMENT_LINK_MISSING", "STALE_DOCUMENTATION"},
        )

    def test_base_checks_document_image_links(self) -> None:
        self.fixture.write(
            "README.md",
            "![missing architecture](docs/assets/missing.svg)\n",
        )

        self.assertIn("DOCUMENT_LINK_MISSING", self.codes("base"))

    def test_base_checks_english_readme(self) -> None:
        self.fixture.write(
            "README.en.md",
            "See [missing guide](docs/missing.md).\n",
        )

        self.assertIn("DOCUMENT_LINK_MISSING", self.codes("base"))

    def test_base_rejects_removed_plan_references(self) -> None:
        self.fixture.write(
            "docs/guide.md",
            "See 15_长期工作流与原生IO改造计划.md for details.\n",
        )
        self.assertIn("REMOVED_DOCUMENT_REFERENCE", self.codes("base"))

    def test_base_rejects_obsolete_documented_commands(self) -> None:
        self.fixture.write(
            "docs/guide.md",
            "python run.py compile-old --config project/configs/main.jsonc\n",
        )
        findings = [
            item
            for item in run_profile(self.fixture.root, "base").findings
            if item.code == "STALE_DOCUMENT_COMMAND"
        ]
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details["command"], "compile-old")

    def test_base_accepts_current_launcher_and_module_commands(self) -> None:
        self.fixture.write(
            "docs/guide.md",
            "python run.py architecture --config project/configs/main.jsonc\n"
            "PYTHONPATH=src python -m vibeflow build --target node\n"
            "vibeflow quality-check --path project\n",
        )
        self.assertNotIn("STALE_DOCUMENT_COMMAND", self.codes("base"))

    def test_base_finds_nested_sandbox_artifacts(self) -> None:
        (self.fixture.root / "sandbox/python/integration/.artifacts").mkdir(
            parents=True
        )
        self.fixture.write("src/vibeflow/core/stray.pyc", "compiled")
        findings = run_profile(self.fixture.root, "base").findings
        subjects = {item.subject_id for item in findings}
        self.assertIn(
            "sandbox/python/integration/.artifacts",
            subjects,
        )
        self.assertIn("src/vibeflow/core/stray.pyc", subjects)

    def test_base_finds_all_root_zip_files_and_sandbox_builds(self) -> None:
        self.fixture.write("historical-release.zip", "archive")
        (self.fixture.root / "sandbox/javascript/integration/build").mkdir()
        subjects = {
            item.subject_id
            for item in run_profile(self.fixture.root, "base").findings
            if item.code == "GENERATED_ARTIFACT"
        }
        self.assertIn("historical-release.zip", subjects)
        self.assertIn("sandbox/javascript/integration/build", subjects)

    def test_base_requires_canonical_structure(self) -> None:
        (self.fixture.root / "src/vibeflow/core/config").rmdir()
        findings = run_profile(self.fixture.root, "base").findings
        self.assertTrue(
            any(
                item.code == "MISSING_CANONICAL_DIRECTORY"
                and item.subject_id == "src/vibeflow/core/config"
                for item in findings
            )
        )

    def test_base_rejects_root_api_exports(self) -> None:
        self.fixture.write(
            "src/vibeflow/__init__.py",
            "from vibeflow.core import WorkflowPlan\n",
        )
        self.assertIn("ROOT_API_EXPORT", self.codes("base"))

    def test_base_rejects_legacy_repository_paths(self) -> None:
        (self.fixture.root / "tests/unit").mkdir(parents=True)
        self.assertIn("LEGACY_REPOSITORY_PATH", self.codes("base"))

    def test_base_rejects_business_module_at_target_root(self) -> None:
        self.fixture.write(
            "src/vibeflow/targets/python/runtime_bridge.py", "VALUE = 1\n"
        )
        self.assertIn("LAYER_ROOT_BUSINESS_MODULE", self.codes("base"))

    def test_base_scans_tooling_for_removed_imports(self) -> None:
        self.fixture.write(
            "src/vibeflow/tooling/application/entry.py",
            "from vibeflow.runtime import PipelineRuntime\n",
        )
        self.assertIn("LAYER_DEPENDENCY", self.codes("base"))

    def test_javascript_quality_cannot_launch_processes(self) -> None:
        self.fixture.write(
            "src/vibeflow/targets/javascript/quality/source.py",
            "import subprocess\n\ndef inspect():\n    subprocess.run(['node'])\n",
        )
        self.assertIn("JAVASCRIPT_FRONTEND_PROCESS", self.codes("javascript-target"))

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for all profile")
    def test_all_aggregates_base_and_layer_findings(self) -> None:
        self.fixture.write("src/vibeflow/core/wrong.py", "import os\n")
        (self.fixture.root / "output").mkdir()
        codes = self.codes("all")
        self.assertIn("CORE_IO_IMPORT", codes)
        self.assertIn("GENERATED_ARTIFACT", codes)

    def test_checker_never_imports_vibeflow(self) -> None:
        original = builtins.__import__

        def guarded(name: str, *args: object, **kwargs: object) -> object:
            if name == "vibeflow" or name.startswith("vibeflow."):
                raise AssertionError(f"unexpected VibeFlow import: {name}")
            return original(name, *args, **kwargs)

        self.fixture.write("src/vibeflow/core/model.py", "from dataclasses import dataclass\n")
        with mock.patch("builtins.__import__", side_effect=guarded):
            report = run_profile(self.fixture.root, "core")
        self.assertTrue(report.ok)

    def test_json_report_has_stable_envelope(self) -> None:
        report = run_profile(self.fixture.root, "base")
        payload = json.loads(report.to_json())
        self.assertEqual(payload["schema_version"], "vibeflow.repository-quality.v1")
        self.assertEqual(payload["profile"], "base")
        self.assertIn("summary", payload)
        self.assertIn("findings", payload)


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixture = RepositoryFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def test_cli_returns_zero_for_clean_profile(self) -> None:
        self.fixture.write("src/vibeflow/core/model.py", "VALUE = 1\n")
        with mock.patch("builtins.print"):
            self.assertEqual(
                main(["--root", str(self.fixture.root), "--profile", "core"]),
                0,
            )

    def test_cli_returns_one_for_violation(self) -> None:
        self.fixture.write("src/vibeflow/core/model.py", "import os\n")
        with mock.patch("builtins.print"):
            self.assertEqual(
                main(["--root", str(self.fixture.root), "--profile", "core"]),
                1,
            )

    def test_cli_returns_two_for_invalid_environment(self) -> None:
        missing = self.fixture.root / "missing"
        with mock.patch("builtins.print"):
            self.assertEqual(main(["--root", str(missing)]), 2)

    def test_cli_json_configuration_error_uses_report_envelope(self) -> None:
        missing = self.fixture.root / "missing"
        with mock.patch("builtins.print") as output:
            self.assertEqual(
                main(["--root", str(missing), "--format", "json"]), 2
            )
        payload = json.loads(output.call_args.args[0])
        self.assertEqual(payload["profile"], "all")
        self.assertEqual(
            payload["findings"][0]["code"], "CHECKER_CONFIGURATION"
        )

    def test_run_script_works_without_installing_package(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(QUALITY_ROOT / "run.py"),
                "--root",
                str(self.fixture.root),
                "--profile",
                "base",
                "--format",
                "json",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["profile"], "base")


if __name__ == "__main__":
    unittest.main()
