from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from vibeflow.tooling.application.python.project.resource_registries import BaseLibRegistry
from vibeflow.core.contracts import DataProvider
from vibeflow.core.descriptors import (
    JSON_SCHEMA_2020_12,
    BaseLibCatalog,
    BaseLibDescriptor,
    DataSchemaDescriptor,
    ImplementationDescriptor,
    NodeCatalog,
    NodeContractDescriptor,
    NodeDescriptor,
    SourceLocator,
)
from vibeflow.targets.python.project.descriptors import (
    adapt_base_lib_registry,
    adapt_node_registry,
    node_descriptor_from_registry,
)
from vibeflow.tooling.project.descriptor_loader import (
    DescriptorLoadError,
    load_descriptor_catalogs,
)
from vibeflow.targets.python.project.node import NodeContract, NodeInfo
from vibeflow.targets.python.project.registry import NodeRegistry


def _write_jsonc(path: Path, payload: object, *, comment: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "// descriptor fixture\n" if comment else ""
    path.write_text(prefix + json.dumps(payload, indent=2), encoding="utf-8")


def _node_payload(
    type_key: str = "demo.add",
    *,
    display_name: str = "Add",
) -> dict[str, object]:
    return {
        "kind": "node",
        "type_key": type_key,
        "display_name": display_name,
        "category": "demo",
        "description": "Adds one.",
        "version": "1.0.0",
        "flow_kind": "process",
        "contract": {
            "requires": [],
            "provides": [{"key": "value.out", "type": "value.out"}],
            "input_semantics": {},
            "output_semantics": {"value.out": ["result"]},
            "params_schema": {"delta": {"type": "number"}},
            "params_defaults": {"delta": 1},
            "output_schema": {"value.out": {"type": "number"}},
            "examples": [{"inputs": {}, "params": {"delta": 1}}],
        },
        "implementations": [
            {
                "language": "typescript",
                "targets": ["browser", "node"],
                "source": {
                    "kind": "file",
                    "ref": "project/nodes/add.ts",
                    "export": "run",
                },
            }
        ],
        "base_libs": ["demo.math"],
        "capabilities": [
            {"id": "demo.storage", "operations": ["read"]}
        ],
    }


def _descriptor_paths() -> dict[str, list[str]]:
    return {
        "nodes": ["manifests/nodes"],
        "base_lib": ["manifests/base_lib"],
        "data_schemas": ["manifests/data"],
        "capabilities": ["manifests/capabilities"],
        "host_extensions": ["manifests/host_extensions"],
    }


def test_descriptors_are_frozen_and_json_serializable() -> None:
    schema = DataSchemaDescriptor(
        type_key="value.out",
        schema={"type": "object", "properties": {"value": {"type": "number"}}},
    )

    with pytest.raises(TypeError):
        schema.schema["type"] = "string"  # type: ignore[index]

    snapshot = schema.to_dict()
    assert snapshot["schema"]["$schema"] == JSON_SCHEMA_2020_12
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_loader_scans_recursively_and_builds_all_catalogs(tmp_path: Path) -> None:
    root = tmp_path / "project-root"
    root.mkdir()
    _write_jsonc(
        root / "manifests/nodes/nested/add.jsonc",
        _node_payload(),
        comment=True,
    )
    _write_jsonc(
        root / "manifests/base_lib/math.jsonc",
        {
            "kind": "base_lib",
            "id": "demo.math",
            "display_name": "Math",
            "description": "Pure math helpers.",
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "project/base_lib/math.ts",
                    },
                }
            ],
            "dependencies": [],
            "external_packages": [],
        },
    )
    _write_jsonc(
        root / "manifests/data/value.jsonc",
        {
            "kind": "data_schema",
            "type_key": "value.out",
            "representation": "json",
            "schema": {"type": "number"},
        },
    )
    _write_jsonc(
        root / "manifests/capabilities/storage.jsonc",
        {
            "kind": "capability",
            "id": "demo.storage",
            "targets": ["browser", "node"],
            "operations": {
                "read": {
                    "input_type": "storage.read.request",
                    "output_type": "storage.read.result",
                }
            },
        },
    )
    _write_jsonc(
        root / "manifests/host_extensions/storage-host.jsonc",
        {
            "kind": "host_extension",
            "id": "demo.storage_host",
            "targets": ["browser", "node"],
            "implementations": [
                {
                    "language": "typescript",
                    "targets": ["browser", "node"],
                    "source": {
                        "kind": "file",
                        "ref": "project/host_extensions/storage.ts",
                        "export": "createHostExtension",
                    },
                }
            ],
            "provides": ["demo.storage"],
            "dependencies": [],
            "external_packages": [],
        },
    )

    catalogs = load_descriptor_catalogs(root, _descriptor_paths())

    assert catalogs.nodes.available() == ("demo.add",)
    assert catalogs.base_libs.available() == ("demo.math",)
    assert catalogs.schemas.available() == ("value.out",)
    assert catalogs.capabilities.available() == ("demo.storage",)
    assert catalogs.host_extensions.available() == (
        "demo.storage_host",
    )
    assert catalogs.nodes.require("demo.add").contract.params_defaults["delta"] == 1
    assert [path.relative_to(root).as_posix() for path in catalogs.source_files] == [
        "manifests/nodes/nested/add.jsonc",
        "manifests/base_lib/math.jsonc",
        "manifests/data/value.jsonc",
        "manifests/capabilities/storage.jsonc",
        "manifests/host_extensions/storage-host.jsonc",
    ]
    json.dumps(catalogs.to_dict())


@pytest.mark.parametrize(
    ("second_name", "expected_code"),
    [("Add", "DESCRIPTOR.DUPLICATE"), ("Different", "DESCRIPTOR.CONFLICT")],
)
def test_loader_reports_duplicate_and_conflicting_ids(
    tmp_path: Path,
    second_name: str,
    expected_code: str,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write_jsonc(root / "nodes/a.jsonc", _node_payload())
    _write_jsonc(
        root / "nodes/b.jsonc",
        _node_payload(display_name=second_name),
    )

    with pytest.raises(DescriptorLoadError) as captured:
        load_descriptor_catalogs(root, {"nodes": ["nodes"]})

    assert captured.value.code == expected_code
    assert "a.jsonc" in str(captured.value)
    assert "b.jsonc" in str(captured.value)


def test_loader_rejects_root_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()

    with pytest.raises(DescriptorLoadError) as escaped:
        load_descriptor_catalogs(root, {"nodes": ["../outside"]})
    assert escaped.value.code == "DESCRIPTOR.PATH.ESCAPE"

    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available")
    with pytest.raises(DescriptorLoadError) as linked:
        load_descriptor_catalogs(root, {"nodes": ["linked"]})
    assert linked.value.code == "DESCRIPTOR.PATH.SYMLINK"


def test_catalogs_sort_ids_and_preserve_source_diagnostics() -> None:
    contract = NodeContractDescriptor()
    first = NodeDescriptor(
        type_key="demo.z",
        display_name="Z",
        category="demo",
        description="Z.",
        version="1",
        flow_kind="process",
        contract=contract,
    )
    second = replace(first, type_key="demo.a", display_name="A")
    catalog = NodeCatalog()
    catalog.register(first, source="z.jsonc")
    catalog.register(second, source="a.jsonc")

    assert catalog.available() == ("demo.a", "demo.z")
    assert catalog.source_for("demo.z") == "z.jsonc"


class _LegacyNode:
    NODE_INFO = NodeInfo(
        "demo.legacy",
        "Legacy",
        "demo",
        "Legacy node.",
        "1.0.0",
        "process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider("value.out", "value.out"),),
        output_semantics={"value.out": ("result",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": params["value"]}


def test_legacy_adapters_keep_python_bindings_outside_descriptors() -> None:
    registry = NodeRegistry()
    registry.register(
        "demo.legacy",
        _LegacyNode,
        config_schema={"value": {"type": "number"}},
        config_defaults={"value": 1},
    )
    legacy = node_descriptor_from_registry(registry, "demo.legacy")
    static = replace(
        legacy,
        implementations=(
            ImplementationDescriptor(
                language="typescript",
                targets=("browser", "node"),
                source=SourceLocator(
                    kind="file",
                    ref="project/nodes/legacy.ts",
                    export="run",
                ),
            ),
        ),
    )
    static_catalog = NodeCatalog((static,))

    adapted = adapt_node_registry(registry, static_catalog=static_catalog)

    assert adapted.binding("demo.legacy") is _LegacyNode
    assert {
        implementation.language
        for implementation in adapted.catalog.require(
            "demo.legacy"
        ).implementations
    } == {"python", "typescript"}
    json.dumps(adapted.catalog.to_dict())

    base_registry = BaseLibRegistry()
    base_registry.register(
        "demo.math",
        module="demo.math",
        display_name="Math",
        description="Math helpers.",
    )
    static_base = BaseLibDescriptor(
        id="demo.math",
        display_name="Math",
        description="Math helpers.",
        implementations=(
            ImplementationDescriptor(
                language="typescript",
                targets=("browser", "node"),
                source=SourceLocator(
                    kind="file",
                    ref="project/base_lib/math.ts",
                ),
            ),
        ),
    )
    base_adapted = adapt_base_lib_registry(
        base_registry,
        static_catalog=BaseLibCatalog((static_base,)),
    )
    assert base_adapted.module("demo.math") == "demo.math"
    assert len(base_adapted.catalog.require("demo.math").implementations) == 2
