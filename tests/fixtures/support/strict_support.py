from __future__ import annotations
from tests.fixtures.support.declarations import native_registry
from vibeflow.core.descriptors import NodeDescriptor, NodeContractDescriptor
from tests.fixtures.support.declarations import node_declaration, configured_declaration

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

import pytest

from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.flow import GraphConfigError
from vibeflow.core.findings import HealthFinding, HealthReport
from vibeflow.tooling.project.graph_config import parse_graph_config
from vibeflow.targets.shared.quality_support import QualityStructureLimits, QualityThresholds
from vibeflow.targets.python.project import GraphCompileError, GraphCompiler, NodeRegistry, PluginRegistry
from vibeflow.targets.python.quality import PurityPolicy, validate_graph_health
from vibeflow.targets.python.runtime.block_compiler import explain_block_compilation
from vibeflow.targets.python.runtime.engine import PipelineRuntime
from vibeflow.targets.python.runtime.errors import PipelineRuntimeError
from vibeflow.targets.python.runtime.options import RuntimeOptions
from vibeflow.targets.python.runtime.planning import (
    ExecutionPlan,
    NodeFrame,
    build_execution_plan,
)
from vibeflow.tooling.application.python.execution import CheckedRunError
from vibeflow.tooling.application.python.runner import run_checked
from vibeflow.tooling.application.python.presentation.ascii_flowchart import export_ascii_flowchart
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid
from vibeflow.tooling.presentation.mermaid import (
    is_mermaid_svg_renderer_available,
    render_mermaid_svg,
)
from vibeflow.tooling.project.config_loader import ConfigLoadError, load_config_document
from vibeflow.tooling.project.config_schema import collect_config_schema_findings
from vibeflow.tooling.application.python.project.effective_policy import resolve_effective_policy
from vibeflow.tooling.application.python.project.quality_scan import scan_code_quality
from vibeflow.tooling.project.schema_resources import schema_text

from .strict_support_boundaries import *
from .strict_support_runtime_nodes import *


def REQ_SPEC(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type.replace(".", " ").title()}


def PROV_SPEC(key: str, data_type: str | None = None) -> dict[str, str]:
    return {"key": key, "type": data_type or key, "display_name": key.replace(".", " ").title()}


def INPUT_SPEC(key: str, data_type: str | None = None, *, required: bool = True) -> dict:
    return {**PROV_SPEC(key, data_type), "required": required}


def _requirement_specs(values: list[str] | None) -> list[dict[str, str]]:
    return [REQ_SPEC(value) for value in values or []]


def _provider_specs(values: list[str] | None) -> list[dict[str, str]]:
    return [PROV_SPEC(value) for value in values or []]


def cli_main(args):
    if args and args[0] == "review-rules":
        from vibeflow.tooling.application.cli import main
    else:
        from vibeflow.tooling.application.python.cli import main

    return main(args)


def register_node(registry: NodeRegistry, descriptor, node_cls: type, schema: dict | None = None, defaults: dict | None = None, **kwargs):
    registry.register(configured_declaration(descriptor, schema, defaults), node_cls, **kwargs)


BadIoNode_DECLARATION = node_declaration(NodeDescriptor(type_key='test.bad_io', display_name='Bad IO', description='Illegally performs IO.', version='0.1.0', flow_kind='process', contract=NodeContractDescriptor()), NodeContractDescriptor(provides=(DataProvider(key='value.out', type='value.out', display_name='value.out'),), output_semantics={'value.out': ('output value',)}), rulesets=("vibeflow.process",))

class BadIoNode:

    def run_pure(self, inputs, params):
        time.sleep(0)
        return {"value.out": 1}


def _registry() -> NodeRegistry:
    from . import strict_support_runtime_nodes as runtime_nodes

    registry = native_registry()
    register_node(registry, runtime_nodes.StartNode_DECLARATION, runtime_nodes.StartNode)
    register_node(registry, runtime_nodes.ValueInputNode_DECLARATION, runtime_nodes.ValueInputNode)
    register_node(registry, runtime_nodes.OutEndNode_DECLARATION, runtime_nodes.OutEndNode)
    register_node(registry, runtime_nodes.InEndNode_DECLARATION, runtime_nodes.InEndNode)
    register_node(registry, runtime_nodes.SeedNode_DECLARATION, runtime_nodes.SeedNode, {"value": {"type": "number"}}, {"value": 1})
    register_node(registry, runtime_nodes.AddNode_DECLARATION, runtime_nodes.AddNode, {"delta": {"type": "number"}}, {"delta": 1})
    register_node(registry, runtime_nodes.CopyNode_DECLARATION, runtime_nodes.CopyNode)
    register_node(registry, runtime_nodes.IdentityObjectNode_DECLARATION, runtime_nodes.IdentityObjectNode)
    register_node(registry, runtime_nodes.NanOutputNode_DECLARATION, runtime_nodes.NanOutputNode)
    register_node(registry, runtime_nodes.RuntimeFailNode_DECLARATION, runtime_nodes.RuntimeFailNode, {"fail": {"type": "boolean"}}, {"fail": False})
    register_node(registry, runtime_nodes.CountingInitNode_DECLARATION, runtime_nodes.CountingInitNode, {"value": {"type": "number"}}, {"value": 3})
    register_node(registry, runtime_nodes.EffectRequestNode_DECLARATION, runtime_nodes.EffectRequestNode)
    return registry


def _nodeset_config(
    name: str,
    *,
    pipeline: dict,
    requires: list[str] | None = None,
    provides: list[str] | None = None,
    exports: list[str] | None = None,
) -> dict:
    return {
        "type_key": name,
        "display_name": name.replace(".", " ").title(),
        "description": f"Composite flow for {name}.",
        "requires": _requirement_specs(requires),
        "provides": _provider_specs(
            ["value.out"] if provides is None else provides
        ),
        "pipeline": pipeline,
    }


def _edge_chain(*names: str) -> list[dict[str, str]]:
    return [{"from": source, "to": target} for source, target in zip(names, names[1:])]


def _write_config_file(path: Path, data: dict) -> None:
    payload = dict(data)
    nodesets = payload.pop("nodesets", None)
    imports = list(payload.get("nodeset_imports") or [])
    if isinstance(nodesets, list):
        nodeset_dir = path.parent / f"{path.stem}_nodesets"
        nodeset_dir.mkdir(parents=True, exist_ok=True)
        for nodeset in nodesets:
            type_key = str(nodeset.get("type_key") or nodeset.get("name") or "nodeset")
            filename = re.sub(r"[^A-Za-z0-9_.-]+", "_", type_key).replace(".", "_") + ".jsonc"
            nodeset_path = nodeset_dir / filename
            nodeset_path.write_text(json.dumps(nodeset, indent=2), encoding="utf-8")
            imports.append({"path": nodeset_path.relative_to(path.parent).as_posix()})
    if imports:
        payload["nodeset_imports"] = imports
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _node_call(name: str, node_type: str, default_description: str, **fields) -> dict:
    node_id = str(fields.pop("id", fields.pop("name", name)))
    type_used = str(fields.pop("type_used", fields.pop("type", node_type)))
    if type_used.startswith("nodeset."):
        type_used = type_used.removeprefix("nodeset.")
    explicit_contract = (
        fields.get("status") == "planned"
        or type_used == "vibeflow.io"
        or type_used in {"vibeflow.loop", "vibeflow.loop.while"}
    )
    if explicit_contract:
        fields.setdefault("requires", [])
        fields.setdefault("provides", [])
    return {
        "id": node_id,
        "type_used": type_used,
        "display_name": node_id.replace("_", " ").title(),
        "description": default_description,
        **fields,
    }


def _seed_add_pipeline(*, seed: dict | None = None, add: dict | None = None) -> dict:
    seed_fields = dict(seed or {})
    seed_defaults = seed_fields
    seed_node = _node_call(str(seed_defaults.pop("id", seed_defaults.pop("name", "seed"))), str(seed_defaults.pop("type_used", seed_defaults.pop("type", "test.seed"))), "Produces the initial value.", **seed_defaults)
    add_fields = dict(add or {})
    add_defaults = add_fields
    add_node = _node_call(str(add_defaults.pop("id", add_defaults.pop("name", "add"))), str(add_defaults.pop("type_used", add_defaults.pop("type", "test.add"))), "Adds delta to value.in.", **add_defaults)
    return {
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            seed_node,
            add_node,
            _node_call("end", "test.out_end", "Ends after value.out is ready."),
        ],
        "edges": _edge_chain("start", "seed", "add", "end"),
        "outputs": [REQ_SPEC("value.out")],
    }


def _seed_only_pipeline(*, seed: dict | None = None) -> dict:
    seed_fields = dict(seed or {})
    seed_defaults = seed_fields
    seed_node = _node_call(str(seed_defaults.pop("id", seed_defaults.pop("name", "seed"))), str(seed_defaults.pop("type_used", seed_defaults.pop("type", "test.seed"))), "Produces the initial value.", **seed_defaults)
    return {
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            seed_node,
            _node_call("end", "test.in_end", "Ends after value.in is ready."),
        ],
        "edges": _edge_chain("start", "seed", "end"),
        "outputs": [REQ_SPEC("value.in")],
    }


def _input_add_pipeline(*, add: dict | None = None) -> dict:
    add_fields = dict(add or {})
    add_defaults = add_fields
    add_node = _node_call(str(add_defaults.pop("id", add_defaults.pop("name", "add"))), str(add_defaults.pop("type_used", add_defaults.pop("type", "test.add"))), "Adds delta to value.in.", **add_defaults)
    add_name = str(add_node["id"])
    return {
        "inputs": [INPUT_SPEC("value.in")],
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            add_node,
            _node_call("end", "test.out_end", "Ends after value.out is ready."),
        ],
        "edges": _edge_chain("start", add_name, "end"),
        "outputs": [REQ_SPEC("value.out")],
    }


def _write_base_lib_chain(tmp_path: Path, modules: list[str]) -> None:
    base_dir = tmp_path / "base_lib"
    base_dir.mkdir()
    (base_dir / "__init__.py").write_text("", encoding="utf-8")
    for index, name in enumerate(modules):
        next_name = modules[index + 1] if index + 1 < len(modules) else ""
        body = f"import base_lib.{next_name}\n\n\ndef helper():\n    return base_lib.{next_name}.helper()\n" if next_name else "\ndef helper():\n    return 1\n"
        (base_dir / f"{name}.py").write_text(body, encoding="utf-8")


def _clear_base_lib_modules() -> None:
    for name in tuple(sys.modules):
        if name == "base_lib" or name.startswith("base_lib."):
            sys.modules.pop(name, None)


@pytest.fixture(autouse=True)
def _isolate_base_lib_modules():
    _clear_base_lib_modules()
    yield
    _clear_base_lib_modules()


def _repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "pyproject.toml").is_file() and (candidate / "src" / "vibeflow").is_dir():
            return candidate
    raise AssertionError("could not locate the VibeFlow repository root")


def _load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


__all__ = [name for name in globals() if not name.startswith("__")]
