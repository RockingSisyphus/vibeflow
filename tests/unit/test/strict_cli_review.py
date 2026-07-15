from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from tests.unit.strict_support import _seed_add_pipeline, cli_main
from vibeflow.rendering.architecture_document import ARCHITECTURE_DOCUMENT_HEADER


_CANONICAL_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" '
    'aria-roledescription="flowchart-review-columns">'
    '<g class="review-inline-fragment"><g id="real-content"/></g>'
    "</svg>"
)


def _write_review_workspace(
    tmp_path: Path,
    *,
    registered: bool = True,
    planned: bool = False,
) -> tuple[Path, Path, Path, Path]:
    repo = tmp_path / "repo"
    project = repo / "project"
    configs = project / "configs"
    configs.mkdir(parents=True)
    workspace_path = repo / "vibeflow_config.jsonc"
    workflow_path = configs / "main.jsonc"
    architecture_path = project / "ARCHITECTURE.jsonc"
    output_path = repo / "reports" / "graph.expanded.svg"
    workspace_path.write_text(
        json.dumps({"policy": {}, "roots": [{"id": "project", "path": "project"}]}),
        encoding="utf-8",
    )
    project_config: dict[str, object] = {
        "registry": "registry.py:build_node_registry",
        "quality_enabled": False,
    }
    if registered:
        project_config["architecture"] = {
            "documents": [{"workflow": "configs/main.jsonc", "document": "ARCHITECTURE.jsonc"}]
        }
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(project_config, indent=2),
        encoding="utf-8",
    )
    (project / "registry.py").write_text(
        "from vibeflow import NodeRegistry\n"
        "from tests.unit import strict_support_runtime_nodes as nodes\n\n"
        "def build_node_registry():\n"
        "    registry = NodeRegistry()\n"
        "    registry.register('test.start', nodes.StartNode, config_schema={}, config_defaults={})\n"
        "    registry.register('test.seed', nodes.SeedNode, config_schema={'value': {'type': 'number'}}, config_defaults={'value': 1})\n"
        "    registry.register('test.add', nodes.AddNode, config_schema={'delta': {'type': 'number'}}, config_defaults={'delta': 1})\n"
        "    registry.register('test.out_end', nodes.OutEndNode, config_schema={}, config_defaults={})\n"
        "    return registry\n",
        encoding="utf-8",
    )
    pipeline = _seed_add_pipeline()
    if planned:
        pipeline["nodes"][2]["status"] = "planned"
        pipeline["nodes"][2]["flow_kind"] = "process"
        pipeline["nodes"][2]["planned_behavior"] = "transparent"
    workflow_path.write_text(json.dumps({"pipeline": pipeline}, indent=2), encoding="utf-8")
    return workspace_path, workflow_path, architecture_path, output_path


def _review_args(workspace_path: Path, workflow_path: Path, output_path: Path) -> list[str]:
    return [
        "review",
        "--workspace",
        str(workspace_path),
        "--config",
        str(workflow_path),
        "--output",
        str(output_path),
    ]


def _install_fake_renderer(monkeypatch, *, svg_text: str = _CANONICAL_SVG) -> list[dict[str, object]]:
    import vibeflow.rendering.mermaid.review_svg as review_svg_module

    calls: list[dict[str, object]] = []

    def fake_renderer(graph, compiled, output, **kwargs):
        calls.append({"graph": graph, "compiled": compiled, "output": Path(output), **kwargs})
        Path(output).write_text(svg_text, encoding="utf-8")

    monkeypatch.setattr(review_svg_module, "render_review_columns_svg", fake_renderer)
    return calls


def test_review_requires_workspace_config_and_output() -> None:
    with pytest.raises(SystemExit) as exc_info:
        cli_main(["review", "--config", "workflow.jsonc", "--output", "graph.svg"])

    assert exc_info.value.code == 2


def test_review_refreshes_architecture_validates_and_atomically_publishes_svg(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    from vibeflow.rendering.mermaid.render import (
        EXPANDED_MERMAID_MAX_EDGES,
        EXPANDED_MERMAID_MAX_TEXT_SIZE,
    )

    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    architecture_path.write_text("stale architecture", encoding="utf-8")
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(b"legacy-svg")
    calls = _install_fake_renderer(monkeypatch)

    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 0
    assert payload == {
        "status": payload["validation"]["status"],
        "failed_stage": None,
        "config": str(workflow_path.resolve()),
        "architecture": str(architecture_path.resolve()),
        "validation": payload["validation"],
        "svg": str(output_path.resolve()),
        "published": True,
    }
    assert payload["status"] in {"PASS", "CONCERNS"}
    assert architecture_path.read_text(encoding="utf-8").startswith(ARCHITECTURE_DOCUMENT_HEADER)
    assert output_path.read_text(encoding="utf-8") == _CANONICAL_SVG
    assert len(calls) == 1
    assert calls[0]["output"] != output_path
    assert calls[0]["expand_nodesets"] is True
    assert calls[0]["show_contract"] is True
    assert calls[0]["show_semantics"] is True
    assert calls[0]["theme"] == "default"
    assert calls[0]["background"] == "transparent"
    assert calls[0]["max_text_size"] == EXPANDED_MERMAID_MAX_TEXT_SIZE
    assert calls[0]["max_edges"] == EXPANDED_MERMAID_MAX_EDGES
    assert "provenance" not in output_path.read_text(encoding="utf-8").lower()
    assert not list(output_path.parent.glob("*provenance*"))


def test_review_rejects_unregistered_workflow_without_rendering(tmp_path, monkeypatch, capsys) -> None:
    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(
        tmp_path,
        registered=False,
    )

    def fail_renderer(*args, **kwargs):
        raise AssertionError("unregistered workflow must not render")

    monkeypatch.setattr("vibeflow.cli.review._render_canonical_review_svg", fail_renderer)
    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["failed_stage"] == "architecture"
    assert payload["error"]["rule_id"] == "REVIEW.ARCHITECTURE.UNREGISTERED"
    assert payload["published"] is False
    assert not architecture_path.exists()
    assert not output_path.exists()


@pytest.mark.parametrize("conflict", ["workspace", "workflow", "architecture"])
def test_review_rejects_output_that_would_overwrite_a_source(
    tmp_path,
    monkeypatch,
    capsys,
    conflict,
) -> None:
    workspace_path, workflow_path, architecture_path, _ = _write_review_workspace(tmp_path)
    architecture_path.write_bytes(b"existing-architecture")
    protected = {
        "workspace": workspace_path,
        "workflow": workflow_path,
        "architecture": architecture_path,
    }
    before = {name: path.read_bytes() for name, path in protected.items()}

    def fail_renderer(*args, **kwargs):
        raise AssertionError("conflicting output must be rejected before rendering")

    monkeypatch.setattr("vibeflow.cli.review._render_canonical_review_svg", fail_renderer)
    code = cli_main(_review_args(workspace_path, workflow_path, protected[conflict]))
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "FAIL"
    assert payload["failed_stage"] == "output"
    assert payload["published"] is False
    assert payload["error"]["rule_id"] == "REVIEW.OUTPUT.CONFLICT"
    assert {name: path.read_bytes() for name, path in protected.items()} == before


def test_review_creates_missing_registered_architecture(tmp_path, monkeypatch, capsys) -> None:
    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    _install_fake_renderer(monkeypatch)

    assert not architecture_path.exists()
    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["published"] is True
    assert architecture_path.read_text(encoding="utf-8").startswith(ARCHITECTURE_DOCUMENT_HEADER)


def test_review_restores_noncanonical_registered_architecture(tmp_path, monkeypatch, capsys) -> None:
    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    _install_fake_renderer(monkeypatch)
    assert cli_main(_review_args(workspace_path, workflow_path, output_path)) == 0
    json.loads(capsys.readouterr().out)
    canonical = architecture_path.read_bytes()
    architecture_path.write_bytes(canonical + b"\n")

    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["published"] is True
    assert architecture_path.read_bytes() == canonical


def test_review_preflight_failure_does_not_touch_architecture_or_render(tmp_path, monkeypatch, capsys) -> None:
    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    workflow["pipeline"]["nodes"] = workflow["pipeline"]["nodes"][1:]
    workflow["pipeline"]["edges"] = workflow["pipeline"]["edges"][1:]
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    architecture_path.write_bytes(b"architecture-before-preflight")

    def fail_renderer(*args, **kwargs):
        raise AssertionError("failed preflight must not render")

    monkeypatch.setattr("vibeflow.cli.review._render_canonical_review_svg", fail_renderer)
    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["failed_stage"] == "preflight"
    assert payload["validation"]["status"] in {"FAIL", "ERROR"}
    assert architecture_path.read_bytes() == b"architecture-before-preflight"
    assert not output_path.exists()


@pytest.mark.parametrize(
    ("helper", "failed_stage", "rule_id", "architecture_is_refreshed"),
    [
        (
            "load_workspace_graph_for_export",
            "preflight",
            "REVIEW.PREFLIGHT",
            False,
        ),
        (
            "validate_workspace_config_path",
            "validation",
            "REVIEW.VALIDATION",
            True,
        ),
    ],
)
def test_review_stage_exception_is_json_failure_without_publishing(
    tmp_path,
    monkeypatch,
    capsys,
    helper,
    failed_stage,
    rule_id,
    architecture_is_refreshed,
) -> None:
    import vibeflow.workspace as workspace_module

    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    architecture_before = b"architecture-before-stage-exception"
    svg_before = b"svg-before-stage-exception"
    architecture_path.write_bytes(architecture_before)
    output_path.parent.mkdir(parents=True)
    output_path.write_bytes(svg_before)

    def raise_stage_error(*args, **kwargs):
        raise RuntimeError(f"unexpected {helper} failure")

    def fail_renderer(*args, **kwargs):
        raise AssertionError("failed review stage must not render")

    monkeypatch.setattr(workspace_module, helper, raise_stage_error)
    monkeypatch.setattr("vibeflow.cli.review._render_canonical_review_svg", fail_renderer)
    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "ERROR"
    assert payload["failed_stage"] == failed_stage
    assert payload["published"] is False
    assert payload["error"]["rule_id"] == rule_id
    assert output_path.read_bytes() == svg_before
    if architecture_is_refreshed:
        assert architecture_path.read_text(encoding="utf-8").startswith(
            ARCHITECTURE_DOCUMENT_HEADER
        )
    else:
        assert architecture_path.read_bytes() == architecture_before


def test_review_concerns_is_success_and_publishes(tmp_path, monkeypatch, capsys) -> None:
    workspace_path, workflow_path, _, output_path = _write_review_workspace(tmp_path, planned=True)
    _install_fake_renderer(monkeypatch)

    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "CONCERNS"
    assert payload["validation"]["status"] == "CONCERNS"
    assert payload["published"] is True


def test_review_render_failure_preserves_existing_svg_and_writes_one_json_object(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    workspace_path, workflow_path, architecture_path, output_path = _write_review_workspace(tmp_path)
    architecture_path.write_text("stale architecture", encoding="utf-8")
    output_path.parent.mkdir(parents=True)
    original_svg = b"\x00old-review-svg\xff"
    output_path.write_bytes(original_svg)

    def fail_renderer(*args, **kwargs):
        raise RuntimeError("renderer unavailable")

    monkeypatch.setattr("vibeflow.cli.review._render_canonical_review_svg", fail_renderer)
    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 1
    assert payload["failed_stage"] == "svg"
    assert payload["published"] is False
    assert payload["error"]["rule_id"] == "REVIEW.SVG.RENDER"
    assert output_path.read_bytes() == original_svg
    assert architecture_path.read_text(encoding="utf-8").startswith(ARCHITECTURE_DOCUMENT_HEADER)
    assert not list(output_path.parent.glob(f".{output_path.name}.*.tmp"))
    assert not list(output_path.parent.glob("*provenance*"))


@pytest.mark.parametrize(
    ("svg_text", "rule_id"),
    [
        ("", "REVIEW.SVG.XML"),
        ("<html><g/></html>", "REVIEW.SVG.ROOT"),
        ('<svg><g class="review-inline-fragment"><g/></g></svg>', "REVIEW.SVG.LAYOUT"),
        (
            '<svg aria-roledescription="flowchart-review-columns"><g class="review-inline-fragment"/></svg>',
            "REVIEW.SVG.FRAGMENT",
        ),
        (
            '<svg aria-roledescription="flowchart-review-columns"><rect class="review-inline-fragment"><g/></rect></svg>',
            "REVIEW.SVG.FRAGMENT",
        ),
    ],
)
def test_review_svg_check_failure_preserves_existing_svg(
    tmp_path,
    monkeypatch,
    capsys,
    svg_text,
    rule_id,
) -> None:
    workspace_path, workflow_path, _, output_path = _write_review_workspace(tmp_path)
    output_path.parent.mkdir(parents=True)
    original_svg = b"existing-canonical-review"
    output_path.write_bytes(original_svg)
    _install_fake_renderer(monkeypatch, svg_text=svg_text)

    code = cli_main(_review_args(workspace_path, workflow_path, output_path))
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)

    assert code == 1
    assert payload["failed_stage"] == "svg_check"
    assert payload["published"] is False
    assert payload["error"]["rule_id"] == rule_id
    assert output_path.read_bytes() == original_svg
    assert not list(output_path.parent.glob(f".{output_path.name}.*.tmp"))
    assert not list(output_path.parent.glob("*provenance*"))


def test_project_template_run_injects_workspace_for_review(tmp_path) -> None:
    source_path = (
        Path(__file__).resolve().parents[3]
        / "distribution"
        / "kernel_development_pack"
        / "project_template"
        / "run.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    assignments = {
        target.id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in {"COMMAND_ALIASES", "WORKSPACE_COMMANDS"}
    }
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_kernel_cli_args"
    )
    workspace_path = tmp_path / "vibeflow_config.jsonc"
    workspace_path.write_text("{}", encoding="utf-8")
    namespace = {
        "COMMAND_ALIASES": assignments["COMMAND_ALIASES"],
        "WORKSPACE_COMMANDS": assignments["WORKSPACE_COMMANDS"],
        "WORKSPACE_CONFIG_PATH": workspace_path,
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source_path), "exec"), namespace)

    assert "review" in assignments["WORKSPACE_COMMANDS"]
    assert namespace["_kernel_cli_args"](["review", "--config", "main.jsonc", "--output", "graph.svg"]) == [
        "review",
        "--workspace",
        str(workspace_path),
        "--config",
        "main.jsonc",
        "--output",
        "graph.svg",
    ]
