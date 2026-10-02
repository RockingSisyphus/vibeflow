from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibeflow.core.descriptors import NodeCategoryCatalog, NodeCategoryDescriptor, selected_node_rulesets
from vibeflow.tooling.project.descriptor_loader import DescriptorLoadError, load_descriptor_catalogs, parse_descriptor_manifest
from vibeflow.tooling.presentation.node_presentation import resolve_presentation


def node(**values):
    return parse_descriptor_manifest({
        "kind": "node", "type_key": "model.affine", "display_name": "Affine",
        "category": "model", "description": "A single affine transform", "version": "1.0",
        "flow_kind": "process", "contract": {}, **values,
    })


def write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_category_default_and_explicit_empty_selection():
    categories = NodeCategoryCatalog([NodeCategoryDescriptor("model", default_rulesets=("model.blocks",))])
    assert selected_node_rulesets(node(), categories) == ("model.blocks",)
    assert selected_node_rulesets(node(rulesets=[]), categories) == ()
    assert selected_node_rulesets(node(rulesets=["custom"]), categories) == ("custom",)
    assert "rulesets" not in node().to_dict()
    assert node(rulesets=[]).to_dict()["rulesets"] == []


def test_presentation_cascade_and_provenance():
    category = NodeCategoryDescriptor("model", presentation={"fill": "#dbeafe", "shape": "hex", "icon": "M"})
    descriptor = node(presentation={"stroke": "#123456"})
    normal = resolve_presentation(descriptor, category)
    assert normal.values["fill"] == "#dbeafe"
    assert normal.shape == "hex"
    error = resolve_presentation(descriptor, category, status_class="healthError", call_style={"fill": "#abcdef", "shape": "circle"})
    assert error.values["stroke"] == "#dc2626"
    assert error.values["fill"] == "#abcdef"
    assert error.sources["fill"] == "call"
    assert error.sources["icon"] == "category"
    assert error.shape == "circle"
    with pytest.raises(TypeError):
        error.values["fill"] = "#ffffff"


def test_bundle_loads_resources_and_retains_source(tmp_path):
    write(tmp_path / "package/category.jsonc", {"kind": "node_category", "id": "model", "default_rulesets": ["model.blocks"]})
    write(tmp_path / "package/rule.jsonc", {"kind": "rule", "id": "model.block", "handler": "test.block", "outputs": {"blocks": "model.blocks.v1"}})
    write(tmp_path / "package/ruleset.jsonc", {"kind": "ruleset", "id": "model.blocks", "calls": [{"id": "block", "rule_id": "model.block"}], "entrypoints": {"static": ["block"]}})
    write(tmp_path / "package/node.jsonc", node().to_dict())
    write(tmp_path / "entry/bundle.jsonc", {"kind": "bundle", "id": "model.package", "resources": {
        "categories": ["../package/category.jsonc"], "nodes": ["../package/node.jsonc"],
        "rules": ["../package/rule.jsonc"], "rulesets": ["../package/ruleset.jsonc"],
    }})
    catalogs = load_descriptor_catalogs(tmp_path, {"bundles": ["entry"]})
    assert catalogs.rules.require("model.block").outputs["blocks"] == "model.blocks.v1"
    assert catalogs.nodes.require("model.affine").category == "model"
    assert catalogs.categories.source_for("model") == str(tmp_path / "package/category.jsonc")
    assert len(catalogs.source_files) == 5


def test_nested_bundle_cycle_is_reported(tmp_path):
    write(tmp_path / "entry/a.jsonc", {"kind": "bundle", "id": "a", "resources": {"bundles": ["../other/b.jsonc"]}})
    write(tmp_path / "other/b.jsonc", {"kind": "bundle", "id": "b", "resources": {"bundles": ["../entry/a.jsonc"]}})
    with pytest.raises(DescriptorLoadError, match="BUNDLE.CYCLE"):
        load_descriptor_catalogs(tmp_path, {"bundles": ["entry"]})
