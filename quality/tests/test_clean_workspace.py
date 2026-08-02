from __future__ import annotations

import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPOSITORY_ROOT / "tools" / "clean_workspace.py"
SPEC = importlib.util.spec_from_file_location("clean_workspace_under_test", SCRIPT)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - invalid checkout
    raise RuntimeError(f"cannot load {SCRIPT}")
clean_workspace = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = clean_workspace
SPEC.loader.exec_module(clean_workspace)


class CleanerDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def mkdir(self, relative: str) -> Path:
        path = self.root / relative
        path.mkdir(parents=True, exist_ok=True)
        return path

    def test_discovers_recursive_and_sandbox_artifacts(self) -> None:
        self.mkdir("src/package/__pycache__")
        self.mkdir("sandbox/javascript/integration/build")
        self.mkdir("sandbox/python/integration/reports")
        self.mkdir("some-package.egg-info")
        self.mkdir(".agents")
        (self.root / "old-release.zip").write_bytes(b"zip")

        with mock.patch.object(clean_workspace, "ROOT", self.root):
            targets = clean_workspace.discover_targets()

        subjects = {target.path.relative_to(self.root).as_posix() for target in targets}
        self.assertIn("src/package/__pycache__", subjects)
        self.assertIn("sandbox/javascript/integration/build", subjects)
        self.assertIn("sandbox/python/integration/reports", subjects)
        self.assertIn("some-package.egg-info", subjects)
        self.assertIn(".agents", subjects)
        self.assertIn("old-release.zip", subjects)

    def test_prunes_protected_and_nonempty_metadata_directories(self) -> None:
        self.mkdir(".git/cache/__pycache__")
        self.mkdir("references/cache/__pycache__")
        self.mkdir("distribution/cache/node_modules")
        self.mkdir(".codex/cache/__pycache__")
        with mock.patch.object(clean_workspace, "ROOT", self.root):
            targets = clean_workspace.discover_targets()
        subjects = {target.path.relative_to(self.root).as_posix() for target in targets}
        self.assertEqual(subjects, {"distribution/cache/node_modules"})

    def test_validation_rejects_tracked_content(self) -> None:
        target = self.mkdir("build")
        tracked = target / "tracked.txt"
        tracked.write_text("source", encoding="utf-8")
        with mock.patch.object(clean_workspace, "ROOT", self.root):
            with self.assertRaisesRegex(RuntimeError, "tracked files"):
                clean_workspace.validate_targets(
                    [clean_workspace.CleanupTarget(target, "workspace")],
                    tracked=frozenset({tracked}),
                )

    def test_validation_allows_only_tracked_root_zip_release(self) -> None:
        release = self.root / "historical.zip"
        release.write_bytes(b"zip")
        nested = self.root / "nested" / "historical.zip"
        nested.parent.mkdir()
        nested.write_bytes(b"zip")
        with mock.patch.object(clean_workspace, "ROOT", self.root):
            validated = clean_workspace.validate_targets(
                [clean_workspace.CleanupTarget(release, "release")],
                tracked=frozenset({release}),
            )
            self.assertEqual(validated[0].path, release)
            with self.assertRaisesRegex(RuntimeError, "tracked files"):
                clean_workspace.validate_targets(
                    [clean_workspace.CleanupTarget(nested, "release")],
                    tracked=frozenset({nested}),
                )

    def test_removes_empty_legacy_directory_but_not_source(self) -> None:
        empty_legacy = self.mkdir("src/vibeflow/aot/__pycache__").parent
        populated_legacy = self.mkdir("src/vibeflow/runtime")
        (populated_legacy / "runtime.py").write_text("VALUE = 1\n", encoding="utf-8")
        with mock.patch.object(clean_workspace, "ROOT", self.root):
            targets = clean_workspace.discover_targets()
        subjects = {target.path.relative_to(self.root).as_posix() for target in targets}
        self.assertIn(empty_legacy.relative_to(self.root).as_posix(), subjects)
        self.assertNotIn(populated_legacy.relative_to(self.root).as_posix(), subjects)


class CleanerCliTests(unittest.TestCase):
    def test_default_is_dry_run(self) -> None:
        target = clean_workspace.CleanupTarget(
            REPOSITORY_ROOT / "tmp", "workspace"
        )
        with (
            mock.patch.object(clean_workspace, "discover_targets", return_value=(target,)),
            mock.patch.object(clean_workspace, "_tracked_paths", return_value=frozenset()),
            mock.patch.object(clean_workspace, "remove_targets") as remove,
            mock.patch("sys.stdout", new_callable=io.StringIO) as output,
        ):
            self.assertEqual(clean_workspace.main([]), 0)
        remove.assert_not_called()
        self.assertIn("WOULD_REMOVE", output.getvalue())

    def test_apply_removes_only_validated_plan(self) -> None:
        target = clean_workspace.CleanupTarget(
            REPOSITORY_ROOT / "tmp", "workspace"
        )
        with (
            mock.patch.object(clean_workspace, "discover_targets", return_value=(target,)),
            mock.patch.object(clean_workspace, "_tracked_paths", return_value=frozenset()),
            mock.patch.object(clean_workspace, "remove_targets") as remove,
            mock.patch("sys.stdout", new_callable=io.StringIO),
        ):
            self.assertEqual(clean_workspace.main(["--apply"]), 0)
        remove.assert_called_once_with((target,))


if __name__ == "__main__":
    unittest.main()
