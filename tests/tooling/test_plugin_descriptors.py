"""Canonical plugin declarations compose through the common catalogs."""

from __future__ import annotations

import json
from pathlib import Path

from vibeflow.core.descriptors import PluginDescriptor
from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, ResourceOwner, compose_contributions
from vibeflow.core.descriptors.decode import decode_resource


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
    descriptor = decode_resource(_manifest(), expected_kind="plugin")

    assert isinstance(descriptor, PluginDescriptor)
    assert descriptor.implementations[0].source.export == "createPlugin"


def test_descriptor_loader_registers_plugin_catalog(tmp_path: Path) -> None:
    builder = ContributionBuilder("demo", source="runtime_plugin.py")
    builder.add(decode_resource(_manifest()), origin=ResourceOrigin(ResourceOwner("plugin", "demo"), "runtime_plugin.py"))
    catalogs = compose_contributions((builder.finish(),))
    assert catalogs.plugins.require("demo.runtime").plugin_type == "runtime"
    assert catalogs.source_files == ("runtime_plugin.py",)
