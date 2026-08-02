"""Real TypeScript dependency-closure failures with stable diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil

import pytest

from vibeflow.targets.javascript.build import BuildRequest, build_aot
from vibeflow.targets.javascript.frontend.errors import AotBuildError


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOOLCHAIN_ROOT = Path(
    os.environ.get(
        "VIBEFLOW_TEST_TOOLCHAIN_ROOT",
        str(REPOSITORY_ROOT / "sandbox/javascript/minimal/project"),
    )
).resolve()


@dataclass(frozen=True)
class NegativeCase:
    name: str
    code: str
    diagnostic_file: str
    marker: str
    sources: dict[str, str]
    owners: tuple[dict[str, str], ...]
    entry_mode: str = "sync"
    completion: str = "immediate"
    node_base_libs: dict[str, list[str]] | None = None


def _project(tmp_path: Path) -> Path:
    if not (TOOLCHAIN_ROOT / "node_modules/typescript").is_dir():
        pytest.skip("the TypeScript sandbox toolchain has not been installed")
    project = tmp_path / "project"
    project.mkdir()
    package = json.loads(
        (TOOLCHAIN_ROOT / "package.json").read_text(encoding="utf-8")
    )
    package["imports"] = {"#forbidden-node": "./other.ts"}
    (project / "package.json").write_text(
        json.dumps(package),
        encoding="utf-8",
    )
    shutil.copy2(
        TOOLCHAIN_ROOT / "package-lock.json",
        project / "package-lock.json",
    )
    (project / "node_modules").symlink_to(
        TOOLCHAIN_ROOT / "node_modules",
        target_is_directory=True,
    )
    return project


def _plan(entry: Path, *, entry_mode: str, completion: str) -> dict[str, object]:
    return {
        "abi_version": "vibeflow.workflow.v2",
        "workflow_id": "test.project-negative",
        "entry_mode": entry_mode,
        "inputs": [],
        "outputs": [],
        "nodes": [
            {
                "id": "run",
                "type_used": "test.entry",
                "implementation": {
                    "kind": "file",
                    "ref": str(entry),
                    "export": "run",
                    "completion": completion,
                },
                "requires": [],
                "provides": [],
                "flow_kind": "terminal",
                "is_terminal": True,
                "completion": completion,
            }
        ],
        "routes": [],
        "order": ["run"],
        "max_steps": 5,
    }


def _line_column(source: str, marker: str) -> tuple[int, int]:
    offset = source.index(marker)
    line = source.count("\n", 0, offset) + 1
    previous = source.rfind("\n", 0, offset)
    return line, offset - previous


CASES = (
    NegativeCase(
        name="barrel",
        code="VF_IMPORT_NODE_TO_NODE",
        diagnostic_file="barrel.ts",
        marker='"./other.ts"',
        sources={
            "entry.ts": 'import { forbidden } from "./barrel.ts";\nexport function run() { void forbidden; return {}; }\n',
            "barrel.ts": 'export { forbidden } from "./other.ts";\n',
            "other.ts": "export const forbidden = 1;\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
            {"path": "other.ts", "kind": "node", "id": "test.other"},
        ),
    ),
    NegativeCase(
        name="package-alias",
        code="VF_IMPORT_NODE_TO_NODE",
        diagnostic_file="entry.ts",
        marker='"#forbidden-node"',
        sources={
            "entry.ts": 'import { forbidden } from "#forbidden-node";\nexport function run() { void forbidden; return {}; }\n',
            "other.ts": "export const forbidden = 1;\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
            {"path": "other.ts", "kind": "node", "id": "test.other"},
        ),
    ),
    NegativeCase(
        name="symlink",
        code="VF_IMPORT_NODE_TO_NODE",
        diagnostic_file="entry.ts",
        marker='"./link.ts"',
        sources={
            "entry.ts": 'import { forbidden } from "./link.ts";\nexport function run() { void forbidden; return {}; }\n',
            "other.ts": "export const forbidden = 1;\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
            {"path": "other.ts", "kind": "node", "id": "test.other"},
        ),
    ),
    NegativeCase(
        name="base-lib-reverse",
        code="VF_IMPORT_LAYER",
        diagnostic_file="base.ts",
        marker='"./other.ts"',
        sources={
            "entry.ts": 'import { helper } from "./base.ts";\nexport function run() { void helper; return {}; }\n',
            "base.ts": 'import { forbidden } from "./other.ts";\nexport const helper = forbidden;\n',
            "other.ts": "export const forbidden = 1;\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
            {"path": "base.ts", "kind": "base_lib", "id": "test.base"},
            {"path": "other.ts", "kind": "node", "id": "test.other"},
        ),
        node_base_libs={"test.entry": ["test.base"]},
    ),
    NegativeCase(
        name="undeclared-external",
        code="VF_IMPORT_EXTERNAL",
        diagnostic_file="entry.ts",
        marker='"typescript"',
        sources={
            "entry.ts": 'import ts from "typescript";\nexport function run() { void ts; return {}; }\n',
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
    NegativeCase(
        name="package-root-escape",
        code="VF_IMPORT_PACKAGE_ROOT",
        diagnostic_file="entry.ts",
        marker='"../outside.ts"',
        sources={
            "entry.ts": 'import { outside } from "../outside.ts";\nexport function run() { void outside; return {}; }\n',
            "../outside.ts": "export const outside = 1;\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
    NegativeCase(
        name="dynamic-code",
        code="VF_IMPORT_DYNAMIC_CODE",
        diagnostic_file="entry.ts",
        marker="eval",
        sources={
            "entry.ts": 'export function run() { return eval("1"); }\n',
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
    NegativeCase(
        name="module-promise",
        code="VF_IMPORT_SIDE_EFFECT",
        diagnostic_file="entry.ts",
        marker="const ready",
        sources={
            "entry.ts": "const ready = Promise.resolve(1);\nexport function run() { void ready; return {}; }\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
    NegativeCase(
        name="discarded-promise",
        code="VF_PROMISE_UNOWNED",
        diagnostic_file="entry.ts",
        marker="void Promise",
        sources={
            "entry.ts": "export async function run() {\n  void Promise.resolve(1);\n  return {};\n}\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
        entry_mode="async",
        completion="suspend",
    ),
    NegativeCase(
        name="long-lived-listener",
        code="VF_NODE_LONG_LIVED_LISTENER",
        diagnostic_file="entry.ts",
        marker="addEventListener",
        sources={
            "entry.ts": 'export function run() { addEventListener("message", () => {}); return {}; }\n',
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
    NegativeCase(
        name="global-state",
        code="VF_MODULE_STATE",
        diagnostic_file="entry.ts",
        marker="count +=",
        sources={
            "entry.ts": "let count = 0;\nexport function run() { count += 1; return {}; }\n",
        },
        owners=(
            {"path": "entry.ts", "kind": "node", "id": "test.entry"},
        ),
    ),
)


@pytest.mark.parametrize("case", CASES, ids=lambda item: item.name)
def test_project_dependency_negative_has_precise_diagnostic(
    tmp_path: Path,
    case: NegativeCase,
) -> None:
    project = _project(tmp_path)
    for relative, source in case.sources.items():
        path = (project / relative).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    if case.name == "symlink":
        (project / "link.ts").symlink_to(project / "other.ts")
    owners = tuple(
        {
            **owner,
            "path": str((project / owner["path"]).resolve()),
            "export": "run",
            "completion": case.completion,
        }
        for owner in case.owners
    )
    entry = project / "entry.ts"
    with pytest.raises(AotBuildError) as caught:
        build_aot(
            BuildRequest(
                plan=_plan(
                    entry,
                    entry_mode=case.entry_mode,
                    completion=case.completion,
                ),
                project_root=project,
                package_root=project,
                out_dir=project / "dist",
                target="browser",
                profile="single-esm",
                import_policy={
                    "owners": owners,
                    "node_base_libs": case.node_base_libs or {},
                    "base_lib_dependencies": {"test.base": []},
                },
            )
        )
    matching = [
        item for item in caught.value.diagnostics if item.get("code") == case.code
    ]
    assert matching, [item.get("code") for item in caught.value.diagnostics]
    diagnostic = matching[0]
    expected_file = (project / case.diagnostic_file).resolve()
    expected_source = case.sources[case.diagnostic_file]
    expected_line, expected_column = _line_column(expected_source, case.marker)
    assert Path(str(diagnostic["file"])).resolve() == expected_file
    assert diagnostic["line"] == expected_line
    assert diagnostic["column"] == expected_column
    assert diagnostic["owner"] == {
        "id": "test.base" if case.name == "base-lib-reverse" else "test.entry",
        "kind": "base_lib" if case.name == "base-lib-reverse" else "node",
        "path": str(
            (
                project / "base.ts"
                if case.name == "base-lib-reverse"
                else project / "entry.ts"
            ).resolve()
        ),
    }


def test_failed_replace_preserves_every_existing_output_byte(tmp_path: Path) -> None:
    project = _project(tmp_path)
    entry = project / "entry.ts"
    entry.write_text("export function run() { return {}; }\n", encoding="utf-8")
    request = BuildRequest(
        plan=_plan(entry, entry_mode="sync", completion="immediate"),
        project_root=project,
        package_root=project,
        out_dir=project / "dist",
        target="browser",
        profile="single-esm",
        import_policy={
            "owners": [
                {
                    "path": str(entry),
                    "kind": "node",
                    "id": "test.entry",
                    "export": "run",
                    "completion": "immediate",
                }
            ]
        },
    )
    built = build_aot(request)
    before = {
        path.relative_to(built.out_dir).as_posix(): path.read_bytes()
        for path in built.out_dir.rglob("*")
        if path.is_file()
    }
    entry.write_text('export function run() { return eval("1"); }\n', encoding="utf-8")
    with pytest.raises(AotBuildError) as caught:
        build_aot(BuildRequest(**{**request.__dict__, "replace": True}))
    assert "VF_IMPORT_DYNAMIC_CODE" in {
        item.get("code") for item in caught.value.diagnostics
    }
    after = {
        path.relative_to(built.out_dir).as_posix(): path.read_bytes()
        for path in built.out_dir.rglob("*")
        if path.is_file()
    }
    assert after == before
