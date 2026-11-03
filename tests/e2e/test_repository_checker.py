"""Repository checker policy through its standalone command and JSON report."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from tests.e2e.support import ROOT, checker_command


def checker_report(root, profile, node_executable=None):
    result=checker_command(root,profile,*( ["--node",node_executable] if node_executable else []))
    assert result.returncode in (0,1),result.stdout+result.stderr
    payload=json.loads(result.stdout)
    rows=[SimpleNamespace(**{**row,"source_location":SimpleNamespace(**row["source_location"])}) for row in payload["findings"]]
    return SimpleNamespace(**{**payload,"findings":rows,"payload":payload})


def checker_findings(root,code):
    return [row for row in checker_report(root,"base").findings if row.code==code]


def generated_paths(root):
    return [root/row.subject_id for row in checker_findings(root,"GENERATED_ARTIFACT")]

class RepositoryFixture:

    def __init__(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.write('src/vibeflow/__init__.py', '')
        for relative in ('repo_check', 'sandbox/python/minimal', 'sandbox/python/integration', 'sandbox/javascript/minimal', 'sandbox/javascript/integration', 'src/vibeflow/core/config', 'src/vibeflow/core/descriptors', 'src/vibeflow/targets/shared/quality_support', 'src/vibeflow/core/inspection', 'src/vibeflow/block_compiler', 'src/vibeflow/targets/python/project', 'src/vibeflow/targets/python/quality', 'src/vibeflow/targets/python/runtime', 'src/vibeflow/targets/javascript/frontend', 'src/vibeflow/targets/javascript/quality', 'src/vibeflow/targets/javascript/build', 'src/vibeflow/targets/javascript/resources', 'src/vibeflow/tooling/application', 'src/vibeflow/tooling/application/cli', 'src/vibeflow/tooling/application/javascript', 'src/vibeflow/tooling/application/python', 'src/vibeflow/tooling/application/python/project', 'src/vibeflow/tooling/application/python/presentation', 'src/vibeflow/tooling/presentation', 'src/vibeflow/tooling/project', 'tests/e2e', 'tests/e2e/cases', 'tests/e2e/applications', 'tests/e2e/browser', 'tests/e2e/runtime', 'distribution', 'distribution/docs', 'references', 'tools'):
            (self.root / relative).mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, source: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

class ProfileTests(unittest.TestCase):

    def setUp(self) -> None:
        self.fixture = RepositoryFixture()

    def tearDown(self) -> None:
        self.fixture.close()

    def codes(self, profile: str) -> list[str]:
        return [item.code for item in checker_report(self.fixture.root, profile).findings]

    def test_text_io_requires_explicit_encoding_at_public_check_entry(self) -> None:
        self.fixture.write('src/vibeflow/tooling/project/text.py', '\nfrom pathlib import Path as P\nimport io as streams\nimport subprocess as processes\nfrom tempfile import NamedTemporaryFile\nfrom gzip import open as compressed\npath = P("input.json")\npath.read_text()\npath.write_text("中文")\npath.open()\nopen("input.json")\nstreams.open("input.json", "w", encoding=None)\nstreams.TextIOWrapper(raw)\nNamedTemporaryFile(mode="w+t")\ncompressed("input.gz", "rt")\nprocesses.run(["node"], text=True)\nP.read_text(path)\npath.read_text(encoding="locale")\n')
        findings = [item for item in checker_report(self.fixture.root, 'base').findings if item.code == 'TEXT_ENCODING_UNSPECIFIED']
        self.assertEqual(len(findings), 11)
        self.assertEqual({item.source_location.line for item in findings}, set(range(8, 19)))
        self.assertTrue(all((item.subject_id.endswith('project/text.py') for item in findings)))
        self.assertTrue(all(('encoding="utf-8"' in item.suggested_fix for item in findings)))

    def test_text_io_accepts_formats_bytes_and_unrelated_open_methods(self) -> None:
        self.fixture.write('src/vibeflow/tooling/project/text.py', '\nfrom pathlib import Path\nfrom io import open as file_open\nimport subprocess\nimport tempfile\nimport gzip\nfrom vibeflow.targets.javascript import resources\npath = Path("input")\npath.read_text("utf-8")\npath.write_text("text", "utf-8")\npath.open("w", -1, "utf-8")\nopen("input", "r", -1, "gbk")\nfile_open("input", encoding="ascii")\nopen("input", "rb")\npath.open("wb")\ntempfile.NamedTemporaryFile()\ngzip.open("input.gz")\nsubprocess.run(["node"], text=True, encoding="utf-8")\nsubprocess.run(["node"], stdout=subprocess.PIPE)\nsession.open()\nsession.open("connection")\nresources.read_text("runtime_helpers.mjs")\nPath.read_text(path, encoding="utf-8")\n')
        self.assertNotIn('TEXT_ENCODING_UNSPECIFIED', self.codes('base'))

    def test_text_encoding_check_covers_owned_tools_without_auditing_fixtures(self) -> None:
        for name in ('tools/check.py', 'distribution/build.py', 'repo_check/src/checker.py'):
            self.fixture.write(name, 'open("data.json").read()\n')
        self.fixture.write('tests/encoding_fixture.py', 'open("legacy.txt").read()\n')
        self.fixture.write('sandbox/encoding_fixture.py', 'open("legacy.txt").read()\n')
        findings = [item for item in checker_report(self.fixture.root, 'base').findings if item.code == 'TEXT_ENCODING_UNSPECIFIED']
        self.assertEqual({item.subject_id for item in findings}, {'tools/check.py', 'distribution/build.py', 'repo_check/src/checker.py'})

    def test_directory_roles_reject_workdirs_and_audit_archives(self) -> None:
        self.fixture.write('dist/independent-review/result.json', '{}')
        self.fixture.write('archive/review-performance-observations.zip', 'audit')
        self.fixture.write('docs/maintainers/run.log', 'output')
        self.fixture.write('sandbox/rule_gaps/report.json', '{}')
        self.fixture.write('docs/maintainers/history/audits/case-index.json', '{}')
        self.fixture.write('docs/maintainers/history/audits/sandbox-task-inventory-20261010.json', '{}')
        subjects = {f.subject_id for f in checker_findings(self.fixture.root, 'DIRECTORY_ROLE')}
        self.assertIn('dist/independent-review', subjects)
        self.assertIn('archive/review-performance-observations.zip', subjects)
        self.assertIn('docs/maintainers/run.log', subjects)
        self.assertIn('sandbox/rule_gaps', subjects)
        self.assertIn('docs/maintainers/history/audits/case-index.json', subjects)
        self.assertIn('docs/maintainers/history/audits/sandbox-task-inventory-20261010.json', subjects)
        self.fixture.write('outputs/test-audit/table.xlsx', 'workbook')
        self.assertIn(self.fixture.root / 'outputs', generated_paths(self.fixture.root))

    def test_directory_roles_allow_releases_sources_and_document_assets(self) -> None:
        self.fixture.write('dist/README.md', 'latest releases only')
        self.fixture.write('archive/README.md', 'historical releases only')
        self.fixture.write('archive/history/README.md', 'historical build variants')
        self.fixture.write('dist/vibeflow-distribution/DISTRIBUTION.json', '{"version":"0.17.0"}')
        self.fixture.write('dist/vibeflow-distribution-0.17.0.zip', 'package')
        self.fixture.write('dist/SHA256SUMS-0.17.0.txt', 'hash')
        self.fixture.write('archive/history/old-build/vibeflow-distribution-0.15.1.zip', 'old')
        self.fixture.write('docs/assets/architecture.svg', 'image')
        self.fixture.write('docs/assets/architecture/table.xlsx', 'workbook')
        self.fixture.write('docs/maintainers/design.pdf', 'document')
        self.fixture.write('docs/maintainers/notes.txt', 'notes')
        self.fixture.write('docs/design/diagram.json', '{}')
        self.fixture.write('sandbox/python/domain_rules/input.json', '{}')
        self.fixture.write('tests/e2e/cases/reference.json', '{}')
        self.assertEqual(checker_findings(self.fixture.root, 'DIRECTORY_ROLE'), [])
        self.fixture.write('dist/vibeflow-distribution-0.15.2.zip', 'stale')
        self.assertEqual([f.subject_id for f in checker_findings(self.fixture.root, 'DIRECTORY_ROLE')], ['dist/vibeflow-distribution-0.15.2.zip'])

    def test_core_rejects_target_dependency(self) -> None:
        self.fixture.write('src/vibeflow/core/model.py', 'from vibeflow.targets.python import Runtime\n')
        self.assertIn('LAYER_DEPENDENCY', self.codes('core'))

    def test_coordination_protocol_stays_below_targets_and_tooling(self) -> None:
        self.fixture.write('src/vibeflow/coordination/server.py', 'from vibeflow.targets.python.runtime import PipelineRuntime\n')
        self.fixture.write('src/vibeflow/coordination/client.py', 'from vibeflow.tooling.application import cli\n')
        findings = checker_report(self.fixture.root, 'base').findings
        rejected = {item.subject_id for item in findings if item.code == 'LAYER_DEPENDENCY'}
        self.assertIn('vibeflow.coordination.server', rejected)
        self.assertIn('vibeflow.coordination.client', rejected)

    def test_coordination_launcher_can_dispatch_to_its_neutral_command_only(self) -> None:
        self.fixture.write('src/vibeflow/coordination/__main__.py', 'from vibeflow.tooling.application.coordination import main\n')
        self.assertNotIn('LAYER_DEPENDENCY', self.codes('base'))

    def test_core_rejects_filesystem_io(self) -> None:
        self.fixture.write('src/vibeflow/core/loader.py', "from pathlib import Path\n\ndef load():\n    return Path('x').read_text()\n")
        codes = self.codes('core')
        self.assertIn('CORE_IO_CALL', codes)

    def test_block_compiler_rejects_target_dependency(self) -> None:
        self.fixture.write('src/vibeflow/block_compiler/compile.py', 'from vibeflow.targets.javascript import emitter\n')
        self.assertIn('LAYER_DEPENDENCY', self.codes('block-compiler'))

    def test_targets_may_not_import_each_other(self) -> None:
        self.fixture.write('src/vibeflow/targets/python/wrong.py', 'from vibeflow.targets.javascript import emitter\n')
        self.fixture.write('src/vibeflow/targets/javascript/wrong.py', 'from vibeflow.targets.python import runtime\n')
        self.assertIn('LAYER_DEPENDENCY', self.codes('python-target'))
        self.assertIn('LAYER_DEPENDENCY', self.codes('javascript-target'))

    def test_import_graph_covers_function_and_type_checking_imports(self) -> None:
        self.fixture.write('src/vibeflow/core/hidden_imports.py', 'from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from vibeflow.targets.python import runtime\n\ndef load():\n    from vibeflow.targets.javascript import frontend\n    return frontend\n')
        findings = [item for item in checker_report(self.fixture.root, 'core').findings if item.code == 'LAYER_DEPENDENCY']
        self.assertEqual({item.details['target'] for item in findings}, {'vibeflow.targets.javascript', 'vibeflow.targets.python'})

    def test_import_graph_covers_fixed_dynamic_imports(self) -> None:
        self.fixture.write('src/vibeflow/core/dynamic_imports.py', 'import importlib as loader\nfrom importlib import import_module as load_module\n\ndef load():\n    loader.import_module("vibeflow.targets.python.runtime")\n    load_module("vibeflow.targets.javascript.frontend")\n    __import__("vibeflow.targets.python.project")\n')
        findings = [item for item in checker_report(self.fixture.root, 'core').findings if item.code == 'LAYER_DEPENDENCY' and item.details.get('import_kind') == 'dynamic']
        self.assertEqual({item.details['target'] for item in findings}, {'vibeflow.targets.javascript.frontend', 'vibeflow.targets.python.project', 'vibeflow.targets.python.runtime'})

    def test_python_application_reports_shortest_cross_target_path(self) -> None:
        self.fixture.write('src/vibeflow/tooling/application/python/runner.py', 'from vibeflow.tooling.project import long_path, short_path\n')
        self.fixture.write('src/vibeflow/tooling/project/long_path.py', 'from vibeflow.tooling.project import middle\n')
        self.fixture.write('src/vibeflow/tooling/project/middle.py', 'from vibeflow.targets.javascript import frontend\n')
        self.fixture.write('src/vibeflow/tooling/project/short_path.py', 'from vibeflow.targets.javascript import frontend\n')
        findings = [item for item in checker_report(self.fixture.root, 'python-target').findings if item.code == 'APPLICATION_CROSS_TARGET' and item.subject_id == 'vibeflow.tooling.application.python.runner']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details['dependency_path'], ['vibeflow.tooling.application.python.runner', 'vibeflow.tooling.project.short_path', 'vibeflow.targets.javascript'])

    def test_javascript_application_reports_transitive_python_path(self) -> None:
        self.fixture.write('src/vibeflow/tooling/application/javascript/build.py', 'from vibeflow.tooling.project import bridge\n')
        self.fixture.write('src/vibeflow/tooling/project/bridge.py', 'from vibeflow.targets.python import compiler\n')
        findings = [item for item in checker_report(self.fixture.root, 'javascript-target').findings if item.code == 'APPLICATION_CROSS_TARGET']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details['dependency_path'], ['vibeflow.tooling.application.javascript.build', 'vibeflow.tooling.project.bridge', 'vibeflow.targets.python'])

    def test_target_profile_reports_transitive_cross_target_path(self) -> None:
        self.fixture.write('src/vibeflow/targets/python/project/entry.py', 'from vibeflow.core import bridge\n')
        self.fixture.write('src/vibeflow/core/bridge.py', 'from vibeflow.targets.javascript import frontend\n')
        findings = [item for item in checker_report(self.fixture.root, 'python-target').findings if item.code == 'TRANSITIVE_LAYER_DEPENDENCY']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details['dependency_path'], ['vibeflow.targets.python.project.entry', 'vibeflow.core.bridge', 'vibeflow.targets.javascript'])

    def test_base_rejects_transitive_neutral_tooling_target_dependency(self) -> None:
        self.fixture.write('src/vibeflow/tooling/project/neutral.py', 'from vibeflow.tooling.project import helper\n')
        self.fixture.write('src/vibeflow/tooling/project/helper.py', 'def load():\n    from vibeflow.targets.python import runtime\n    return runtime\n')
        findings = [item for item in checker_report(self.fixture.root, 'base').findings if item.code == 'NEUTRAL_TARGET_DEPENDENCY' and item.subject_id == 'vibeflow.tooling.project.neutral']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details['dependency_path'], ['vibeflow.tooling.project.neutral', 'vibeflow.tooling.project.helper', 'vibeflow.targets.python'])

    def test_base_allows_explicit_target_application_boundary(self) -> None:
        self.fixture.write('src/vibeflow/tooling/application/cli/__init__.py', 'from vibeflow.tooling.application.javascript import cli\n')
        self.fixture.write('src/vibeflow/tooling/application/javascript/cli.py', 'from vibeflow.targets.javascript import build\n')
        findings = checker_report(self.fixture.root, 'base').findings
        self.assertFalse(any((item.code == 'NEUTRAL_TARGET_DEPENDENCY' and item.subject_id == 'vibeflow.tooling.application.cli' for item in findings)))

    def test_javascript_application_rejects_python_specific_symbol(self) -> None:
        self.fixture.write('src/vibeflow/tooling/application/javascript/build.py', 'from vibeflow.core import NodeRegistry\n')
        findings = checker_report(self.fixture.root, 'javascript-target').findings
        matched = [item for item in findings if item.code == 'JAVASCRIPT_APPLICATION_PYTHON_SYMBOL']
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0].details['symbol'], 'NodeRegistry')

    def test_javascript_profile_checks_mjs_syntax(self) -> None:
        self.fixture.write('src/vibeflow/targets/javascript/resources/broken.mjs', 'export const broken = ;\n')
        self.assertIn('JS_SYNTAX', self.codes('javascript-target'))

    def test_base_finds_syntax_and_generated_content(self) -> None:
        self.fixture.write('src/vibeflow/core/broken.py', 'def broken(:\n')
        (self.fixture.root / 'output').mkdir()
        codes = self.codes('base')
        self.assertIn('PY_SYNTAX', codes)
        self.assertIn('GENERATED_ARTIFACT', codes)

    def test_base_allows_formal_release_directories(self) -> None:
        (self.fixture.root / 'dist/vibeflow-distribution').mkdir(parents=True)
        (self.fixture.root / 'archive').mkdir()
        self.assertNotIn('GENERATED_ARTIFACT', self.codes('base'))

    def test_base_checks_document_links_without_rejecting_historical_release_text(self) -> None:
        self.fixture.write('docs/guide.md', 'VibeFlow 0.10.0 used [a missing guide](missing.md).\n')
        findings = checker_report(self.fixture.root, 'base').findings
        self.assertEqual({item.code for item in findings if item.subject_id == 'docs/guide.md'}, {'DOCUMENT_LINK_MISSING'})

    def test_document_links_support_line_numbers_and_ignore_inline_code(self) -> None:
        self.fixture.write('docs/source.py', 'value = 1\n')
        self.fixture.write('docs/guide.md', '[source](source.py:1) and `[x](1,2)`\n')
        self.assertNotIn('DOCUMENT_LINK_MISSING', self.codes('base'))

    def test_aot_manifest_name_does_not_match_removed_module(self) -> None:
        self.fixture.write('docs/guide.md', 'vibeflow.aot-build.v2\n')
        self.assertNotIn('STALE_DOCUMENTATION', self.codes('base'))
        self.fixture.write('docs/guide.md', 'vibeflow.aot.compiler\n')
        self.assertIn('STALE_DOCUMENTATION', self.codes('base'))

    def test_base_current_development_version_uses_project_metadata(self) -> None:
        for text in ('当前开发版本为 `0.16.0`，Workflow ABI 为 v4。\n', 'Current development package version: `0.16.0`. Workflow ABI: v4.\n'):
            with self.subTest(text=text):
                self.fixture.write('pyproject.toml', '[project]\nversion = "0.17.0"\n')
                self.fixture.write('README.md', text)
                findings = [finding for finding in checker_report(self.fixture.root, 'base').findings if finding.code == 'STALE_DOCUMENTATION']
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].details, {'version': '0.16.0', 'expected_version': '0.17.0', 'version_source': 'pyproject.toml'})
                self.assertIn('0.17.0', findings[0].suggested_fix)
                self.assertNotIn('0.15.0', findings[0].suggested_fix)
                self.fixture.write('pyproject.toml', '[project]\nversion = "0.16.0"\n')
                self.assertNotIn('STALE_DOCUMENTATION', self.codes('base'))

    def test_base_accepts_current_development_version_with_history_and_older_release(self) -> None:
        self.fixture.write('pyproject.toml', '[project]\nversion = "0.16.0"\n')
        self.fixture.write('README.md', '当前开发版本为 0.16.0；旧版 0.9.0、0.10.0 仅作历史对照。\nPreviously released package: vibeflow-distribution-0.15.2.zip.\n')
        self.fixture.write('README.en.md', 'Current development package version: 0.16.0.\nVibeFlow 0.10.0 used a different architecture.\n')
        self.assertNotIn('STALE_DOCUMENTATION', self.codes('base'))

    def test_base_checks_document_image_links(self) -> None:
        self.fixture.write('README.md', '![missing architecture](docs/assets/missing.svg)\n')
        self.assertIn('DOCUMENT_LINK_MISSING', self.codes('base'))

    def test_base_checks_english_readme(self) -> None:
        self.fixture.write('README.en.md', 'See [missing guide](docs/missing.md).\n')
        self.assertIn('DOCUMENT_LINK_MISSING', self.codes('base'))

    def test_base_rejects_removed_plan_references(self) -> None:
        self.fixture.write('docs/guide.md', 'See 15_长期工作流与原生IO改造计划.md for details.\n')
        self.assertIn('REMOVED_DOCUMENT_REFERENCE', self.codes('base'))

    def test_base_rejects_obsolete_documented_commands(self) -> None:
        self.fixture.write('docs/guide.md', 'python run.py compile-old --config project/configs/main.jsonc\n')
        findings = [item for item in checker_report(self.fixture.root, 'base').findings if item.code == 'STALE_DOCUMENT_COMMAND']
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].details['command'], 'compile-old')

    def test_base_accepts_current_launcher_and_module_commands(self) -> None:
        self.fixture.write('docs/guide.md', 'python run.py architecture --config project/configs/main.jsonc\nPYTHONPATH=src python -m vibeflow build --target node\nvibeflow quality-check --path project\n')
        self.assertNotIn('STALE_DOCUMENT_COMMAND', self.codes('base'))

    def test_base_finds_nested_sandbox_artifacts(self) -> None:
        (self.fixture.root / 'sandbox/python/integration/.artifacts').mkdir(parents=True)
        self.fixture.write('src/vibeflow/core/stray.pyc', 'compiled')
        findings = checker_report(self.fixture.root, 'base').findings
        subjects = {item.subject_id for item in findings}
        self.assertIn('sandbox/python/integration/.artifacts', subjects)
        self.assertIn('src/vibeflow/core/stray.pyc', subjects)

    def test_base_finds_all_root_zip_files_and_sandbox_builds(self) -> None:
        self.fixture.write('historical-release.zip', 'archive')
        (self.fixture.root / 'sandbox/javascript/integration/build').mkdir()
        subjects = {item.subject_id for item in checker_report(self.fixture.root, 'base').findings if item.code == 'GENERATED_ARTIFACT'}
        self.assertIn('historical-release.zip', subjects)
        self.assertIn('sandbox/javascript/integration/build', subjects)

    def test_base_requires_canonical_structure(self) -> None:
        (self.fixture.root / 'src/vibeflow/core/config').rmdir()
        findings = checker_report(self.fixture.root, 'base').findings
        self.assertTrue(any((item.code == 'MISSING_CANONICAL_DIRECTORY' and item.subject_id == 'src/vibeflow/core/config' for item in findings)))

    def test_base_rejects_root_api_exports(self) -> None:
        self.fixture.write('src/vibeflow/__init__.py', 'from vibeflow.core import WorkflowPlan\n')
        self.assertIn('ROOT_API_EXPORT', self.codes('base'))

    def test_base_rejects_legacy_repository_paths(self) -> None:
        (self.fixture.root / 'tests/unit').mkdir(parents=True)
        self.assertIn('LEGACY_REPOSITORY_PATH', self.codes('base'))

    def test_base_rejects_business_module_at_target_root(self) -> None:
        self.fixture.write('src/vibeflow/targets/python/runtime_bridge.py', 'VALUE = 1\n')
        self.assertIn('LAYER_ROOT_BUSINESS_MODULE', self.codes('base'))

    def test_base_scans_tooling_for_removed_imports(self) -> None:
        self.fixture.write('src/vibeflow/tooling/application/entry.py', 'from vibeflow.runtime import PipelineRuntime\n')
        self.assertIn('LAYER_DEPENDENCY', self.codes('base'))

    def test_javascript_quality_cannot_launch_processes(self) -> None:
        self.fixture.write('src/vibeflow/targets/javascript/quality/source.py', "import subprocess\n\ndef inspect():\n    subprocess.run(['node'])\n")
        self.assertIn('JAVASCRIPT_FRONTEND_PROCESS', self.codes('javascript-target'))

    def test_all_aggregates_base_and_layer_findings(self) -> None:
        self.fixture.write('src/vibeflow/core/wrong.py', 'import os\n')
        (self.fixture.root / 'output').mkdir()
        codes = self.codes('all')
        self.assertIn('CORE_IO_IMPORT', codes)
        self.assertIn('GENERATED_ARTIFACT', codes)

    def test_json_report_has_stable_envelope(self) -> None:
        report = checker_report(self.fixture.root, 'base')
        payload = json.loads(json.dumps(report.payload))
        self.assertEqual(payload['schema_version'], 'vibeflow.repository-quality.v1')
        self.assertEqual(payload['profile'], 'base')
        self.assertIn('summary', payload)
        self.assertIn('findings', payload)
