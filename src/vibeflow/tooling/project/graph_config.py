"""Filesystem and diagnostic adapter for the Core graph parser."""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any, Mapping

from vibeflow.core.flow import GraphConfig, LOOP_DEFINITION_IDS, NodeCallSpec
from vibeflow.core.config.graph import parse_graph_config_data
from vibeflow.tooling.project.diagnostic_sink import emit_core_diagnostic


def parse_graph_config(
    config: Mapping[str, Any],
    *,
    project_root: str | Path | None = None,
    root_id: str = "",
    root_path: str | Path | None = None,
    source_path: str | Path | None = None,
) -> GraphConfig:
    """Normalize path metadata, parse in Core, then emit optional diagnostics."""

    started = time.perf_counter()
    root_text = (
        str(Path(project_root).resolve()) if project_root is not None else ""
    )
    actual_root_path = (
        str(Path(root_path).resolve()) if root_path is not None else root_text
    )
    actual_source_path = (
        str(Path(source_path).resolve()) if source_path is not None else ""
    )
    graph = parse_graph_config_data(
        config,
        project_root=root_text,
        root_id=root_id,
        root_path=actual_root_path,
        source_path=actual_source_path,
    )
    if _trace_enabled():
        for index, (type_key, nodeset) in enumerate(graph.nodeset_types.items()):
            emit_core_diagnostic(
                "[vibeflow config] "
                f"parsed nodeset type_key={type_key} index={index} "
                f"nodes={len(nodeset.graph.nodes)} "
                f"refs={','.join(_nodeset_reference_targets(nodeset.graph.nodes)) or '-'} "
                "elapsed=0.0ms"
            )
        emit_core_diagnostic(
            "[vibeflow config] "
            f"parsed nodeset registry count={len(graph.nodeset_types)} elapsed=0.0ms"
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
        emit_core_diagnostic(
            "[vibeflow config] "
            f"parsed graph nodes={len(graph.nodes)} "
            f"nodeset_types={len(graph.nodeset_types)} elapsed={elapsed_ms}ms"
        )
    return graph


def _trace_enabled() -> bool:
    return str(os.environ.get("VIBEFLOW_CONFIG_TRACE", "")).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _nodeset_reference_targets(nodes: tuple[NodeCallSpec, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                node.loop.body
                for node in nodes
                if node.definition_id in LOOP_DEFINITION_IDS and node.loop.body
            }
        )
    )


__all__ = ["parse_graph_config"]
