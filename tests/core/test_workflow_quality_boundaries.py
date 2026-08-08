"""Directed checks for the Core/Python Target split."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def _run_isolated(source: str) -> None:
    environment = os.environ.copy()
    current = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(SOURCE_ROOT), current) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_core_config_and_quality_imports_are_boundary_pure() -> None:
    _run_isolated(
        """
import sys
import vibeflow.core.config.graph
import vibeflow.core.quality
import vibeflow.core.quality.workflow_rules.flow_data
import vibeflow.core.quality.workflow_rules.join_exclusivity

forbidden_prefixes = (
    'vibeflow.targets',
    'vibeflow.tooling',
    'vibeflow.graph_config',
    'vibeflow.health',
    'vibeflow.rendering',
)
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.')
           for prefix in forbidden_prefixes)
)
assert loaded == [], loaded
"""
    )


def test_tooling_path_adapter_keeps_core_parser_filesystem_free(
    tmp_path: Path,
) -> None:
    from vibeflow.core.config.graph import parse_graph_config_data
    from vibeflow.tooling.project.graph_config import parse_graph_config

    document = {
        "pipeline": {"nodes": [{"id": "node", "type_used": "test.node", "display_name": "Node", "description": "Exercises the path adapter."}]}
    }
    relative = Path("relative-project-root")
    core_graph = parse_graph_config_data(
        document,
        project_root=str(relative),
    )
    public_graph = parse_graph_config(
        document,
        project_root=tmp_path / relative,
    )

    assert core_graph.project_root == "relative-project-root"
    assert public_graph.project_root == str((tmp_path / relative).resolve())


def test_planned_structural_and_python_source_events_keep_finding_order(
    tmp_path: Path,
) -> None:
    from vibeflow.tooling.project.graph_config import parse_graph_config
    from vibeflow.targets.python.quality.workflow.planned import append_planned_findings
    from vibeflow.targets.python.quality.workflow.validation import _HealthValidationState

    graph = parse_graph_config(
        {
            "pipeline": {
                "nodes": [
                        {
                            "id": "planned",
                            "status": "planned",
                            "flow_kind": "process",
                            "display_name": "Planned",
                            "description": "Exercises planned finding order.",
                            "requires": [],
                            "provides": [],
                            "planned_behavior": {
                            "kind": "python_stub",
                            "stub_module": "stubs/missing.py",
                        },
                    }
                ]
            }
        },
        project_root=tmp_path,
    )
    state = _HealthValidationState()

    append_planned_findings(graph, state)

    assert [finding.rule_id for finding in state.warnings] == [
        "GRAPH.PLANNED.NODE",
        "GRAPH.PLANNED.PYTHON_STUB_DEV_ONLY",
    ]
    assert [finding.rule_id for finding in state.errors] == [
        "GRAPH.PLANNED.STUB_MISSING"
    ]


def test_python_plugin_loader_imports_no_outer_configuration_layer() -> None:
    _run_isolated(
        """
import sys
import vibeflow.targets.python.project.plugin_loader

forbidden_prefixes = (
    'vibeflow.config',
    'vibeflow.tooling',
)
loaded = sorted(
    name for name in sys.modules
    if any(name == prefix or name.startswith(prefix + '.')
           for prefix in forbidden_prefixes)
)
assert loaded == [], loaded
"""
    )
