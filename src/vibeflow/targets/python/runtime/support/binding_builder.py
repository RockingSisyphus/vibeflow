"""Build the opaque Python binding sidecar for an execution plan."""

from __future__ import annotations

from typing import Mapping, Protocol

from vibeflow.block_compiler.compiler import _block_id
from vibeflow.block_compiler.model import SourceRef
from vibeflow.targets.python.project.bindings import PythonBindingPlan, PythonCallBinding


class _Frame(Protocol):
    type_used: str
    node: object | None
    params: Mapping[str, object]
    is_planned_stub: bool
    planned_stub_module: str
    planned_stub_path: str
    planned_stub_hash: str
    subplan: object | None


def build_python_binding_plan(
    frames: Mapping[str, _Frame],
    *,
    order: tuple[str, ...],
    path: tuple[str, ...],
    plugin_registry: object | None,
) -> PythonBindingPlan:
    """Keep Python objects beside, never inside, the portable workflow plan."""

    calls: list[PythonCallBinding] = []
    children: list[PythonBindingPlan] = []
    for node_id in order:
        frame = frames[node_id]
        binding = _python_call_binding(frame, path=(*path, node_id))
        if binding is not None:
            calls.append(binding)
        if frame.subplan is not None:
            children.append(frame.subplan.python_bindings)
    return PythonBindingPlan(
        block_id=_block_id(path),
        calls=tuple(calls),
        children=tuple(children),
        plugin_registry=plugin_registry,
    )


def _python_call_binding(
    frame: _Frame,
    *,
    path: tuple[str, ...],
) -> PythonCallBinding | None:
    if frame.node is not None:
        implementation_type = type(frame.node)
        return PythonCallBinding(
            path=path,
            type_key=frame.type_used,
            implementation=frame.node,
            effective_params=frame.params,
            source=SourceRef(
                kind="python",
                ref=implementation_type.__module__,
                export=implementation_type.__qualname__,
            ),
        )
    if not frame.is_planned_stub:
        return None
    # Planned stubs intentionally bind only their validated source location.
    # The runtime remains authoritative and loads ``run_stub`` lazily when the
    # planned frame is actually executed.
    return PythonCallBinding(
        path=path,
        type_key=frame.type_used,
        implementation=frame.planned_stub_path or frame.planned_stub_module,
        effective_params=frame.params,
        source=SourceRef(
            kind="python_stub",
            ref=frame.planned_stub_module,
            export="run_stub",
        ),
        source_hash=frame.planned_stub_hash,
    )


__all__ = ["build_python_binding_plan"]
