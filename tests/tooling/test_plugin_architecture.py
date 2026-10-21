from __future__ import annotations
from tests.fixtures.support.declarations import write_node_plugin

import json
import re
from pathlib import Path

from tests.fixtures.support.strict_support import _seed_add_pipeline

from vibeflow.core.descriptors import PluginCatalog
from vibeflow.tooling.application.python.presentation.architecture_document import (
    build_architecture_document,
)
from vibeflow.tooling.application.python.presentation.compiled_document import compiled_graph_payload
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.application.python.workspace_service import (
    load_workspace_config,
    load_workspace_graph_for_export,
    validate_workspace_config_path,
)
from vibeflow.tooling.project.plugin_review import (
    load_plugin_review_resources,
)


def test_planned_static_plugin_is_complete_without_descriptor() -> None:
    resources = load_plugin_review_resources(
        {
            "plugins": [
                {
                    "id": "demo.future_runtime",
                    "status": "planned",
                    "type": "runtime",
                    "targets": ["browser"],
                    "config": {"level": "future"},
                    "display_name": "Future Runtime",
                    "description": "Provides a future runtime extension.",
                }
            ]
        },
        catalog=PluginCatalog(),
    )

    assert [item.to_dict() for item in resources] == [
        {
            "id": "demo.future_runtime",
            "name": "demo.future_runtime",
            "type": "runtime",
            "status": "planned",
            "targets": ["browser"],
            "dependencies": [],
            "config": {"level": "future"},
            "config_keys": ["level"],
            "priority": 100,
            "display_name": "Future Runtime",
            "category": "",
            "description": "Provides a future runtime extension.",
            "version": "",
            "rulesets": [],
        }
    ]


def test_implemented_static_plugin_architecture_uses_only_review_facts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_path, workflow_path, source_path = _write_plugin_workspace(
        tmp_path,
        include_planned=False,
    )
    # Loading a trusted fixed SDK declaration is allowed; its runtime factory
    # must remain untouched during review.
    graph, compiled, registry, resources, error = load_workspace_graph_for_export(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert error is None
    resource = resources.to_dict()["plugins"][0]
    assert resource["type"] == "runtime"
    assert resource["targets"] == ["python"]
    assert resource["config"] == {"label": "selected", "mode": "audit"}
    assert "implementation" not in resource
    assert resource["module"] == "plugin"
    assert resource["class"] == "runtime"

    document = build_architecture_document(
        graph,
        compiled=compiled,
        registry=registry,
        resources=resources,
    )
    plugin = document["resources"]["plugins"][0]
    assert plugin["targets"] == ["python"]
    assert plugin["config"] == {"label": "selected", "mode": "audit"}
    assert plugin["priority"] == 20
    assert plugin["module"] == "plugin" and plugin["class"] == "runtime"
    assert "plugins/runtime_audit/plugin.py" in json.dumps(document)


def test_planned_static_plugin_marks_workspace_and_payload_not_production_ready(
    tmp_path: Path,
) -> None:
    workspace_path, workflow_path, _ = _write_plugin_workspace(
        tmp_path,
        include_planned=True,
    )
    workspace = load_workspace_config(workspace_path)
    report = validate_workspace_config_path(workflow_path, workspace=workspace)
    graph, compiled, _, resources, error = load_workspace_graph_for_export(
        workflow_path,
        workspace=workspace,
    )

    assert error is None
    assert report.status not in {"FAIL", "ERROR"}
    assert report.info["production_ready"] is False
    assert [item["status"] for item in report.info["resources"]["plugins"]] == [
        "implemented",
        "planned",
    ]
    assert compiled_graph_payload(
        graph,
        compiled,
        resources=resources,
    )["production_ready"] is False
    assert not any(
        finding.rule_id == "PLUGIN.LOAD"
        for finding in (*report.errors, *report.warnings)
    )


def test_static_plugins_render_in_mermaid_with_planned_status(
    tmp_path: Path,
) -> None:
    workspace_path, workflow_path, _ = _write_plugin_workspace(
        tmp_path,
        include_planned=True,
    )
    graph, compiled, registry, resources, error = load_workspace_graph_for_export(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert error is None
    mermaid = export_mermaid(
        graph,
        compiled=compiled,
        registry=registry,
        resources=resources,
    )
    assert "resource_plugins" in mermaid
    assert "Runtime Audit" in mermaid
    assert "Future Compiler" in mermaid
    # The directory lists selected packages, not lifecycle factory contracts.
    assert "id: demo.runtime_audit\\n" in mermaid
    assert "class: runtime" not in mermaid
    assert "config: label, mode" in mermaid
    planned = re.search(r'(resource_plugins_\d+)@\{[^\n]*Future Compiler', mermaid)
    assert planned and f"class {planned[1]} plannedResource;" in mermaid


def _write_plugin_workspace(
    tmp_path: Path,
    *,
    include_planned: bool,
) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    project = repository / "project"
    configs = project / "configs"
    configs.mkdir(parents=True)
    workspace_path = repository / "vibeflow_config.jsonc"
    workflow_path = configs / "main.jsonc"
    workspace_path.write_text(json.dumps({"roots": [{"id": "project", "path": "project"}]}))
    (project / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python"}))
    node_selection = write_node_plugin(project, [("test.start", "StartNode", {}, {}),
        ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
        ("test.add", "AddNode", {"delta": {"type": "number"}}, {"delta": 1}),
        ("test.out_end", "OutEndNode", {}, {})])
    source_path = project / "plugins/runtime_audit/plugin.py"
    source_path.parent.mkdir(parents=True,exist_ok=True)
    source_path.write_text('from vibeflow.targets.python.sdk import Plugin\ndef runtime(context):\n    raise AssertionError("runtime factory invoked during review")\nplugin = Plugin(id="demo.runtime_audit", runtime=runtime, priority=20, display_name="Runtime Audit", description="Audits one invocation", config_schema={"type":"object","properties":{"mode":{"type":"string"},"label":{"type":"string"}}},config_defaults={"mode":"audit"})\n')
    plugins = [node_selection, {"source": {"kind": "file", "ref": "plugins/runtime_audit/plugin.py", "export": "plugin"}, "config": {"label": "selected"}}]
    if include_planned:
        plugins.append({"id": "demo.future_compiler", "status": "planned", "type": "compiler",
            "targets": ["browser"], "config": {"phase": "future"}, "display_name": "Future Compiler",
            "description": "Reviews a future compiler hook."})
    workflow_path.write_text(json.dumps({"plugins": plugins, "pipeline": _seed_add_pipeline()}))
    return workspace_path, workflow_path, source_path
