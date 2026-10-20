#!/usr/bin/env python3
"""Run the reproducible VibeFlow repository verification gate."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    # ``python tools/verify_project.py`` puts only ``tools/`` on sys.path.
    # The full gate also reuses repository-owned Sandbox test helpers, which
    # are deliberately not packaged in the wheel.
    sys.path.insert(0, str(ROOT))
from tools.test_parallel import DEFAULT_WORKERS, add_worker_argument
from tools.pytest_workdirs import external_scratch
from tools.audit_retired_architecture import RETIRED_FILES, MOVED_FILES
PYTHON = sys.executable
TEST_GROUPS = (
    "tests/core",
    "tests/block_compiler",
    "tests/targets",
    "tests/tooling",
    "tests/conformance",
    "tests/coordination",
    "tests/integration",
)


class VerificationError(RuntimeError):
    """A verification step could not complete successfully."""


@dataclass(frozen=True)
class Step:
    name: str
    action: Callable[[Path], None]


def _environment(
    overrides: dict[str, str | None] | None = None,
) -> dict[str, str]:
    environment = os.environ.copy()
    source = str(ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source if not existing else os.pathsep.join((source, existing))
    )
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    for key, value in (overrides or {}).items():
        if value is None:
            environment.pop(key, None)
        else:
            environment[key] = value
    return environment


def _run(
    command: Sequence[str | Path],
    *,
    cwd: Path = ROOT,
    overrides: dict[str, str | None] | None = None,
) -> None:
    normalized = tuple(str(item) for item in command)
    print(f"$ {shlex.join(normalized)}", flush=True)
    subprocess.run(
        normalized,
        cwd=cwd,
        env=_environment(overrides),
        check=True,
    )


def _repository_quality(_scratch: Path) -> None:
    _run((PYTHON, "repo_check/run.py", "--profile", "all"))


def _compileall(scratch: Path) -> None:
    compile_root = scratch / "compile-source"
    ignored = shutil.ignore_patterns(
        "__pycache__",
        ".pytest_cache",
        ".artifacts",
        "node_modules",
        "*.pyc",
        "*.pyo",
    )
    for name in ("src", "tests", "sandbox", "repo_check", "tools", "distribution"):
        source = ROOT / name
        if source.exists():
            shutil.copytree(source, compile_root / name, ignore=ignored)
    _run(
        (PYTHON, "-m", "compileall", "-q", str(compile_root)),
        cwd=compile_root,
        overrides={"PYTHONPATH": None},
    )


def _pytest(scratch: Path, *, with_renderer: bool = False, workers: int = DEFAULT_WORKERS) -> None:
    _run(
        (
            PYTHON,
            "tools/run_tests.py",
            "--workers", str(workers),
            "--scratch",
            scratch / "pytest",
            "--",
            *(ROOT / item for item in TEST_GROUPS if (ROOT / item).exists()),
        ),
        overrides={"VIBEFLOW_MERMAID_RENDERER_ROOT": str(_puppeteer_root(scratch))}
        if with_renderer else None,
    )


def _python_sandbox(_scratch: Path) -> None:
    _run((PYTHON, "sandbox/python/integration/run_all.py"))


def _javascript_minimal(_scratch: Path) -> None:
    _run((PYTHON, "sandbox/javascript/minimal/run_e2e.py"))


def _puppeteer_root(scratch: Path) -> Path:
    root = scratch / "puppeteer"
    if (root / "node_modules/puppeteer").is_dir():
        return root
    root.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copy2(ROOT / "tools/mermaid-renderer" / name, root / name)
    _run(("npm", "ci"), cwd=root)
    if not (root / "node_modules/puppeteer").is_dir():
        raise VerificationError("Puppeteer was not installed by the renderer lockfile")
    return root


def _javascript_integration(scratch: Path) -> None:
    _run(
        (
            PYTHON,
            "sandbox/javascript/integration/run_all.py",
            "--puppeteer-root",
            _puppeteer_root(scratch),
        )
    )


def _rule_regressions(scratch: Path, *, workers: int = DEFAULT_WORKERS) -> None:
    toolchain = scratch / "pytest/javascript-toolchain"
    commands = (
        (PYTHON, "tests/fixtures/rule_parity/run_all.py", "--workers", str(workers), "--current-only", "--toolchain", toolchain,
         "--work", scratch / "rule-parity", "--report", scratch / "rule-parity.json"),
        (PYTHON, "tests/fixtures/rule_gaps/run_all.py", "--workers", str(workers), "--toolchain", toolchain,
         "--renderer", _puppeteer_root(scratch), "--work", scratch / "rule-gaps", "--report", scratch / "rule-gaps.json"),
    )
    failures = []
    for command in commands:
        try:
            _run(command)
        except (subprocess.CalledProcessError, VerificationError) as error:
            failures.append(str(error))
    if failures:
        raise VerificationError("rule sandbox failures: " + "; ".join(failures))


def _runtime_observation_browser(scratch: Path) -> None:
    """Exercise onStatus in an actual browser; Python/Node cases run in pytest."""
    _run((PYTHON, "-c", """
import json
from pathlib import Path
import sys
from sandbox.javascript.runtime_observation.probe import observe_browser
work, toolchain, renderer, report = map(Path, sys.argv[1:])
work.mkdir(parents=True, exist_ok=True)
result = observe_browser(work, toolchain, renderer)
report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\\n')
if not result['matched']:
    raise SystemExit('browser runtime observation mismatch')
""", scratch / "runtime-observation-browser", scratch / "pytest/javascript-toolchain",
          _puppeteer_root(scratch), scratch / "runtime-observation-browser.json"))


def _javascript_review_performance(scratch: Path) -> None:
    _run((PYTHON, "tests/fixtures/javascript/review_performance/run_all.py",
          "--work", scratch / "javascript-review-performance", "--report", scratch / "javascript-review-performance.json",
          "--toolchain", scratch / "pytest/javascript-toolchain"))


def _review_performance_regressions(scratch: Path) -> None:
    _run((PYTHON, "tests/fixtures/python/review_performance/run_all.py",
          "--work", scratch / "review-performance", "--report", scratch / "review-performance.json",
          "--renderer", _puppeteer_root(scratch)))


def _review_layout_regressions(scratch: Path) -> None:
    _run((PYTHON, "tests/fixtures/python/review_layout/run_all.py",
          "--work", scratch / "review-layout", "--report", scratch / "review-layout.json",
          "--renderer", _puppeteer_root(scratch)))


def _resource_sections_regressions(scratch: Path) -> None:
    _run((PYTHON, "tests/fixtures/python/resource_sections/run_all.py",
          "--work", scratch / "python-resource-sections", "--report", scratch / "python-resource-sections.json",
          "--renderer", _puppeteer_root(scratch)))
    _run((PYTHON, "tests/fixtures/javascript/resource_sections/run_all.py",
          "--work", scratch / "javascript-resource-sections", "--report", scratch / "javascript-resource-sections.json",
          "--renderer", _puppeteer_root(scratch), "--toolchain", scratch / "pytest/javascript-toolchain"))


def _adaptation_regressions(scratch: Path, *, workers: int = DEFAULT_WORKERS) -> None:
    _run((PYTHON, "tests/fixtures/adaptation_regressions/run_all.py", "--workers", str(workers),
          "--toolchain", scratch / "pytest/javascript-toolchain", "--renderer", _puppeteer_root(scratch),
          "--work", scratch / "adaptation-regressions", "--report", scratch / "adaptation-regressions.json"))


def _venv_python(root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return root / relative


_PYTHON_ISOLATION_NODES = """
class StartNode:
    def run_pure(self, inputs, params):
        return {}

class SeedNode:
    def run_pure(self, inputs, params):
        return {"value.out": params["value"]}

class EndNode:
    def run_pure(self, inputs, params):
        return {}
""".strip() + "\n"


def _isolation_declarations() -> list[dict[str, object]]:
    declarations = []
    for key, symbol, kind in (("start", "StartNode", "terminal"), ("seed", "SeedNode", "process"), ("end", "EndNode", "terminal")):
        contract = {}
        if key == "seed":
            contract = {"provides": [{"key": "value.out", "type": "value.out", "display_name": "Result"}],
                        "output_semantics": {"value.out": ["Isolation result"]},
                        "params_schema": {"value": {"type": "number"}}, "params_defaults": {"value": 7}}
        elif key == "end":
            contract = {"requires": [{"type": "value.out", "cardinality": "exactly_one", "display_name": "Result"}],
                        "input_semantics": {"value.out": ["Isolation result"]}}
        declarations.append({"kind": "node", "type_key": "isolation." + key, "display_name": key.title(),
             "description": "Isolated " + key + " implementation.", "version": "1.0.0",
            "flow_kind": kind, "rulesets": ["vibeflow.process"], "contract": contract,
            "implementations": [{"language": "python", "targets": ["python"], "source": {"kind": "file", "ref": "isolation_nodes.py", "export": symbol}}]})
    return declarations


def _blocked_import_finder_source(prefixes: tuple[str, ...]) -> str:
    return f"""
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


def _javascript_cli_isolation_probe() -> str:
    return _blocked_import_finder_source(
        (
            "vibeflow.targets.python",
            "vibeflow.tooling.application.python",
        )
    ) + """
import os
from pathlib import Path
import sys

from vibeflow.tooling.application.cli import main

out_dir = Path(os.environ["VF_ISOLATION_JS_OUT"])
status = main([
    "build",
    "--workspace", os.environ["VF_ISOLATION_JS_WORKSPACE"],
    "--config", os.environ["VF_ISOLATION_JS_CONFIG"],
    "--target", "node",
    "--profile", "single-esm",
    "--out-dir", str(out_dir),
])
assert status == 0, status
assert (out_dir / "index.js").is_file()
assert (out_dir / "vibeflow-build.json").is_file()
assert not [
    name for name in sys.modules
    if any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in BLOCKED_PREFIXES
    )
]
"""


def _python_cli_isolation_probe() -> str:
    return (
        _blocked_import_finder_source(
            (
                "vibeflow.targets.javascript",
                "vibeflow.tooling.application.javascript",
            )
        )
        + f"NODE_SOURCE = {_PYTHON_ISOLATION_NODES!r}\n"
        + f"DECLARATIONS = {_isolation_declarations()!r}\n"
        + r'''
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["VF_ISOLATION_PYTHON_ROOT"])
root.mkdir(parents=True, exist_ok=True)
project_config = root / "vibeflow_project.jsonc"
project_config.write_text(json.dumps({
    "project_target": "python",
}), encoding="utf-8")
workspace = root / "vibeflow_config.jsonc"
workspace.write_text(json.dumps({
    "roots": [{"id": "python-isolation", "path": "."}],
}), encoding="utf-8")
node_path = root / "isolation_nodes.py"
node_path.write_text(NODE_SOURCE, encoding="utf-8")
plugin_source = "from vibeflow.targets.python.sdk import Plugin,node,SourceLocator\n"
resources = []
for index, descriptor in enumerate(DECLARATIONS):
    options = dict(descriptor)
    options.pop("kind")
    implementation = options.pop("implementations")[0]
    options["source"] = implementation["source"]
    resource = "resource_" + str(index)
    resources.append(resource)
    plugin_source += resource + "=node(**" + repr(options) + ")\n"
plugin_source += "plugin=Plugin(id='isolation',resources=[" + ",".join(resources) + "])\n"
(root / "plugin.py").write_text(plugin_source, encoding="utf-8")

config = root / "workflow.jsonc"
config.write_text(json.dumps({
    "plugins": [{"source": {"kind": "file", "ref": "plugin.py"}}],
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

from vibeflow.tooling.application.cli import main

status = main([
    "run",
    "--workspace", str(workspace),
    "--config", str(config),
    "--run-root", str(root / "runs"),
    "--run-id", "wheel-target-isolation",
])
assert status == 0, status
assert (root / "runs/wheel-target-isolation/output_summary.json").is_file()
# The installed wheel must build and run a source-free Python AOT artifact.
import shutil
import subprocess
from vibeflow.tooling.application.python import load_bundle
bundle_path = root.with_name(root.name + "-aot")
assert main(["build", "--workspace", str(workspace), "--config", str(config),
             "--out-dir", str(bundle_path)]) == 0
result = load_bundle(bundle_path).run({}, run_root=root.parent / "wheel-aot-runs",
                                      runtime_options={"execution": "compiled", "trace": "off"})
assert result.context.get("value.out")["value"] == 7
shutil.rmtree(root)
environment = dict(os.environ)
environment.pop("PYTHONPATH", None)
subprocess.run([sys.executable, "-B", str(bundle_path / "run.py"), "run",
                "--runtime-profile", "train", "--run-root", str(root.parent / "standalone-runs")],
               cwd=root.parent, env=environment, check=True)
assert not [
    name for name in sys.modules
    if any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in BLOCKED_PREFIXES
    )
]
'''
    )


def _wheel_smoke(scratch: Path) -> None:
    source_root = scratch / "wheel-source"
    package_root = source_root / "src" / "vibeflow"
    package_root.parent.mkdir(parents=True)
    shutil.copytree(
        ROOT / "src" / "vibeflow",
        package_root,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    for name in ("pyproject.toml", "LICENSE", "MANIFEST.in"):
        shutil.copy2(ROOT / name, source_root / name)

    shutil.copy2(ROOT / "src/vibeflow_build.py", source_root / "src/vibeflow_build.py")
    shutil.copytree(ROOT / "tools/workflow-viewer", source_root / "tools/workflow-viewer")
    sdist_root = scratch / "source-dist"
    _run(
        (PYTHON, "-m", "build", "--sdist", "--outdir", sdist_root),
        cwd=source_root,
        overrides={"PYTHONPATH": None},
    )
    archives = sorted(sdist_root.glob("vibeflow-*.tar.gz"))
    if len(archives) != 1:
        raise VerificationError(f"sdist build produced {len(archives)} matching artifacts")
    unpacked = scratch / "sdist-unpacked"
    with tarfile.open(archives[0]) as archive:
        archive.extractall(unpacked, filter="data")
    wheel_root = scratch / "wheel-dist"
    _run(
        (PYTHON, "-m", "build", "--wheel", "--outdir", wheel_root),
        cwd=next(unpacked.iterdir()),
        overrides={"PYTHONPATH": None},
    )
    wheels = sorted(wheel_root.glob("vibeflow-*.whl"))
    if len(wheels) != 1:
        raise VerificationError(
            f"wheel build produced {len(wheels)} matching artifacts"
        )

    environment_root = scratch / "wheel-venv"
    _run((PYTHON, "-m", "venv", environment_root))
    isolated = _venv_python(environment_root)
    _run(
        (isolated, "-m", "pip", "install", "--no-deps", wheels[0]),
        overrides={"PYTHONPATH": None},
    )
    probe = "\n".join(
        (
            "from importlib.resources import files",
            "import vibeflow",
            "assert tuple(getattr(vibeflow, '__all__', ())) == ()",
            "from vibeflow.core import GraphConfig",
            "from vibeflow.block_compiler import WorkflowPlan",
            "from vibeflow.targets.python.project import NodeRegistry",
            "from vibeflow.targets.python.runtime import PipelineRuntime",
            "from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset",
            "from vibeflow.targets.javascript import JavascriptBindingPlan",
            "from vibeflow.targets.python.rules.plugin import builtin_plugin",
            "assert builtin_plugin().contributions().resources",
            "from vibeflow.tooling.project.config_loader import load_config_document",
            "root = files('vibeflow')",
            f"for retired in {(*RETIRED_FILES, *MOVED_FILES)!r}:",
            "    assert not root.joinpath(retired).is_file(), retired",
            "for name in ('config.schema.json', 'health_report.schema.json', 'node.schema.json', 'nodeset.schema.json', 'policy.schema.json', 'rule.schema.json', 'ruleset.schema.json'):",
            "    assert root.joinpath('tooling/project/schema', name).is_file()",
            "for name in ('runtime_helpers.mjs', 'capability_helpers.mjs', 'plugin_helpers.mjs', 'root_helpers.mjs', 'coordination/workflow_client.mjs', 'coordination/workflow_host.mjs', 'coordination/workflow_node.mjs', 'toolchain_driver.mjs', 'plugin_worker.mjs', 'plugin_abi.d.ts', 'rule_abi.d.ts', 'sdk.mjs', 'sdk.d.ts', 'sdk_loader.mjs'):",
            "    assert root.joinpath('targets/javascript/resources', name).is_file()",
            "for name in ('declarations.mjs', 'contracts.d.ts'):",
            "    assert root.joinpath('targets/javascript/nodetypes', name).is_file()",
            "for removed in ('aot', 'runtime', 'portable', 'config', 'health', 'purity', 'devtools', 'rendering', 'workspace', 'builtin', 'core/quality'):",
            "    assert not root.joinpath(removed).is_dir(), removed",
        )
    )
    _run((isolated, "-c", probe), overrides={"PYTHONPATH": None})
    _run((isolated, "-m", "vibeflow", "--help"), overrides={"PYTHONPATH": None})

    javascript_fixture = scratch / "wheel-isolation-javascript"
    javascript_project = javascript_fixture / "project"
    shutil.copytree(
        ROOT / "sandbox/javascript/minimal/project",
        javascript_project,
        ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", "*.pyc", "*.pyo", ".artifacts"
        ),
    )
    shutil.copy2(
        ROOT / "sandbox/javascript/minimal/vibeflow_config.jsonc",
        javascript_fixture,
    )
    prepared_toolchain = scratch / "pytest/javascript-toolchain/node_modules"
    if prepared_toolchain.is_dir():
        (javascript_project / "node_modules").symlink_to(
            prepared_toolchain,
            target_is_directory=True,
        )
    else:
        _run(("npm", "ci"), cwd=javascript_project, overrides={"PYTHONPATH": None})
    _run(
        (isolated, "-c", _javascript_cli_isolation_probe()),
        cwd=javascript_fixture,
        overrides={
            "PYTHONPATH": None,
            "VF_ISOLATION_JS_WORKSPACE": str(
                javascript_fixture / "vibeflow_config.jsonc"
            ),
            "VF_ISOLATION_JS_CONFIG": str(
                javascript_project / "configs/greeting.jsonc"
            ),
            "VF_ISOLATION_JS_OUT": str(
                scratch / "wheel-isolation-javascript-output"
            ),
        },
    )
    _run(
        (isolated, "-c", _python_cli_isolation_probe()),
        overrides={
            "PYTHONPATH": None,
            "VF_ISOLATION_PYTHON_ROOT": str(
                scratch / "wheel-isolation-python"
            ),
        },
    )


def _distribution_smoke(scratch: Path) -> None:
    collaborative = scratch / "distribution"
    autonomous = scratch / "distribution-autonomous"
    archive_dir = scratch / "archives"
    _run(
        (
            PYTHON,
            "distribution/build.py",
            "--output-dir",
            collaborative,
            "--autonomous-output-dir",
            autonomous,
            "--archive-dir",
            archive_dir,
        ),
        overrides={"PYTHONPATH": None},
    )
    for expected_profile, output in (
        ("collaborative", collaborative),
        ("autonomous", autonomous),
    ):
        launcher = output / "run.py"
        _run((PYTHON, launcher, "verify-kernel"), overrides={"PYTHONPATH": None})
        metadata = json.loads((output / "DISTRIBUTION.json").read_text(encoding="utf-8"))
        if metadata.get("development_profile") != expected_profile:
            raise VerificationError(f"wrong distribution profile metadata: {metadata}")
        title = (output / "README.md").read_text(encoding="utf-8").splitlines()[0]
        if not title.startswith(f"# VibeFlow {metadata['version']} "):
            raise VerificationError(f"distribution README version does not match metadata: {title}")
        _run(
            (
                PYTHON,
                launcher,
                "validate",
                "--config",
                output / "python_project/configs/main.jsonc",
                "--json",
            ),
            overrides={"PYTHONPATH": None},
        )

    for relative in ("python_project", "javascript_project"):
        left = {
            path.relative_to(collaborative / relative): path.read_bytes()
            for path in (collaborative / relative).rglob("*")
            if path.is_file()
        }
        right = {
            path.relative_to(autonomous / relative): path.read_bytes()
            for path in (autonomous / relative).rglob("*")
            if path.is_file()
        }
        if left != right:
            raise VerificationError(f"profile project templates differ: {relative}")
    kernel_hashes = {
        hashlib.sha256((output / "kernel/vibeflow-kernel.zip").read_bytes()).hexdigest()
        for output in (collaborative, autonomous)
    }
    if len(kernel_hashes) != 1:
        raise VerificationError("profile kernel ZIPs are not byte-identical")

    python_run_root = scratch / "distribution-python-runs"
    _run(
        (
            PYTHON,
            collaborative / "run.py",
            "run",
            "--config",
            collaborative / "python_project/configs/main.jsonc",
            "--input",
            collaborative / "python_project/probe_input.json",
            "--run-root",
            python_run_root,
            "--run-id",
            "distribution-probe",
        ),
        overrides={"PYTHONPATH": None},
    )
    javascript_project = collaborative / "javascript_project"
    _run(("npm", "ci"), cwd=javascript_project, overrides={"PYTHONPATH": None})
    _run(
        (
            PYTHON,
            collaborative / "run.py",
            "build",
            "--config",
            javascript_project / "configs/main.jsonc",
            "--target",
            "node",
            "--profile",
            "esm-module",
            "--out-dir",
            javascript_project / "build/node",
        ),
        overrides={"PYTHONPATH": None},
    )
    _run(
        ("node", javascript_project / "scripts/workflow_execution_probe.mjs"),
        cwd=collaborative,
        overrides={"PYTHONPATH": None},
    )

    archives = sorted(archive_dir.glob("vibeflow-distribution-*.zip"))
    if len(archives) != 2:
        raise VerificationError(f"expected two distribution archives, found {archives}")
    for index, archive in enumerate(archives):
        extracted = scratch / f"distribution-extracted-{index}"
        shutil.unpack_archive(archive, extracted)
        _run(
            (PYTHON, extracted / "vibeflow-distribution/run.py", "verify-kernel"),
            overrides={"PYTHONPATH": None},
        )
        distribution_root = extracted / "vibeflow-distribution"
        bundle = scratch / f"python-aot-from-profile-{index}"
        input_path = scratch / f"python-aot-input-{index}.json"
        shutil.copy2(distribution_root / "python_project/probe_input.json", input_path)
        _run((PYTHON, distribution_root / "run.py", "build",
              "--config", distribution_root / "python_project/configs/main.jsonc",
              "--out-dir", bundle), cwd=scratch, overrides={"PYTHONPATH": None})
        api_probe = "\n".join((
            "import sys,json",
            f"sys.path.insert(0, {str(distribution_root / 'kernel/vibeflow-kernel.zip')!r})",
            "from vibeflow.tooling.application.python import load_bundle",
            f"bundle=load_bundle({str(bundle)!r})",
            f"initial=json.loads(open({str(input_path)!r}).read())",
            f"result=bundle.run(initial,run_root={str(scratch / f'aot-api-runs-{index}')!r},runtime_options={{'execution':'compiled','trace':'off'}})",
            "assert result.health.status not in {'FAIL','ERROR'},result.health",
            "assert result.context is not None",
        ))
        _run((PYTHON, "-B", "-c", api_probe), cwd=scratch, overrides={"PYTHONPATH": None})
        # No original extracted framework/project remains available to run.py.
        shutil.rmtree(extracted)
        _run((PYTHON, "-B", bundle / "run.py", "run", "--input", input_path,
              "--runtime-profile", "train", "--run-root", scratch / f"aot-cli-runs-{index}"),
             cwd=scratch, overrides={"PYTHONPATH": None})
    return
def _cleanup_generated_artifacts(_scratch: Path) -> None:
    """Remove only artifacts produced by earlier full-gate steps.

    The repository quality profile intentionally rejects caches and generated
    output.  Some subprocesses exercised by pytest create Python caches even
    when the parent gate disables bytecode generation, so the release smoke
    must cross the same explicit cleanup boundary used by contributors before
    it asks the distribution builder to self-check the source tree.
    """

    _run((PYTHON, "tools/clean_workspace.py", "--apply"))


def _clean_tree_check(_scratch: Path) -> None:
    command = (PYTHON, "tools/clean_workspace.py")
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=_environment(),
        check=False,
        capture_output=True,
        text=True,
    )
    print(f"$ {shlex.join(command)}", flush=True)
    print(completed.stdout, end="")
    if completed.returncode:
        print(completed.stderr, end="", file=sys.stderr)
        raise VerificationError("workspace cleanup preview was refused")
    if "cleanup targets: 0" not in completed.stdout:
        raise VerificationError("verification left repository artifacts behind")


def _steps(*, full: bool, workers: int = DEFAULT_WORKERS) -> tuple[Step, ...]:
    base = (
        Step("repository-quality", _repository_quality),
        Step("compileall", _compileall),
        Step("pytest", lambda scratch: _pytest(scratch, with_renderer=full, workers=workers)),
    )
    if not full:
        return base
    return (
        *base,
        Step("python-sandbox", _python_sandbox),
        Step("javascript-minimal", _javascript_minimal),
        Step("javascript-integration", _javascript_integration),
        Step("rule-regressions", lambda scratch: _rule_regressions(scratch, workers=workers)),
        Step("runtime-observation-browser", _runtime_observation_browser),
        Step("review-layout-regressions", _review_layout_regressions),
        Step("resource-sections-regressions", _resource_sections_regressions),
        Step("review-performance-regressions", _review_performance_regressions),
        Step("javascript-review-performance", _javascript_review_performance),
        Step("adaptation-regressions", lambda scratch: _adaptation_regressions(scratch, workers=workers)),
        Step("wheel-isolation", _wheel_smoke),
        Step("generated-artifact-cleanup", _cleanup_generated_artifacts),
        Step("distribution", _distribution_smoke),
        Step("repository-quality-final", _repository_quality),
        Step("clean-tree", _clean_tree_check),
    )


def _run_steps(steps: Sequence[Step], *, scratch: Path) -> None:
    observations = []
    failures = []
    for index, step in enumerate(steps, start=1):
        print(f"\n[{index}/{len(steps)}] {step.name}", flush=True)
        started = perf_counter()
        try:
            step.action(scratch)
        except (OSError, subprocess.CalledProcessError, VerificationError) as exc:
            failure = f"{step.name} failed: {exc}"
            failures.append(failure)
            observations.append({'step':step.name,'status':'failed','error':str(exc),
                                 'seconds':perf_counter()-started})
            print(failure, file=sys.stderr, flush=True)
        else:
            observations.append({'step':step.name,'status':'passed','seconds':perf_counter()-started})
            print(f"PASS: {step.name}", flush=True)
        (scratch/'verification.json').write_text(json.dumps({'steps':observations,'failures':failures},indent=2)+'\n')
    if failures:
        raise VerificationError('\n'.join(failures))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    add_worker_argument(parser)
    parser.add_argument("--full", action="store_true", help="include Sandboxes and packaging")
    parser.add_argument(
        "--scratch",
        type=Path,
        help="use a caller-owned scratch directory outside the repository",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.scratch is not None:
            try:
                scratch = external_scratch(args.scratch, ROOT)
            except ValueError as exc:
                parser.error(str(exc))
            scratch.mkdir(parents=True, exist_ok=True)
            _run_steps(_steps(full=args.full, workers=args.workers), scratch=scratch)
        else:
            with tempfile.TemporaryDirectory(prefix="vibeflow-verify-") as raw:
                _run_steps(_steps(full=args.full, workers=args.workers), scratch=Path(raw))
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("VibeFlow verification: PASS")
    return 0


if __name__ == "__main__":
    if __package__:
        from .process_supervision import entrypoint
    else:
        from process_supervision import entrypoint
    raise SystemExit(entrypoint(Path(__file__), sys.argv[1:], main))
