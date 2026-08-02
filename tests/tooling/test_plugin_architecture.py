from __future__ import annotations

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
                    "id": "demo.future_policy",
                    "status": "planned",
                    "type": "policy",
                    "targets": ["browser"],
                    "config": {"level": "future"},
                    "display_name": "Future Policy",
                    "description": "Reviews a future policy.",
                }
            ]
        },
        catalog=PluginCatalog(),
    )

    assert [item.to_dict() for item in resources] == [
        {
            "id": "demo.future_policy",
            "name": "demo.future_policy",
            "type": "policy",
            "status": "planned",
            "targets": ["browser"],
            "dependencies": [],
            "config": {"level": "future"},
            "config_keys": ["level"],
            "priority": 100,
            "display_name": "Future Policy",
            "category": "",
            "description": "Reviews a future policy.",
            "version": "",
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
    source_path.parent.mkdir(exist_ok=True)
    source_path.write_text("throw new Error('must not be read');\n", encoding="utf-8")
    original_read_text = Path.read_text

    def guarded_read_text(path: Path, *args, **kwargs):
        if path.resolve() == source_path.resolve():
            raise AssertionError("Plugin source was read during architecture review")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    graph, compiled, registry, resources, error = load_workspace_graph_for_export(
        workflow_path,
        workspace=load_workspace_config(workspace_path),
    )

    assert error is None
    resource = resources.to_dict()["plugins"][0]
    assert resource["type"] == "runtime"
    assert resource["targets"] == ["browser", "node"]
    assert resource["config"] == {"label": "selected", "mode": "audit"}
    assert "implementation" not in resource
    assert "module" not in resource
    assert "class" not in resource

    document = build_architecture_document(
        graph,
        compiled=compiled,
        registry=registry,
        resources=resources,
    )
    plugin = document["resources"]["plugins"][0]
    assert plugin["targets"] == ["browser", "node"]
    assert plugin["config"] == {"label": "selected", "mode": "audit"}
    assert plugin["priority"] == 20
    assert "module" not in plugin and "class" not in plugin
    assert "plugins/runtime_audit.ts" not in json.dumps(document)


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
    assert "targets: browser, node" in mermaid
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
                "registry": "registry.py:build_node_registry",
                "quality_enabled": False,
                "descriptors": {"plugins": ["manifests/plugins"]},
            }
        ),
        encoding="utf-8",
    )
    (project / "registry.py").write_text(
        "\n".join(
            (
                "from vibeflow.targets.python.project import NodeRegistry",
                "from tests.fixtures.support import strict_support_runtime_nodes as nodes",
                "",
                "def build_node_registry():",
                "    registry = NodeRegistry()",
                "    registry.register('test.start', nodes.StartNode, config_schema={}, config_defaults={})",
                "    registry.register('test.seed', nodes.SeedNode, config_schema={'value': {'type': 'number'}}, config_defaults={'value': 1})",
                "    registry.register('test.add', nodes.AddNode, config_schema={'delta': {'type': 'number'}}, config_defaults={'delta': 1})",
                "    registry.register('test.out_end', nodes.OutEndNode, config_schema={}, config_defaults={})",
                "    return registry",
                "",
            )
        ),
        encoding="utf-8",
    )
    (manifests / "runtime-audit.jsonc").write_text(
        json.dumps(
            {
                "kind": "plugin",
                "id": "demo.runtime_audit",
                "type": "runtime",
                "targets": ["browser", "node"],
                "display_name": "Runtime Audit",
                "category": "review",
                "description": "Audits one workflow invocation.",
                "version": "1.0.0",
                "priority": 20,
                "implementations": [
                    {
                        "language": "typescript",
                        "targets": ["browser", "node"],
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
    return workspace_path, workflow_path, source_path
