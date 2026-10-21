from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

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
from vibeflow.tooling.project.resources import (
    ResourcePreparationError,
)
from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, ResourceOwner, compose_contributions, DescriptorCatalogError
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.core.descriptors.contributions import ResourceDeclaration
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
    return {'node_type': 'vibeflow.node',
        "kind": "node",
        'id': type_key,
        "display_name": display_name,

        "description": "Adds one.",
        "version": "1.0.0",
        "flow_kind": "process",
        "contract": {
            "requires": [],
            "provides": [{"key": "value.out", "type": "value.out", "display_name": "Result"}],
            "input_semantics": {},
            "output_semantics": {"value.out": ["result"]},
            "params_schema": {"delta": {"type": "number"}},
            "params_defaults": {"delta": 1},
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


def test_explicit_contributions_build_all_catalogs() -> None:
    values = [_node_payload(),
        {"kind": "base_lib", "id": "demo.math", "display_name": "Math", "description": "Pure math helpers.",
         "implementations": [{"language": "typescript", "targets": ["browser", "node"],
             "source": {"kind": "file", "ref": "project/base_lib/math.ts"}}]},
        {"kind": "data_schema", "type_key": "value.out", "representation": "json", "schema": {"type": "number"}},
        {"kind": "capability", "id": "demo.storage", "targets": ["browser", "node"],
         "operations": {"read": {"input_type": "storage.read.request", "output_type": "storage.read.result"}}},
]
    builder = ContributionBuilder("demo", source="demo_plugin.ts")
    resources = []
    for value in values:
        descriptor = decode_resource(value)
        if value["kind"] in {"node", "base_lib"}:
            resources.append(ResourceDeclaration(descriptor, ResourceOrigin(ResourceOwner("root", "app"), "demo_resources.ts")))
        else:
            builder.add(descriptor, origin=ResourceOrigin(ResourceOwner("plugin", "demo"), "demo_plugin.ts"))
    catalogs = compose_contributions((builder.finish(),), resources=tuple(resources))
    assert catalogs.nodes.available() == ("demo.add",)
    assert catalogs.base_libs.available() == ("demo.math",)
    assert catalogs.schemas.available() == ("value.out",)
    assert catalogs.capabilities.available() == ("demo.storage",)
    assert catalogs.nodes.require("demo.add").contract.params_defaults["delta"] == 1
    assert set(catalogs.source_files) == {"demo_plugin.ts", "demo_resources.ts"}
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
    declarations = tuple(ResourceDeclaration(decode_resource(payload), ResourceOrigin(ResourceOwner("root", "app"), name))
        for name, payload in (("a.py", _node_payload()), ("b.py", _node_payload(display_name=second_name))))
    with pytest.raises(DescriptorCatalogError) as captured:
        compose_contributions((), resources=declarations)
    assert captured.value.code == expected_code
    assert captured.value.source == "b.py"
    assert captured.value.previous_source == "a.py"


def test_selected_plugin_rejects_file_escape_and_symlink(tmp_path: Path) -> None:
    from vibeflow.tooling.project.resources import prepare_workflow_resources
    from vibeflow.tooling.project.workspace_loader import load_workspace_config
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir(); outside.mkdir()
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (tmp_path / "vibeflow_config.jsonc").write_text('{"roots":[{"id":"p","path":"root"}]}')
    (outside / "plugin.py").write_text('raise RuntimeError("escaped plugin was loaded")')
    (root / "linked.py").symlink_to(outside / "plugin.py")
    workspace = load_workspace_config(tmp_path / "vibeflow_config.jsonc")
    for ref in ("../outside/plugin.py", "linked.py"):
        config = root / "workflow.jsonc"
        config.write_text(json.dumps({"plugins":[{"source":{"kind":"file","ref":ref}}],"pipeline":{"nodes":[{"id":"future","definition_id":"future","display_name":"Future","description":"Planned","status":"planned","flow_kind":"process","requires":[],"provides":[]}]}}))
        with pytest.raises(ResourcePreparationError, match="selected workspace root"):
            prepare_workflow_resources(workspace, config)


def test_catalogs_sort_ids_and_preserve_source_diagnostics() -> None:
    contract = NodeContractDescriptor()
    first = NodeDescriptor(
        rulesets=(), id="demo.z",
        display_name="Z",

        description="Z.",
        version="1",
        flow_kind="process",
        contract=contract,
     node_type="vibeflow.node")
    second = replace(first, id="demo.a", display_name="A")
    catalog = NodeCatalog()
    catalog.register(first, source="z.jsonc")
    catalog.register(second, source="a.jsonc")

    assert catalog.available() == ("demo.a", "demo.z")
    assert catalog.source_for("demo.z") == "z.jsonc"


class _DeclaredNode:
    def run_pure(self, inputs, params):
        return {"value.out": params["value"]}


def test_declared_metadata_is_authoritative_for_python_bindings() -> None:
    registry = NodeRegistry()
    descriptor = NodeDescriptor(
        id="demo.declared", display_name="Declared",
        description="A declared node.", version="1.0.0", flow_kind="process",
        rulesets=("vibeflow.process",),
        contract=NodeContractDescriptor(
            provides=(DataProvider("value.out", "value.out", display_name="value.out"),),
            output_semantics={"value.out": ("result",)},
            params_schema={"value": {"type": "number"}}, params_defaults={"value": 1},
        ),
     node_type="vibeflow.node")
    registry.register(descriptor, _DeclaredNode, source="nodes/declared.jsonc")
    assert registry.descriptor("demo.declared") is descriptor
    assert registry.get("demo.declared") is _DeclaredNode
    assert registry.get_config_spec("demo.declared").defaults["value"] == 1
    assert not hasattr(_DeclaredNode, "NODE_INFO")
    assert not hasattr(_DeclaredNode, "CONTRACT")
    json.dumps(descriptor.to_dict())

    # Canonical library declarations retain every language implementation and Ruleset.
    descriptor = BaseLibDescriptor(
        id="demo.math", display_name="Math", description="Math helpers.",
        rulesets=("custom.review",),
        implementations=(
            ImplementationDescriptor(language="python", targets=("python",),
                source=SourceLocator(kind="module", ref="demo.math")),
            ImplementationDescriptor(language="typescript", targets=("browser", "node"),
                source=SourceLocator(kind="file", ref="project/base_lib/math.ts")),
        ),
    )
    catalog = BaseLibCatalog((descriptor,))
    assert catalog.require("demo.math") is descriptor
    assert catalog.require("demo.math").rulesets == ("custom.review",)
    assert len(catalog.require("demo.math").implementations) == 2
