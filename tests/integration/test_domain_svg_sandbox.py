"""Real formal SVG publication for Node, status and call styles."""
from __future__ import annotations
from tests.fixtures.support.plugins import resource as resource_ref

import json
import os
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

import pytest

from vibeflow.tooling.application.cli import main
from vibeflow.tooling.project.config_loader import strip_jsonc_comments
from vibeflow.tooling.presentation.mermaid import is_mermaid_svg_renderer_available
from tests.fixtures.support.rule_sandbox import create_rule_graph_sandbox


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(params=("python", "javascript"))
def svg_project(request, tmp_path):
    if not is_mermaid_svg_renderer_available():
        pytest.skip("requires the renderer prepared by verify_project.py --full")
    target = request.param
    example = tmp_path / target
    shutil.copytree(ROOT / "sandbox" / target / "domain_rules", example)
    project = example / "project"
    if target == "javascript":
        toolchain = Path(os.environ["VIBEFLOW_TEST_TOOLCHAIN_ROOT"])
        (project / "node_modules").symlink_to(toolchain / "node_modules", target_is_directory=True)
    yield target, example / "vibeflow_config.jsonc", project


def _edit(path, change):
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _node(svg, target, name):
    identifier = "vf_" + name if target == "javascript" else name
    matches = [element for element in svg.iter()
        if "node" in element.get("class", "").split()
        and "flowchart-" + identifier + "-" in element.get("id", "")]
    assert len(matches) == 1, [element.get("id") for element in matches]
    return matches[0]


def _label(element):
    return " ".join(" ".join(element.itertext()).split())


def _assert_shape(element, shape):
    geometry = [child for child in element if child.tag.rsplit("}", 1)[-1] in {"polygon", "circle", "rect", "path"}]
    assert geometry, ET.tostring(element, encoding="unicode")
    if shape in {"hex", "diamond"}:
        polygons = [item for item in geometry if item.tag.endswith("polygon")]
        assert polygons
        assert len(polygons[0].get("points", "").split()) == (6 if shape == "hex" else 4)
    elif shape == "circle":
        assert any(item.tag.endswith("circle") for item in geometry)
    elif shape == "rounded":
        assert any(item.tag.endswith("rect") and float(item.get("rx", "0")) > 0 for item in geometry)


@pytest.mark.parametrize("level,fill,shape,icon", [
    ("default", "#cceeff", "hex", "MODEL_ICON"),
    ("node", "#fff2aa", "diamond", "NODE_ICON"),
    ("call", "#ffe6ee", "circle", "CALL_ICON"),
    ("status", "#fef08a", "diamond", "NODE_ICON"),
    ("planned", "#ffe6ee", "circle", "CALL_ICON"),
])
def test_formal_domain_svg_preserves_effective_styles_and_native_identity(svg_project, capsys, tmp_path, level, fill, shape, icon):
    target, workspace, project = svg_project
    _edit(project / "vibeflow_project.jsonc", lambda data: data.update(architecture={"documents": [
        {"workflow": "configs/model.jsonc", "document": "ARCHITECTURE.jsonc"}]}))
    _edit(resource_ref(project, 'node', 'example.model'), lambda data: data.update(
        presentation={"fill": "#cceeff", "shape": "hex", "icon": "MODEL_ICON"},
        metadata={"domain": "example", "purpose": "svg acceptance"}))
    _edit(resource_ref(project, 'node', 'example.transform'), lambda data: data.update(
        presentation={"fill": "#dff7df", "shape": "rounded", "icon": "TRANSFORM_ICON"}))
    def declaration(data):
        data["external"] = True
        if level != "default":
            data["presentation"] = {"fill": "#fff2aa", "shape": "diamond", "icon": "NODE_ICON"}
    _edit(resource_ref(project, 'node', 'example.model'), declaration)
    def calls(data):
        node = next(item for item in data["pipeline"]["nodes"] if item["id"] == "model")
        if level in {"call", "planned"}:
            node["style"] = {"fill": "#ffe6ee", "shape": "circle", "icon": "CALL_ICON"}
        if level in {"planned", "status"}:
            declaration = json.loads((resource_ref(project, 'node', 'example.model')).read_text())
            node.update(status="planned", flow_kind="process", planned_behavior="transparent",
                requires=declaration["contract"]["requires"], provides=declaration["contract"]["provides"])
    _edit(project / "configs/model.jsonc", calls)
    output = tmp_path / "domain.svg"
    code = main(["review", "--workspace", str(workspace), "--config", str(project / "configs/model.jsonc"),
        "--output", str(output)])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0 and payload["published"] is True, payload
    document = json.loads(strip_jsonc_comments((project / "ARCHITECTURE.jsonc").read_text()))
    records = {item["id"]: item for item in document["workflow"]["nodes"]}
    model = records["model"]
    assert model["presentation"]["values"]["fill"] == fill
    assert model["presentation"]["values"]["shape"] == shape
    assert model["presentation"]["sources"]["fill"] == ("call" if level == "planned" else "node" if level == "default" else level)
    assert model["presentation"]["sources"]["icon"] == ("call" if level == "planned" else "node" if level == "status" else "node" if level == "default" else level)
    assert model["flow_kind"] == "process"
    assert "model_block" in model["tags"]
    expected = json.loads((resource_ref(project, 'node', 'example.model')).read_text())["rulesets"]
    assert model["selected_rulesets"] == expected
    assert model["metadata"]["purpose"] == "svg acceptance"
    root = ET.parse(output).getroot()
    assert root.get("aria-roledescription") == "flowchart-review-columns"
    actual = _node(root, target, "model")
    _assert_shape(actual, shape)
    assert re.search(r"fill:\s*" + fill + r"\b", ET.tostring(actual, encoding="unicode"))
    label = _label(actual)
    assert icon in label
    assert "flow_kind: process" in label and "model_block" in label
    assert "rulesets:" in label
    if level in {"planned", "status"}:
        assert "planned" in label and "unavailable" in label
        assert model["status"] == "planned"
    else:
        assert "EXTERNAL" in label
    transform = _node(root, target, "transform")
    assert re.search(r"fill:\s*#dff7df\b", ET.tostring(transform, encoding="unicode"))
    assert "TRANSFORM_ICON" in _label(transform)
    _assert_shape(transform, "rounded")


def test_review_rules_renders_real_svg_without_importing_implementations(svg_project, capsys, tmp_path):
    target, workspace, project = svg_project
    node_file = project / ("nodes/domain_nodes.py" if target == "python" else "nodes/model.ts")
    node_file.write_text("raise RuntimeError('must not import')\n" if target == "python" else "throw new Error('must not import');\n")
    rule_file = project / "plugins/code_plugin/rules" / ("model_definition.py" if target == "python" else "model_definition.ts")
    rule_file.write_text("raise RuntimeError('must not import')\n" if target == "python" else "throw new Error('must not import');\n")
    output = tmp_path / "rules.svg"
    assert main(["review-rules", "--workspace", str(workspace), "--config", str(project / "configs/model.jsonc"),
        "--node", "model", "--output", str(output)]) == 0, capsys.readouterr().out
    root = ET.parse(output).getroot()
    text = _label(root)
    assert "example.model_definition" in text and "example.model_domain" in text
    if target == "python":
        assert "model_forward" in text and "override:" in text
    assert len(list(root.iter())) > 20


@pytest.mark.parametrize("target", ["python", "javascript"])
def test_review_rules_svg_preserves_dependency_override_and_instance_origins(tmp_path, capsys, target):
    if not is_mermaid_svg_renderer_available():
        pytest.skip("requires the renderer prepared by verify_project.py --full")
    project = create_rule_graph_sandbox(tmp_path, target)
    document = project.read(project.graph_resource)
    document["relations"].append({"source": "$self", "target": "provider", "kind": "overrides",
        "params": {"value": 5}, "replace_rule": "example.replacement_provider"})
    project.write(project.graph_resource, document)
    for source in (project.project / "rules").glob("*.*"):
        source.write_text("raise RuntimeError('must not import')\n" if target == "python" else "throw new Error('must not import');\n")
    output = tmp_path / "relations.svg"
    assert main(["review-rules", *project.common_arguments(), "--node", "calculate", "--output", str(output)]) == 0, capsys.readouterr().out
    root = ET.parse(output).getroot()
    text = _label(root)
    assert "requires" in text and "overrides" in text
    assert "example.replacement_provider" in text and "example.number_checker" in text
    assert "value=5" in text and "override:" in text and "origin:" in text
    assert any("edgeLabel" in element.get("class", "").split() for element in root.iter())
