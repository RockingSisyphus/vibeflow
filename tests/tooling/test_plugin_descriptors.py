"""File-backed plugin descriptor loading remains a Tooling concern."""

from __future__ import annotations

import json
from pathlib import Path

from vibeflow.core.descriptors import PluginDescriptor
from vibeflow.tooling.project.descriptor_loader import (
    load_descriptor_catalogs,
    parse_descriptor_manifest,
)


def _manifest() -> dict[str, object]:
    return {
        "kind": "plugin",
        "id": "demo.runtime",
        "type": "runtime",
        "targets": ["browser"],
        "implementations": [
            {
                "language": "typescript",
                "targets": ["browser"],
                "source": {
                    "kind": "file",
                    "ref": "plugins/runtime.ts",
                },
            }
        ],
        "config": {"defaults": {"mode": "test"}},
    }


def test_generic_descriptor_parser_supports_plugin_kind() -> None:
    descriptor = parse_descriptor_manifest(_manifest(), expected_kind="plugin")

    assert isinstance(descriptor, PluginDescriptor)
    assert descriptor.implementations[0].source.export == "createPlugin"


def test_descriptor_loader_registers_plugin_catalog(tmp_path: Path) -> None:
    directory = tmp_path / "manifests/plugins"
    directory.mkdir(parents=True)
    (directory / "runtime.jsonc").write_text(
        json.dumps(_manifest()),
        encoding="utf-8",
    )

    catalogs = load_descriptor_catalogs(
        tmp_path,
        {"plugins": ["manifests/plugins"]},
    )

    assert catalogs.plugins.require("demo.runtime").plugin_type == "runtime"
    assert len(catalogs.source_files) == 1
