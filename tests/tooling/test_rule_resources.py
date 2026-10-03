from __future__ import annotations

import json
from pathlib import Path

import pytest

from vibeflow.core.descriptors import RuleImplementationDescriptor, SourceLocator
from vibeflow.core.rules import RuleDescriptor
from vibeflow.core.descriptors.decode import decode_resource as parse_descriptor_manifest
from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, compose_contributions
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


def test_code_contributions_retain_resource_selection_and_source(tmp_path):
    definitions = [
        {"kind":"rule", "id":"model.block", "handler":"test.block", "outputs":{"blocks":"model.blocks.v1"}},
        {"kind":"ruleset", "id":"model.blocks", "calls":[{"id":"block", "rule_id":"model.block"}], "entrypoints":{"static":["block"]}},
        node(rulesets=["model.blocks"]).to_dict(),
    ]
    builder = ContributionBuilder("model.package")
    for index, value in enumerate(definitions):
        builder.add(parse_descriptor_manifest(value), origin=ResourceOrigin("model.package", str(tmp_path / "model.py"), index + 1))
    catalogs = compose_contributions((builder.finish(),))
    assert catalogs.rules.require("model.block").outputs["blocks"] == "model.blocks.v1"
    assert catalogs.nodes.require("model.affine").rulesets == ("model.blocks",)
    assert catalogs.origins[("nodes", "model.affine")].line == 3


def test_removed_bundle_is_not_a_resource_declaration():
    with pytest.raises(ValueError, match="kind must be one of"):
        parse_descriptor_manifest({"kind":"bundle", "id":"old", "resources":{}})


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
