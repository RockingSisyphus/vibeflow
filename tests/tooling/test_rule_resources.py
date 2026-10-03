from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibeflow.core.descriptors import RuleImplementationDescriptor, SourceLocator
from vibeflow.core.rules import RuleDescriptor
from vibeflow.tooling.project.descriptor_loader import DescriptorLoadError, load_descriptor_catalogs, parse_descriptor_manifest
from vibeflow.tooling.presentation.node_presentation import resolve_presentation


def node(**values):
    return parse_descriptor_manifest({
        "kind": "node", "type_key": "model.affine", "display_name": "Affine",
        "description": "A single affine transform", "version": "1.0",
        "flow_kind": "process", "contract": {}, **values,
    })


def write(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_node_owns_selection_and_missing_selection_is_unconstrained():
    assert node().rulesets == ()
    assert node(rulesets=[]).rulesets == ()
    assert node(rulesets=["custom"]).rulesets == ("custom",)
    assert node().to_dict()["rulesets"] == []
    with pytest.raises(ValueError, match="unknown fields.*category"):
        node(category="model")


def test_presentation_cascade_and_provenance():
    descriptor = node(presentation={"fill": "#dbeafe", "shape": "hex", "icon": "M", "stroke": "#123456"})
    normal = resolve_presentation(descriptor)
    assert normal.values["fill"] == "#dbeafe"
    assert normal.shape == "hex"
    error = resolve_presentation(descriptor, status_class="healthError", call_style={"fill": "#abcdef", "shape": "circle"})
    assert error.values["stroke"] == "#dc2626"
    assert error.values["fill"] == "#abcdef"
    assert error.sources["fill"] == "call"
    assert error.sources["icon"] == "node"
    assert error.shape == "circle"
    with pytest.raises(TypeError):
        error.values["fill"] = "#ffffff"


def test_node_default_colors_keep_the_system_palette_reserved():
    with pytest.raises(ValueError, match="reserved system color"):
        node(presentation={"fill":"#fee2e2"})
    assert node(presentation={"fill":"#cceeff"}).presentation["fill"] == "#cceeff"


def test_bundle_loads_resources_and_retains_source(tmp_path):
    write(tmp_path / "package/rule.jsonc", {"kind": "rule", "id": "model.block", "handler": "test.block", "outputs": {"blocks": "model.blocks.v1"}})
    write(tmp_path / "package/ruleset.jsonc", {"kind": "ruleset", "id": "model.blocks", "calls": [{"id": "block", "rule_id": "model.block"}], "entrypoints": {"static": ["block"]}})
    write(tmp_path / "package/node.jsonc", node(rulesets=["model.blocks"]).to_dict())
    write(tmp_path / "entry/bundle.jsonc", {"kind": "bundle", "id": "model.package", "resources": {
        "nodes": ["../package/node.jsonc"],
        "rules": ["../package/rule.jsonc"], "rulesets": ["../package/ruleset.jsonc"],
    }})
    catalogs = load_descriptor_catalogs(tmp_path, {"bundles": ["entry"]})
    assert catalogs.rules.require("model.block").outputs["blocks"] == "model.blocks.v1"
    assert catalogs.nodes.require("model.affine").rulesets == ("model.blocks",)
    assert catalogs.nodes.source_for("model.affine") == str(tmp_path / "package/node.jsonc")
    assert len(catalogs.source_files) == 4


def test_nested_bundle_cycle_is_reported(tmp_path):
    write(tmp_path / "entry/a.jsonc", {"kind": "bundle", "id": "a", "resources": {"bundles": ["../other/b.jsonc"]}})
    write(tmp_path / "other/b.jsonc", {"kind": "bundle", "id": "b", "resources": {"bundles": ["../entry/a.jsonc"]}})
    with pytest.raises(DescriptorLoadError, match="BUNDLE.CYCLE"):
        load_descriptor_catalogs(tmp_path, {"bundles": ["entry"]})


def test_rule_has_one_implementation_per_execution_family():
    python = RuleImplementationDescriptor("python", SourceLocator("file", "rule.py", "check"))
    js = RuleImplementationDescriptor("javascript", SourceLocator("file", "rule.js", "check"))
    ts = RuleImplementationDescriptor("typescript", SourceLocator("file", "rule.ts", "check"))
    assert len(RuleDescriptor("portable", implementations=(python, js)).implementations) == 2
    with pytest.raises(ValueError, match="duplicate execution families"):
        RuleDescriptor("ambiguous", implementations=(js, ts))
    with pytest.raises(ValueError, match="unknown fields.*targets"):
        parse_descriptor_manifest({"kind": "rule", "id": "old", "implementations": [
            {"language": "javascript", "targets": ["node"], "source": {"kind": "file", "ref": "rule.js"}}]})


@pytest.mark.parametrize("selection,valid", [([], True), (["domain.blocks"], True), ("domain.blocks", False), ([3], False)])
def test_workflow_ruleset_selection_is_validated_without_loading_implementations(selection, valid):
    from vibeflow.tooling.project.config_schema import collect_config_schema_findings
    document = {"rulesets": selection, "pipeline": {"nodes": [{
        "id": "block", "type_used": "model.block", "display_name": "Block",
        "description": "A declaration-only schema check.",
    }]}}
    findings = collect_config_schema_findings(document)
    assert (not any(item.code == "CONFIG.SCHEMA.RULESETS" for item in findings)) == valid
