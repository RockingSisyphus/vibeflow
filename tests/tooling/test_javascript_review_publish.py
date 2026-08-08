from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from vibeflow.tooling.application.javascript import cli
from vibeflow.tooling.project.document_kinds import (
    ARCHITECTURE_DOCUMENT_HEADER,
)


def _review_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from vibeflow.tooling.application.javascript import audit, review
    from vibeflow.tooling.project import workspace_loader

    root_path = tmp_path / "project"
    root_path.mkdir()
    config = root_path / "workflow.jsonc"
    config.write_text('{"pipeline":{"nodes":[]}}\n', encoding="utf-8")
    architecture = root_path / "ARCHITECTURE.jsonc"
    svg = tmp_path / "review.svg"
    spec = SimpleNamespace(
        workflow_path=config,
        document_path=architecture,
    )
    root = SimpleNamespace(
        path=root_path,
        config_path=root_path / "vibeflow_project.jsonc",
        architecture_documents=(spec,),
    )
    workspace = SimpleNamespace(
        path=tmp_path / "vibeflow_config.jsonc",
        root_for_path=lambda path: root if Path(path).resolve() == config else None,
    )
    workspace.path.write_text('{"roots":[]}\n', encoding="utf-8")
    root.config_path.write_text('{}\n', encoding="utf-8")
    monkeypatch.setattr(workspace_loader, "load_workspace_config", lambda _path: workspace)
    rendered_architecture = ARCHITECTURE_DOCUMENT_HEADER + json.dumps(
        {
            "project_target": "javascript",
            "workflow": {},
            "nodesets": {},
            "node_types": {},
            "resources": {},
        },
        indent=2,
    ) + "\n"
    result = SimpleNamespace(
        plan=SimpleNamespace(workflow_id="demo"),
        config_path=config,
        source_files=(),
        toolchain=None,
    )
    monkeypatch.setattr(audit, "render_architecture", lambda _result: rendered_architecture)
    monkeypatch.setattr(review, "expected_review_coverage", lambda _result: frozenset({("workflow", "", "demo")}))
    args = SimpleNamespace(
        workspace=str(workspace.path),
        config=str(config),
        output=str(svg),
        node_command="node",
    )
    return args, result, architecture, svg, rendered_architecture


def test_review_pair_failure_restores_both_previous_documents(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    architecture = tmp_path / "ARCHITECTURE.jsonc"
    svg = tmp_path / "review.svg"
    architecture.write_text("old architecture\n", encoding="utf-8")
    svg.write_text("old svg\n", encoding="utf-8")
    real_replace = os.replace

    def fail_svg_publish(source, destination):
        source_path = Path(source)
        destination_path = Path(destination)
        if destination_path == svg and source_path.suffix == ".tmp":
            raise OSError("injected SVG publish failure")
        return real_replace(source, destination)

    monkeypatch.setattr(cli.os, "replace", fail_svg_publish)

    with pytest.raises(OSError, match="injected SVG"):
        cli._publish_review_pair(
            (
                (architecture, "new architecture\n"),
                (svg, "new svg\n"),
            )
        )

    assert architecture.read_text(encoding="utf-8") == "old architecture\n"
    assert svg.read_text(encoding="utf-8") == "old svg\n"
    assert not tuple(tmp_path.glob(".*.tmp"))
    assert not tuple(tmp_path.glob(".*.backup"))


def test_review_svg_coverage_rejects_missing_nodeset_fragment(tmp_path: Path) -> None:
    svg = tmp_path / "review.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'aria-roledescription="flowchart-review-columns">'
        '<g class="review-inline-fragment" data-review-kind="workflow" '
        'data-review-owner="" data-review-target="demo"><g/></g></svg>',
        encoding="utf-8",
    )

    with pytest.raises(cli._ReviewSvgValidationError) as captured:
        cli._validate_review_svg_file(
            svg,
            expected_coverage=frozenset(
                {
                    ("workflow", "", "demo"),
                    ("nodeset", "workflow", "demo.group"),
                }
            ),
        )

    assert captured.value.code == "REVIEW.SVG.COVERAGE"
    assert "demo.group" in str(captured.value)


def test_review_preflight_failure_preserves_registered_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    args, _result, architecture, svg, _rendered = _review_fixture(tmp_path, monkeypatch)
    architecture.write_text("old architecture\n", encoding="utf-8")
    svg.write_text("old svg\n", encoding="utf-8")
    error = RuntimeError("invalid workflow")
    error.code = "VF_AOT_CONFIG"  # type: ignore[attr-defined]
    monkeypatch.setattr(cli, "_audit", lambda _args: (None, error))

    assert cli.handle_review(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["failed_stage"] == "preflight"
    assert payload["published"] is False
    assert architecture.read_text(encoding="utf-8") == "old architecture\n"
    assert svg.read_text(encoding="utf-8") == "old svg\n"


def test_review_renderer_failure_keeps_new_architecture_and_old_svg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeflow.tooling.application.javascript import review

    args, result, architecture, svg, rendered = _review_fixture(tmp_path, monkeypatch)
    svg.write_text("old svg\n", encoding="utf-8")
    monkeypatch.setattr(cli, "_audit", lambda _args: (result, None))
    monkeypatch.setattr(
        review,
        "write_review_svg",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("renderer failed")),
    )

    assert cli.handle_review(args) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAIL"
    assert payload["failed_stage"] == "svg"
    assert payload["code"] == "REVIEW.SVG.RENDER"
    assert architecture.read_text(encoding="utf-8") == rendered
    assert svg.read_text(encoding="utf-8") == "old svg\n"


def test_review_publishes_single_json_and_coverage_checked_svg(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeflow.tooling.application.javascript import review

    args, result, architecture, svg, rendered = _review_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "_audit", lambda _args: (result, None))

    def write_svg(_result, output: Path, **_kwargs) -> None:
        output.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'aria-roledescription="flowchart-review-columns">'
            '<g class="review-inline-fragment" data-review-kind="workflow" '
            'data-review-owner="" data-review-target="demo"><g/></g></svg>',
            encoding="utf-8",
        )

    monkeypatch.setattr(review, "write_review_svg", write_svg)

    assert cli.handle_review(args) == 0

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "PASS"
    assert payload["failed_stage"] is None
    assert payload["published"] is True
    assert payload["output"] == payload["svg"] == str(svg.resolve())
    assert architecture.read_text(encoding="utf-8") == rendered
    assert "data-review-target=\"demo\"" in svg.read_text(encoding="utf-8")


def test_quality_discovery_ignores_nodesets_and_architecture_documents(
    tmp_path: Path,
) -> None:
    root = tmp_path / "project"
    configs = root / "configs"
    configs.mkdir(parents=True)
    workflow = configs / "workflow.jsonc"
    nodeset = configs / "nodeset.jsonc"
    architecture = configs / "ARCHITECTURE.jsonc"
    workflow.write_text(
        json.dumps({"pipeline": {"nodes": []}}),
        encoding="utf-8",
    )
    nodeset.write_text(
        json.dumps(
            {
                "type_key": "demo.group",
                "requires": [],
                "provides": [],
                "pipeline": {"nodes": []},
            }
        ),
        encoding="utf-8",
    )
    architecture.write_text(
        ARCHITECTURE_DOCUMENT_HEADER
        + json.dumps(
            {
                "project_target": "javascript",
                "workflow": {},
                "nodesets": {},
                "node_types": {},
                "resources": {},
            }
        ),
        encoding="utf-8",
    )
    workspace = SimpleNamespace(
        roots=(
            SimpleNamespace(
                path=root,
                project_target="javascript",
                architecture_documents=(),
            ),
        )
    )

    discovered = cli._quality_configs(
        workspace,
        explicit_config=None,
        explicit_path=str(root),
    )

    assert discovered == (workflow.resolve(),)
