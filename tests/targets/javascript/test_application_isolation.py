from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
JAVASCRIPT_SANDBOX = REPOSITORY_ROOT / "sandbox/javascript/minimal"
from tools.verify_project import _PYTHON_ISOLATION_NODES as PYTHON_ISOLATION_NODES, _isolation_declarations


def _blocked_import_finder_source(prefixes: tuple[str, ...]) -> str:
    return textwrap.dedent(
        f"""
        import importlib.abc
        import sys

        BLOCKED_PREFIXES = {prefixes!r}

        class BlockedTargetFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if any(
                    fullname == prefix or fullname.startswith(prefix + ".")
                    for prefix in BLOCKED_PREFIXES
                ):
                    raise ModuleNotFoundError(
                        f"target isolation blocked {{fullname}}",
                        name=fullname,
                    )
                return None

        sys.meta_path.insert(0, BlockedTargetFinder())
        """
    )


def _run_import_guard(
    script: str,
    *,
    arguments: tuple[str | Path, ...] = (),
) -> None:
    root = REPOSITORY_ROOT
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = str(root / "src")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            *(str(item) for item in arguments),
        ],
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _javascript_fixture(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    shutil.copytree(
        JAVASCRIPT_SANDBOX / "project",
        project,
        ignore=shutil.ignore_patterns("node_modules", ".artifacts", "__pycache__"),
    )
    shutil.copy2(JAVASCRIPT_SANDBOX / "vibeflow_config.jsonc", tmp_path)
    toolchain_root = Path(
        os.environ.get(
            "VIBEFLOW_TEST_TOOLCHAIN_ROOT",
            str(JAVASCRIPT_SANDBOX / "project"),
        )
    ).resolve()
    dependencies = toolchain_root / "node_modules"
    if not (dependencies / "typescript").is_dir() or not (
        dependencies / "esbuild"
    ).is_dir():
        pytest.skip(
            "JavaScript isolation build needs the locked TypeScript/esbuild "
            "toolchain; tools/verify_project.py provisions it"
        )
    (project / "node_modules").symlink_to(dependencies, target_is_directory=True)
    return tmp_path / "vibeflow_config.jsonc", project / "configs/greeting.jsonc"


def test_javascript_build_import_does_not_load_python_application_or_target() -> None:
    _run_import_guard(
        "import sys; "
        "import vibeflow.tooling.application.javascript.build; "
        "bad=sorted(name for name in sys.modules "
        "if name == 'vibeflow.targets.python' "
        "or name.startswith('vibeflow.targets.python.') "
        "or name == 'vibeflow.tooling.application.python' "
        "or name.startswith('vibeflow.tooling.application.python.')); "
        "assert not bad, bad"
    )


def test_javascript_review_import_does_not_load_python_application_or_target() -> None:
    _run_import_guard(
        "import sys; "
        "import vibeflow.tooling.application.javascript.audit; "
        "import vibeflow.tooling.application.javascript.review; "
        "bad=sorted(name for name in sys.modules "
        "if name == 'vibeflow.targets.python' "
        "or name.startswith('vibeflow.targets.python.') "
        "or name == 'vibeflow.tooling.application.python' "
        "or name.startswith('vibeflow.tooling.application.python.')); "
        "assert not bad, bad"
    )


def test_neutral_build_dispatch_does_not_load_python_application_or_target() -> None:
    _run_import_guard(
        "import sys; "
        "from vibeflow.tooling.application.cli import main; "
        "\ntry: main(['build', '--help'])\n"
        "except SystemExit as exc: assert exc.code == 0\n"
        "bad=sorted(name for name in sys.modules "
        "if name == 'vibeflow.targets.python' "
        "or name.startswith('vibeflow.targets.python.') "
        "or name == 'vibeflow.tooling.application.python' "
        "or name.startswith('vibeflow.tooling.application.python.')); "
        "assert not bad, bad"
    )


def test_neutral_run_dispatch_does_not_load_javascript_application_or_target() -> None:
    _run_import_guard(
        "import sys; "
        "from vibeflow.tooling.application.cli import main; "
        "\ntry: main(['run', '--help'])\n"
        "except SystemExit as exc: assert exc.code == 0\n"
        "bad=sorted(name for name in sys.modules "
        "if name == 'vibeflow.targets.javascript' "
        "or name.startswith('vibeflow.targets.javascript.') "
        "or name == 'vibeflow.tooling.application.javascript' "
        "or name.startswith('vibeflow.tooling.application.javascript.')); "
        "assert not bad, bad"
    )


def test_javascript_prepare_and_build_succeed_when_python_target_is_blocked(
    tmp_path: Path,
) -> None:
    workspace, config = _javascript_fixture(tmp_path)
    output = tmp_path / "aot"
    script = _blocked_import_finder_source(
        (
            "vibeflow.targets.python",
            "vibeflow.tooling.application.python",
        )
    ) + textwrap.dedent(
        """
        from pathlib import Path
        import sys

        from vibeflow.tooling.application.javascript.build import (
            ProjectBuildRequest,
            build_project_aot,
            prepare_project_build,
        )

        request = ProjectBuildRequest(
            workspace=Path(sys.argv[1]),
            config=Path(sys.argv[2]),
            out_dir=Path(sys.argv[3]),
            target="node",
            profile="single-esm",
        )
        prepared = prepare_project_build(request)
        assert prepared.plan.workflow_id
        result = build_project_aot(request)
        assert result.entry.is_file()
        assert result.manifest.is_file()
        assert not [
            name for name in sys.modules
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in BLOCKED_PREFIXES
            )
        ]
        """
    )
    _run_import_guard(script, arguments=(workspace, config, output))


def test_python_application_run_succeeds_when_javascript_target_is_blocked(
    tmp_path: Path,
) -> None:
    script = _blocked_import_finder_source(
        (
            "vibeflow.targets.javascript",
            "vibeflow.tooling.application.javascript",
        )
    ) + f"NODE_SOURCE = {PYTHON_ISOLATION_NODES!r}\nDECLARATIONS = {_isolation_declarations()!r}\n" + textwrap.dedent(
        r'''
        import importlib.util
        import json
        from pathlib import Path
        import sys

        from vibeflow.targets.python.project import NodeRegistry
        from vibeflow.tooling.application.python.runner import run_checked

        root = Path(sys.argv[1])
        root.mkdir(parents=True, exist_ok=True)
        node_path = root / "isolation_nodes.py"
        node_path.write_text(
            NODE_SOURCE,
            encoding="utf-8",
        )
        spec = importlib.util.spec_from_file_location("isolation_nodes", node_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        registry = NodeRegistry()
        from vibeflow.tooling.project.descriptor_parser import parse_descriptor_manifest
        for data in DECLARATIONS:
            descriptor = parse_descriptor_manifest(data)
            registry.register(descriptor, getattr(module, data["implementations"][0]["source"]["export"]))

        config = root / "workflow.jsonc"
        config.write_text(json.dumps({
            "pipeline": {
                "nodes": [
                    {"id": "start", "type_used": "isolation.start", "display_name": "Start", "description": "Starts the isolation workflow."},
                    {"id": "seed", "type_used": "isolation.seed", "display_name": "Seed", "description": "Produces the isolation result.", "value": 7},
                    {"id": "end", "type_used": "isolation.end", "display_name": "End", "description": "Consumes the isolation result."},
                ],
                "edges": [["start", "seed"], ["seed", "end"]],
                "outputs": [{"type": "value.out", "cardinality": "exactly_one", "display_name": "Result"}],
            }
        }), encoding="utf-8")
        result = run_checked(
            config,
            registry=registry,
            run_root=root / "runs",
            run_id="target-isolation",
        )
        assert result.context is not None
        assert result.context.get("value.out")["value"] == 7
        assert not [
            name for name in sys.modules
            if any(
                name == prefix or name.startswith(prefix + ".")
                for prefix in BLOCKED_PREFIXES
            )
        ]
        '''
    )
    _run_import_guard(script, arguments=(tmp_path / "python-run",))
