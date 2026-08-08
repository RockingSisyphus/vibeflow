from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from xml.etree import ElementTree


_SOURCE_SANDBOX_ROOT = Path(__file__).resolve().parent
_REPOSITORY_ROOT = _SOURCE_SANDBOX_ROOT.parents[2]
_RUNTIME_TEMP: tempfile.TemporaryDirectory[str] | None = None


def _prepare_runtime_workspace() -> Path:
    global _RUNTIME_TEMP
    if "--help" in sys.argv or "-h" in sys.argv:
        return _SOURCE_SANDBOX_ROOT
    keep_artifacts = "--keep-artifacts" in sys.argv
    if keep_artifacts:
        runtime_root = _SOURCE_SANDBOX_ROOT / ".artifacts"
        if runtime_root.exists():
            shutil.rmtree(runtime_root)
        runtime_root.mkdir(parents=True)
    else:
        _RUNTIME_TEMP = tempfile.TemporaryDirectory(
            prefix="vibeflow-typescript-sandbox-"
        )
        runtime_root = Path(_RUNTIME_TEMP.name)
    shutil.copytree(
        _SOURCE_SANDBOX_ROOT / "project",
        runtime_root / "project",
        ignore=shutil.ignore_patterns(
            "node_modules", "__pycache__", "*.pyc", ".artifacts", "reports"
        ),
    )
    shutil.copy2(_SOURCE_SANDBOX_ROOT / "outside.ts", runtime_root / "outside.ts")
    symlink_specs = json.loads(
        (
            runtime_root
            / "project/negative/symlinks.json"
        ).read_text(encoding="utf-8")
    )
    for spec in symlink_specs:
        link = runtime_root / "project" / str(spec["path"])
        target = runtime_root / "project" / str(spec["target"])
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
    for name in ("vibeflow_config.jsonc", "vibeflow_host_config.jsonc"):
        shutil.copy2(_SOURCE_SANDBOX_ROOT / name, runtime_root / name)
    try:
        completed = subprocess.run(
            ["npm", "ci"],
            cwd=runtime_root / "project",
            check=False,
            text=True,
        )
    except FileNotFoundError as exc:
        raise SystemExit("ENVIRONMENT ERROR: npm is not available") from exc
    if completed.returncode != 0:
        raise SystemExit(
            f"ENVIRONMENT ERROR: npm ci failed with status {completed.returncode}"
        )
    os.environ["VIBEFLOW_SANDBOX_RUNTIME_ROOT"] = str(runtime_root)
    return runtime_root


_RUNTIME_ROOT = _prepare_runtime_workspace()

from sandbox_support import (
    BuildCache,
    CONFIG_ROOT,
    DEFAULT_PUPPETEER_ROOT,
    PROJECT_ROOT,
    assert_deterministic,
    assert_equal,
    diagnostic_codes,
    execute_cases,
    expect_build_failure,
    prepare_temporary_puppeteer,
    run_browser,
    skip_case,
    validate_environment,
    write_report,
)
from vibeflow.targets.javascript.frontend.errors import AotBuildError
from vibeflow.tooling.application.javascript.build import (
    ProjectBuildError,
    ProjectBuildRequest,
    build_project_aot,
)

from advanced_cases import (
    detached_case,
    edge_role_case,
    execution_model_case,
    loop_max_error_case,
    nested_async_case,
    nested_override_case,
    runtime_error_case,
)
from declaration_cases import (
    typecheck_capability_declarations,
    typecheck_declarations,
    typecheck_optional_declarations,
)
from host_extension_cases import (
    browser_permanent_port_host_case,
    host_extension_case,
    permanent_port_host_case,
)
from plugin_cases import (
    build_plugin_hook_case,
    plugin_manifest_case,
    runtime_plugin_concurrent_isolation_case,
    runtime_plugin_repeat_case,
)
from runtime_cases import (
    async_capability_case,
    branch_case,
    capability_error_case,
    capability_isolation_case,
    concurrent_trace_case,
    fanout_case,
    import_case,
    input_error_case,
    linear_case,
    loop_case,
    loop_stop_when_case,
    nodeset_case,
    optional_input_case,
    port_math_case,
    repeat_case,
)


_BASE64_VLQ = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _decode_vlq(segment: str) -> list[int]:
    values: list[int] = []
    value = 0
    shift = 0
    for character in segment:
        try:
            digit = _BASE64_VLQ.index(character)
        except ValueError as exc:
            raise AssertionError(f"invalid source-map VLQ: {character!r}") from exc
        value |= (digit & 31) << shift
        if digit & 32:
            shift += 5
            continue
        values.append(-(value >> 1) if value & 1 else value >> 1)
        value = 0
        shift = 0
    if shift:
        raise AssertionError(f"unterminated source-map VLQ segment: {segment!r}")
    return values


def _mapped_sources(payload: dict[str, Any]) -> set[str]:
    sources = [str(item) for item in payload.get("sources", ())]
    mapped: set[str] = set()
    source_index = 0
    for line in str(payload.get("mappings", "")).split(";"):
        for segment in line.split(","):
            if not segment:
                continue
            fields = _decode_vlq(segment)
            if len(fields) == 1:
                continue
            if len(fields) not in {4, 5}:
                raise AssertionError(
                    f"invalid source-map segment field count: {segment!r}"
                )
            source_index += fields[1]
            if source_index < 0 or source_index >= len(sources):
                raise AssertionError(
                    f"source-map index {source_index} is out of bounds"
                )
            mapped.add(sources[source_index])
    return mapped


def _manifest_case(cache: BuildCache, *, key: str, profile: str) -> dict[str, Any]:
    result = cache.build(key, "linear.jsonc", profile=profile)
    manifest = json.loads(result.manifest.read_text(encoding="utf-8"))
    assert_equal(manifest["profile"], profile, label="manifest profile")
    assert_equal(manifest["target"], "node", label="manifest target")
    lock_path = PROJECT_ROOT / "package-lock.json"
    lock_digest = hashlib.sha256()
    lock_digest.update(b"package-lock.json\0")
    lock_digest.update(lock_path.read_bytes())
    lock_digest.update(b"\0")
    installed_typescript = json.loads(
        (PROJECT_ROOT / "node_modules/typescript/package.json").read_text(
            encoding="utf-8"
        )
    )["version"]
    installed_esbuild = json.loads(
        (PROJECT_ROOT / "node_modules/esbuild/package.json").read_text(
            encoding="utf-8"
        )
    )["version"]
    node_version = subprocess.run(
        ["node", "--eval", "process.stdout.write(process.versions.node)"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    expected_toolchain = {
        "node": node_version,
        "typescript": installed_typescript,
        "esbuild": installed_esbuild,
        "lock_sha256": lock_digest.hexdigest(),
        "lock_files": ["package-lock.json"],
    }
    assert_equal(
        manifest["toolchain"],
        expected_toolchain,
        label="manifest toolchain identity",
    )
    assert_equal(
        result.build.toolchain.to_dict(),
        expected_toolchain,
        label="builder toolchain identity",
    )
    for relative, expected_hash in manifest["files"].items():
        actual_hash = hashlib.sha256(
            (result.out_dir / relative).read_bytes()
        ).hexdigest()
        assert_equal(actual_hash, expected_hash, label=f"hash for {relative}")
    expected = {
        "workflow.js" if profile == "esm-module" else "index.js",
        "workflow.d.ts" if profile == "esm-module" else "index.d.ts",
        "workflow.js.map" if profile == "esm-module" else "index.js.map",
        "vibeflow-build.json",
    }
    assert_equal(set(result.files), expected, label=f"{profile} files")
    return {
        "profile": profile,
        "files": list(result.files),
        "toolchain": expected_toolchain,
    }


def _source_map_case(result: Any) -> dict[str, Any]:
    maps = sorted(result.out_dir.rglob("*.map"))
    sources: set[str] = set()
    mapped_sources: set[str] = set()
    for path in maps:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not payload.get("mappings"):
            raise AssertionError(f"source map has empty mappings: {path.name}")
        sources.update(str(item) for item in payload.get("sources", ()))
        mapped_sources.update(_mapped_sources(payload))
    for expected in (
        "base_lib/math.ts",
        "nodes/add.ts",
        "nodes/subtract.ts",
    ):
        assert any(expected in item for item in sources), (
            expected,
            sorted(sources),
        )
        assert any(expected in item for item in mapped_sources), (
            f"{expected} has no mapping segment",
            sorted(mapped_sources),
        )
    return {
        "maps": len(maps),
        "sourceCount": len(sources),
        "mappedSourceCount": len(mapped_sources),
    }


def _review_case(puppeteer_root: Path) -> dict[str, Any]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(_REPOSITORY_ROOT / "src")
    environment["VIBEFLOW_MERMAID_RENDERER_ROOT"] = str(puppeteer_root)
    specs = (
        ("nodeset.jsonc", "NODESET_ARCHITECTURE.jsonc", {"sandbox.arithmetic_nodeset"}),
        (
            "nested_async.jsonc",
            "NESTED_ASYNC_ARCHITECTURE.jsonc",
            {"sandbox.nested_async_outer", "sandbox.nested_async_inner"},
        ),
        (
            "browser_permanent_port_host.jsonc",
            "PERMANENT_PORT_ARCHITECTURE.jsonc",
            {"sandbox.permanent_port_body"},
        ),
    )
    reviewed: dict[str, Any] = {}
    for config_name, architecture_name, expected_targets in specs:
        output = _RUNTIME_ROOT / "reports" / f"{Path(config_name).stem}.expanded.svg"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "vibeflow",
                "review",
                "--workspace",
                str(_RUNTIME_ROOT / "vibeflow_config.jsonc"),
                "--config",
                str(CONFIG_ROOT / config_name),
                "--output",
                str(output),
            ],
            cwd=_RUNTIME_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(completed.stderr or completed.stdout)
        payload = json.loads(completed.stdout)
        if payload.get("status") != "PASS" or payload.get("published") is not True:
            raise AssertionError(payload)
        root = ElementTree.parse(output).getroot()
        coverage = {
            element.attrib.get("data-review-target", "")
            for element in root.iter()
            if "review-inline-fragment" in element.attrib.get("class", "").split()
        }
        missing = expected_targets - coverage
        if missing:
            raise AssertionError(
                f"review {config_name} is missing expanded targets: {sorted(missing)}"
            )
        architecture = PROJECT_ROOT / "review_artifacts" / architecture_name
        architecture_text = architecture.read_text(encoding="utf-8")
        for target in expected_targets:
            if target not in architecture_text:
                raise AssertionError(
                    f"Architecture {architecture_name} is missing {target}"
                )
        reviewed[config_name] = {
            "bytes": output.stat().st_size,
            "coverage": sorted(coverage),
        }
    return reviewed


def _single_file_case(result: Any) -> dict[str, Any]:
    companions = [
        path.relative_to(result.out_dir).as_posix()
        for path in result.out_dir.rglob("*.js")
        if path != result.entry
    ]
    assert_equal(companions, [], label="single-esm companion chunks")
    return {"entry": result.entry.name, "companionChunks": companions}


def _web_profile_case(cache: BuildCache) -> dict[str, Any]:
    result = cache.build(
        "linear_web",
        "linear.jsonc",
        target="browser",
        profile="web-app",
        html_template=PROJECT_ROOT / "web/index.template.html",
        app_entry=PROJECT_ROOT / "web/app.ts",
    )
    assert_equal(
        set(result.files),
        {
            "index.html",
            "index.js",
            "index.js.map",
            "workflow.d.ts",
            "vibeflow-build.json",
        },
        label="web-app files",
    )
    return {"files": list(result.files)}


def _atomic_failure_case(cache: BuildCache) -> dict[str, Any]:
    valid = cache.build("atomic_target", "linear.jsonc")
    before = {
        path.relative_to(valid.out_dir).as_posix(): path.read_bytes()
        for path in valid.out_dir.rglob("*")
        if path.is_file()
    }
    try:
        build_project_aot(
            ProjectBuildRequest(
                workspace=PROJECT_ROOT.parent / "vibeflow_config.jsonc",
                config=CONFIG_ROOT / "negative/direct_node_import.jsonc",
                out_dir=valid.out_dir,
                target="node",
                profile="single-esm",
                replace=True,
            )
        )
    except (AotBuildError, ProjectBuildError) as exc:
        codes = diagnostic_codes(exc)
        assert "VF_IMPORT_NODE_TO_NODE" in codes, sorted(codes)
    else:
        raise AssertionError("invalid replacement build unexpectedly succeeded")
    after = {
        path.relative_to(valid.out_dir).as_posix(): path.read_bytes()
        for path in valid.out_dir.rglob("*")
        if path.is_file()
    }
    assert_equal(after, before, label="failed build preserved old output")
    return {"preservedFiles": len(after)}


def _negative_cases(cache: BuildCache) -> list[tuple[str, Any]]:
    expected = {
        "direct_node_import": "VF_IMPORT_NODE_TO_NODE",
        "undeclared_base_lib": "VF_IMPORT_BASE_LIB",
        "dynamic_import": "VF_IMPORT_DYNAMIC",
        "runtime_import": "VF_IMPORT_OWNER",
        "node_builtin_browser": "VF_ESBUILD",
        "immediate_async": "VF_COMPLETION_IMMEDIATE_PROMISE",
        "suspend_sync": "VF_COMPLETION_SUSPEND_NON_PROMISE",
        "unowned_promise": "VF_PROMISE_UNOWNED",
        "suspend_in_sync": "VF_ENTRY_MODE_SUSPEND_IN_SYNC",
        "task_in_sync": "VF_ENTRY_MODE_TASK_IN_SYNC",
        "barrel_import": "VF_IMPORT_NODE_TO_NODE",
        "alias_import": "VF_IMPORT_NODE_TO_NODE",
        "symlink_import": "VF_IMPORT_NODE_TO_NODE",
        "base_lib_reverse": "VF_IMPORT_LAYER",
        "undeclared_external": "VF_IMPORT_EXTERNAL",
        "package_root_escape": "VF_IMPORT_PACKAGE_ROOT",
        "dynamic_code": "VF_IMPORT_DYNAMIC_CODE",
        # The helper itself is outside the declared Node/base_lib ownership
        # closure, so VibeFlow rejects that architectural violation before
        # esbuild reaches the platform-specific node:fs import.
        "indirect_node_builtin": "VF_IMPORT_OWNER",
        "module_promise": "VF_IMPORT_SIDE_EFFECT",
        "discarded_promise": "VF_PROMISE_UNOWNED",
        "long_lived_listener": "VF_NODE_LONG_LIVED_LISTENER",
        "global_state": "VF_MODULE_STATE",
    }
    precise = {
        "barrel_import": (
            "sandbox.invalid.barrel_import",
            "node",
            "negative/barrels/math.ts",
            '"../../nodes/math.ts"',
        ),
        "alias_import": (
            "sandbox.invalid.alias_import",
            "node",
            "negative/nodes/alias_import.ts",
            '"#forbidden-node"',
        ),
        "symlink_import": (
            "sandbox.invalid.symlink_import",
            "node",
            "negative/nodes/symlink_import.ts",
            '"../links/math.ts"',
        ),
        "base_lib_reverse": (
            "sandbox.negative.reverse",
            "base_lib",
            "negative/base_lib/reverse.ts",
            '"../../nodes/math.ts"',
        ),
        "undeclared_external": (
            "sandbox.invalid.undeclared_external",
            "node",
            "negative/nodes/undeclared_external.ts",
            '"typescript"',
        ),
        "package_root_escape": (
            "sandbox.invalid.package_root_escape",
            "node",
            "negative/nodes/package_root_escape.ts",
            '"../../../outside.ts"',
        ),
        "dynamic_code": (
            "sandbox.invalid.dynamic_code",
            "node",
            "negative/nodes/dynamic_code.ts",
            "eval",
        ),
        "module_promise": (
            "sandbox.invalid.module_promise",
            "node",
            "negative/nodes/module_promise.ts",
            "const ready",
        ),
        "discarded_promise": (
            "sandbox.invalid.discarded_promise",
            "node",
            "negative/nodes/discarded_promise.ts",
            "void Promise",
        ),
        "long_lived_listener": (
            "sandbox.invalid.long_lived_listener",
            "node",
            "negative/nodes/long_lived_listener.ts",
            "addEventListener",
        ),
        "global_state": (
            "sandbox.invalid.global_state",
            "node",
            "negative/nodes/global_state.ts",
            "count +=",
        ),
    }
    cases: list[tuple[str, Any]] = []
    for name, code in expected.items():
        precise_expectation = precise.get(name)
        expected_location = (
            _source_marker_location(
                PROJECT_ROOT / precise_expectation[2],
                precise_expectation[3],
            )
            if precise_expectation is not None
            else None
        )
        cases.append(
            (
                f"reject:{name}",
                lambda name=name,
                code=code,
                precise_expectation=precise_expectation,
                expected_location=expected_location: expect_build_failure(
                    lambda: cache.build(
                        f"negative_{name}",
                        f"negative/{name}.jsonc",
                        target="browser",
                    ),
                    expected_code=code,
                    expected_owner_id=(
                        precise_expectation[0]
                        if precise_expectation is not None
                        else None
                    ),
                    expected_owner_kind=(
                        precise_expectation[1]
                        if precise_expectation is not None
                        else None
                    ),
                    expected_file=(
                        PROJECT_ROOT / precise_expectation[2]
                        if precise_expectation is not None
                        else None
                    ),
                    expected_line=(
                        expected_location[0]
                        if expected_location is not None
                        else None
                    ),
                    expected_column=(
                        expected_location[1]
                        if expected_location is not None
                        else None
                    ),
                ),
            )
        )
    return cases


def _source_marker_location(path: Path, marker: str) -> tuple[int, int]:
    source = path.read_text(encoding="utf-8")
    offset = source.index(marker)
    previous_newline = source.rfind("\n", 0, offset)
    return source.count("\n", 0, offset) + 1, offset - previous_newline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build and run the VibeFlow TypeScript integration sandbox."
    )
    parser.add_argument(
        "--puppeteer-root",
        type=Path,
        default=None,
        help="use an existing Puppeteer installation instead of the temporary one",
    )
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="preserve the copied project, toolchain, builds, and reports in .artifacts",
    )
    args = parser.parse_args()
    try:
        puppeteer_root = (
            args.puppeteer_root.resolve()
            if args.puppeteer_root is not None
            else (
                DEFAULT_PUPPETEER_ROOT
                if args.skip_browser
                else prepare_temporary_puppeteer(_RUNTIME_ROOT / "puppeteer")
            )
        )
        validate_environment(
            puppeteer_root=puppeteer_root,
            skip_browser=args.skip_browser,
        )
    except EnvironmentError as exc:
        print(f"ENVIRONMENT ERROR: {exc}")
        return 2

    if args.keep_artifacts:
        build_root = _RUNTIME_ROOT / "builds"
        build_root.mkdir(parents=True)
        build_context = nullcontext(str(build_root))
    else:
        build_context = tempfile.TemporaryDirectory(prefix="vibeflow-ts-builds-")
    with build_context as raw:
        cache = BuildCache(Path(raw))
        module = lambda: cache.build(
            "linear_module", "linear.jsonc", profile="esm-module"
        )
        single = lambda: cache.build("linear_single", "linear.jsonc")
        optional_input = lambda: cache.build(
            "optional_input", "optional_input.jsonc"
        )
        fanout = lambda: cache.build("fanout", "fanout_join.jsonc")
        edge_roles = lambda: cache.build("edge_roles", "edge_roles.jsonc")
        branch = lambda: cache.build("branch", "branch_join.jsonc")
        nodeset = lambda: cache.build("nodeset", "nodeset.jsonc")
        loop = lambda: cache.build("loop", "loop.jsonc")
        loop_stop_when = lambda: cache.build(
            "loop_stop_when", "loop_stop_when.jsonc"
        )
        loop_max_failure = lambda: cache.build(
            "loop_max_failure", "loop_max_failure.jsonc"
        )
        async_capability = lambda: cache.build(
            "async_capability", "async_capability.jsonc"
        )
        detached = lambda: cache.build("detached", "detached.jsonc")
        port_math = lambda: cache.build("port_math", "port_math.jsonc")
        nested_override = lambda: cache.build(
            "nested_override", "nested_override.jsonc"
        )
        nested_async = lambda: cache.build(
            "nested_async", "nested_async.jsonc"
        )
        runtime_node_failure = lambda: cache.build(
            "runtime_node_failure", "runtime_node_failure.jsonc"
        )
        runtime_output_failure = lambda: cache.build(
            "runtime_output_failure", "runtime_output_failure.jsonc"
        )
        plugins = lambda: cache.build("plugins", "plugins.jsonc")
        cases: list[tuple[str, Any]] = [
            ("review:javascript-expanded-parity", lambda: _review_case(puppeteer_root)),
            ("profile:esm-module", lambda: _manifest_case(
                cache, key="linear_module", profile="esm-module"
            )),
            ("profile:single-esm", lambda: _manifest_case(
                cache, key="linear_single", profile="single-esm"
            )),
            ("profile:web-app", lambda: _web_profile_case(cache)),
            ("host-extension:lifecycle-and-capability", lambda: host_extension_case(cache)),
            ("host-extension:async-permanent-port-cleanup",
             lambda: permanent_port_host_case(cache)),
            ("plugin:manifest-and-planned", lambda: plugin_manifest_case(
                plugins()
            )),
            ("plugin:policy-compiler-hooks", lambda: build_plugin_hook_case(
                plugins()
            )),
            ("plugin:runtime-repeat", lambda: runtime_plugin_repeat_case(
                plugins()
            )),
            (
                "plugin:runtime-concurrent-isolation",
                lambda: runtime_plugin_concurrent_isolation_case(plugins()),
            ),
            (
                "execution:sync-async-taskplan-metadata",
                lambda: execution_model_case(
                    module(),
                    async_capability(),
                    detached(),
                ),
            ),
            ("abi:import-no-side-effect", lambda: import_case(module().entry)),
            ("math:linear-base-lib", lambda: linear_case(module().entry)),
            ("abi:optional-input", lambda: optional_input_case(
                optional_input().entry
            )),
            ("abi:repeat-isolation", lambda: repeat_case(module().entry)),
            ("abi:concurrent-trace-isolation", lambda: concurrent_trace_case(
                module().entry
            )),
            ("abi:input-and-trace-errors", lambda: input_error_case(
                module().entry
            )),
            ("math:fanout-all-join", lambda: fanout_case(fanout().entry)),
            ("routes:schedule-transfer-split", lambda: edge_role_case(
                edge_roles()
            )),
            ("branch:any-active-positive", lambda: branch_case(
                branch().entry, 4, "non-negative:4"
            )),
            ("branch:any-active-negative", lambda: branch_case(
                branch().entry, -3, "negative:-3"
            )),
            ("nodeset:nested-math", lambda: nodeset_case(nodeset().entry)),
            ("nodeset:nested-qualified-override", lambda: nested_override_case(
                nested_override().entry
            )),
            ("nodeset:nested-deferred-detached", lambda: nested_async_case(
                nested_async()
            )),
            ("loop:bounded-carry", lambda: loop_case(loop().entry)),
            ("loop:stop-when-carry-collect", lambda: loop_stop_when_case(
                loop_stop_when().entry
            )),
            ("loop:max-iterations-error", lambda: loop_max_error_case(
                loop_max_failure().entry
            )),
            ("async:promise-and-capability", lambda: async_capability_case(
                async_capability().entry
            )),
            ("capability:concurrent-isolation", lambda: capability_isolation_case(
                async_capability().entry
            )),
            ("capability:missing-and-cancel", lambda: capability_error_case(
                async_capability().entry
            )),
            ("async:detached-cleanup-and-timeout", lambda: detached_case(
                detached().entry
            )),
            ("io:receive-node-base-lib-send", lambda: port_math_case(
                port_math().entry
            )),
            ("error:node-cause-and-path", lambda: runtime_error_case(
                runtime_node_failure().entry,
                workflow_id="runtime_node_failure",
                expected_code="VF_NODE_FAILED",
                expected_cause="sandbox node exploded",
            )),
            ("error:output-schema-and-path", lambda: runtime_error_case(
                runtime_output_failure().entry,
                workflow_id="runtime_output_failure",
                expected_code="VF_OUTPUT_SCHEMA",
            )),
            ("build:source-map-origins", lambda: _source_map_case(single())),
            ("build:single-esm-no-chunks", lambda: _single_file_case(single())),
            ("build:deterministic", lambda: assert_deterministic(
                single().out_dir,
                cache.build("linear_single_repeat", "linear.jsonc").out_dir,
            )),
            ("build:atomic-failure-preserves-output", lambda: _atomic_failure_case(
                cache
            )),
        ]
        if not args.skip_browser:
            cases.extend(
                [
                    (
                        "browser:no-auto-start",
                        lambda: run_browser(
                            cache.build(
                                "linear_web",
                                "linear.jsonc",
                                target="browser",
                                profile="web-app",
                                html_template=(
                                    PROJECT_ROOT / "web/index.template.html"
                                ),
                                app_entry=PROJECT_ROOT / "web/app.ts",
                            ).out_dir,
                            puppeteer_root=puppeteer_root,
                            expected="15",
                        ),
                    ),
                    (
                        "browser:permanent-host-web-app",
                        lambda: browser_permanent_port_host_case(
                            cache,
                            puppeteer_root=puppeteer_root,
                            profile="web-app",
                        ),
                    ),
                    (
                        "browser:permanent-host-esm-module",
                        lambda: browser_permanent_port_host_case(
                            cache,
                            puppeteer_root=puppeteer_root,
                            profile="esm-module",
                        ),
                    ),
                ]
            )
        else:
            cases.extend(
                (
                    name,
                    lambda: skip_case("disabled with --skip-browser"),
                )
                for name in (
                    "browser:no-auto-start",
                    "browser:permanent-host-web-app",
                    "browser:permanent-host-esm-module",
                )
            )
        cases.append(
            (
                "types:strict-consumer",
                lambda: typecheck_declarations(module()),
            )
        )
        cases.append(
            (
                "types:optional-input-consumer",
                lambda: typecheck_optional_declarations(optional_input()),
            )
        )
        cases.append(
            (
                "types:capability-consumer",
                lambda: typecheck_capability_declarations(async_capability()),
            )
        )
        cases.extend(_negative_cases(cache))
        results = execute_cases(cases)

    write_report(results)
    if args.keep_artifacts:
        print(f"sandbox artifacts: {_RUNTIME_ROOT}")
    failed = [item for item in results if item.status == "FAIL"]
    passed = sum(item.status == "PASS" for item in results)
    skipped = sum(item.status == "SKIP" for item in results)
    print(
        "TypeScript sandbox: "
        f"total={len(results)} passed={passed} failed={len(failed)} "
        f"skipped={skipped}"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
