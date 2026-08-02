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
