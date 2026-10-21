from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Mapping

from vibeflow.core.flow import GraphConfig
from vibeflow.tooling.application.python.presentation.mermaid import MERMAID_LAYOUT_DEFAULT, _mapping_items, _rendered_resources_payload, export_mermaid
from vibeflow.tooling.presentation.mermaid import DEFAULT_MERMAID_MAX_EDGES, DEFAULT_MERMAID_MAX_TEXT_SIZE

from . import review_fragments as _review_fragments

from vibeflow.tooling.presentation.mermaid import layout as review_layout
from vibeflow.tooling.presentation.mermaid.types import REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH, SvgFragment


def render_review_columns_svg(
    graph: GraphConfig,
    compiled: object,
    output: Path,
    *,
    registry: object | None = None,
    resources: object | None = None,
    expand_nodesets: bool = False,
    show_contract: bool = True,
    show_semantics: bool = True,
    theme: str = "default",
    background: str = "transparent",
    max_text_size: int | None = None,
    max_edges: int | None = None,
    review_fragment_max_width: float = REVIEW_COLUMNS_MAX_FRAGMENT_WIDTH,
    prepared=None,
) -> None:
    from vibeflow.tooling.application.python.presentation.prepared import prepare_python_presentation

    prepared = prepared or prepare_python_presentation(graph, compiled=compiled, registry=registry, resources=resources)
    graph, compiled, registry = prepared.graph, prepared.compiled, prepared.registry
    resources = prepared.resources if resources is None else resources
    actual_review_fragment_max_width = review_layout._validate_review_fragment_max_width(review_fragment_max_width)
    actual_max_text_size = max_text_size if max_text_size is not None else DEFAULT_MERMAID_MAX_TEXT_SIZE
    actual_max_edges = max_edges if max_edges is not None else DEFAULT_MERMAID_MAX_EDGES
    with tempfile.TemporaryDirectory(prefix="vibeflow-review-svg-") as temp_dir:
        root = Path(temp_dir)
        columns = _build_columns(
            graph,
            compiled,
            root,
            registry=registry,
            resources=resources,
            expand_nodesets=expand_nodesets,
            show_contract=show_contract,
            show_semantics=show_semantics,
            theme=theme,
            background=background,
            max_text_size=actual_max_text_size,
            max_edges=actual_max_edges,
            review_fragment_max_width=actual_review_fragment_max_width,
            prepared=prepared,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(review_layout._compose_svg(columns, background=background, review_fragment_max_width=actual_review_fragment_max_width), encoding="utf-8")


def _build_columns(
    graph: GraphConfig,
    compiled: object,
    temp_dir: Path,
    *,
    registry: object | None,
    resources: object | None,
    expand_nodesets: bool,
    show_contract: bool,
    show_semantics: bool,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
    review_fragment_max_width: float,
    prepared=None,
) -> list[list[SvgFragment]]:
    columns: list[list[SvgFragment]] = [
        [
            _review_fragments._render_fragment(
                "main pipeline",
                export_mermaid(
                    graph,
                    compiled=compiled,
                    registry=registry,
                    expand_nodesets=False,
                    show_contract=show_contract,
                    show_semantics=show_semantics,
                    mermaid_layout=MERMAID_LAYOUT_DEFAULT,
                    prepared=prepared,
                ),
                temp_dir,
                theme=theme,
                background=background,
                max_text_size=max_text_size,
                max_edges=max_edges,
            )
        ]
    ]
    columns.extend(_resource_columns(graph, resources, temp_dir, registry=registry, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges))
    if expand_nodesets:
        nodeset_fragments = _review_fragments._nodeset_fragments(
            graph,
            temp_dir,
            registry=registry,
            show_contract=show_contract,
            show_semantics=show_semantics,
            theme=theme,
            background=background,
            max_text_size=max_text_size,
            max_edges=max_edges,
            review_fragment_max_width=review_fragment_max_width,
            prepared=prepared,
        )
        if nodeset_fragments:
            columns.append(nodeset_fragments)
    return columns


def _resource_columns(
    graph: GraphConfig,
    resources: object | None,
    temp_dir: Path,
    *,
    theme: str,
    background: str,
    max_text_size: int | None,
    max_edges: int | None,
    registry=None,
) -> list[list[SvgFragment]]:
    payload = _rendered_resources_payload(resources, graph, registry)
    columns: list[list[SvgFragment]] = []
    plugins = _mapping_items(payload.get("plugins", ()))
    if plugins:
        columns.append([_review_fragments._render_fragment("plugins", _review_fragments._resource_mermaid("plugins", plugins, kind="plugin"), temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges)])
    base_lib_payload = payload.get("base_lib", {})
    modules = _mapping_items(base_lib_payload.get("modules", ()) if isinstance(base_lib_payload, Mapping) else ())
    if modules:
        columns.append([_review_fragments._render_fragment("base_lib", _review_fragments._resource_mermaid("base_lib", modules, kind="base_lib"), temp_dir, theme=theme, background=background, max_text_size=max_text_size, max_edges=max_edges)])


    return columns
