from __future__ import annotations
from tests.fixtures.support.declarations import write_node_manifests

import json
from pathlib import Path

from tests.fixtures.support.strict_support import _seed_add_pipeline

from vibeflow.core.descriptors import PluginCatalog
from vibeflow.tooling.application.python.presentation.architecture_document import (
    build_architecture_document,
)
from vibeflow.tooling.application.python.presentation.mermaid import (
    compiled_graph_payload,
    export_mermaid,
)
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
    assert resource["module"] == str(source_path)
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
    assert plugin["module"] == "plugins/runtime_audit.py" and plugin["class"] == "runtime"
    assert "plugins/runtime_audit.py" in json.dumps(document)


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
    assert "targets: python" in mermaid
    assert "config: label, mode" in mermaid
    assert "class resource_plugins_1 plannedResource;" in mermaid


def _write_plugin_workspace(
    tmp_path: Path,
    *,
    include_planned: bool,
) -> tuple[Path, Path, Path]:
    repository = tmp_path / "repository"
    project = repository / "project"
    configs = project / "configs"
    manifests = project / "manifests" / "plugins"
    configs.mkdir(parents=True)
    manifests.mkdir(parents=True)
    workspace_path = repository / "vibeflow_config.jsonc"
    workflow_path = configs / "main.jsonc"
    source_path = project / "plugins" / "runtime_audit.ts"
    workspace_path.write_text(
        json.dumps(
            {"policy": {}, "roots": [{"id": "project", "path": "project"}]}
        ),
        encoding="utf-8",
    )
    (project / "vibeflow_project.jsonc").write_text(
        json.dumps(
            {
                "project_target": "python",
                "quality_enabled": False,
                "descriptors": {"nodes": ["manifests/nodes"], "plugins": ["manifests/plugins"]},
            }
        ),
        encoding="utf-8",
    )
    write_node_manifests(project, [("test.start", "StartNode", {}, {}),
        ("test.seed", "SeedNode", {"value": {"type": "number"}}, {"value": 1}),
        ("test.add", "AddNode", {"delta": {"type": "number"}}, {"delta": 1}),
        ("test.out_end", "OutEndNode", {}, {})])
    (manifests / "runtime-audit.jsonc").write_text(
        json.dumps(
            {
                "kind": "plugin",
                "id": "demo.runtime_audit",
                "type": "runtime",
                "targets": ["python"],
                "display_name": "Runtime Audit",
                "category": "review",
                "description": "Audits one workflow invocation.",
                "version": "1.0.0",
                "priority": 20,
                "implementations": [
                    {
                        "language": "typescript",
                        "targets": ["python"],
                        "completion": "immediate",
                        "source": {
                            "kind": "file",
                            "ref": "plugins/runtime_audit.ts",
                            "export": "createPlugin",
                        },
                    }
                ],
                "dependencies": [],
                "external_packages": [],
                "config": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "mode": {"type": "string"},
                            "label": {"type": "string"},
                        },
                    },
                    "defaults": {"mode": "audit"},
                },
            }
        ),
        encoding="utf-8",
    )
    plugins: list[object] = [
        {"id": "demo.runtime_audit", "config": {"label": "selected"}}
    ]
    if include_planned:
        plugins.append(
            {
                "id": "demo.future_compiler",
                "status": "planned",
                "type": "compiler",
                "targets": ["browser"],
                "config": {"phase": "future"},
                "display_name": "Future Compiler",
                "description": "Reviews a future compiler hook.",
            }
        )
    workflow_path.write_text(
        json.dumps({"plugins": plugins, "pipeline": _seed_add_pipeline()}),
        encoding="utf-8",
    )
    from tests.fixtures.support.code_plugins import migrate_fixture
    # The actual SDK package is Python; native callbacks are delayed until run.
    project_document = json.loads((project / "vibeflow_project.jsonc").read_text())
    project_document["descriptors"].pop("plugins")
    (project / "vibeflow_project.jsonc").write_text(json.dumps(project_document))
    migrate_fixture(project)
    source_path = project / "plugins/runtime_audit.py"
    source_path.parent.mkdir(exist_ok=True)
    source_path.write_text('from vibeflow.targets.python.sdk import Plugin\ndef runtime(context):\n    raise AssertionError("runtime factory invoked during review")\nplugin = Plugin(id="demo.runtime_audit", runtime=runtime, priority=20, display_name="Runtime Audit", description="Audits one invocation", config_schema={"type":"object","properties":{"mode":{"type":"string"},"label":{"type":"string"}}},config_defaults={"mode":"audit"})\n')
    workflow = json.loads(workflow_path.read_text())
    workflow["plugins"] = [item for item in workflow["plugins"] if item.get("status") == "planned" or item.get("source")]
    workflow["plugins"].append({"source":{"kind":"file","ref":"plugins/runtime_audit.py"},"config":{"label":"selected"}})
    workflow_path.write_text(json.dumps(workflow))
    return workspace_path, workflow_path, source_path
