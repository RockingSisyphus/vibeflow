from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path

import pytest

from vibeflow import (
    DataProvider,
    DataRequirement,
    ConfigLoadError,
    ExecutionPlan,
    GraphCompileError,
    GraphCompiler,
    HealthFinding,
    HealthReport,
    NodeContract,
    NodeFrame,
    NodeInfo,
    NodeRegistry,
    PipelineRuntime,
    PipelineRuntimeError,
    RuntimeOptions,
    CheckedRunError,
    BaseLibInfo,
    PluginRegistry,
    PluginInfo,
    STABLE_PUBLIC_API,
    schema_text,
    export_ascii_flowchart,
    export_mermaid,
    explain_block_compilation,
    is_mermaid_svg_renderer_available,
    load_config_document,
    parse_graph_config,
    resolve_effective_policy,
    render_mermaid_svg,
    run_checked,
    scan_base_lib,
    validate_graph_health,
    build_execution_plan,
)
from vibeflow.graph_config import GraphConfigError
from vibeflow.config.schema import collect_config_schema_findings
from vibeflow.devtools import QualityStructureLimits, QualityThresholds, scan_code_quality
from vibeflow.purity.types import PurityPolicy

from .strict_support_boundaries import *
from .strict_support_runtime_nodes import *


def REQ_SPEC(data_type: str, cardinality: str = "exactly_one") -> dict[str, str]:
    return {"type": data_type, "cardinality": cardinality, "display_name": data_type.replace(".", " ").title()}


def PROV_SPEC(key: str, data_type: str | None = None) -> dict[str, str]:
    return {"key": key, "type": data_type or key, "display_name": key.replace(".", " ").title()}


def _requirement_specs(values: list[str] | None) -> list[dict[str, str]]:
    return [REQ_SPEC(value) for value in values or []]


def _provider_specs(values: list[str] | None) -> list[dict[str, str]]:
    return [PROV_SPEC(value) for value in values or []]


def cli_main(args):
    from vibeflow.cli import main

    return main(args)


def collect_node_metrics(*args, **kwargs):
    from vibeflow.purity import collect_node_metrics as impl

    return impl(*args, **kwargs)


def validate_node_class(*args, **kwargs):
    from vibeflow.purity import validate_node_class as impl

    return impl(*args, **kwargs)


def register_node(registry: NodeRegistry, key: str, node_cls: type, schema: dict | None = None, defaults: dict | None = None, **kwargs):
    registry.register(key, node_cls, config_schema=schema or {}, config_defaults=defaults or {}, **kwargs)


class BadIoNode:
    NODE_INFO = NodeInfo(
        type_key="test.bad_io",
        display_name="Bad IO",
        category="test",
        description="Illegally performs IO.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=(DataProvider(key="value.out", type="value.out"),),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        time.sleep(0)
        return {"value.out": 1}


def _registry() -> NodeRegistry:
    from . import strict_support_runtime_nodes as runtime_nodes

    registry = NodeRegistry()
    register_node(registry, "test.start", runtime_nodes.StartNode)
    register_node(registry, "test.value_input", runtime_nodes.ValueInputNode)
    register_node(registry, "test.out_end", runtime_nodes.OutEndNode)
    register_node(registry, "test.in_end", runtime_nodes.InEndNode)
    register_node(registry, "test.seed", runtime_nodes.SeedNode, {"value": {"type": "number"}}, {"value": 1})
    register_node(registry, "test.add", runtime_nodes.AddNode, {"delta": {"type": "number"}}, {"delta": 1})
    register_node(registry, "test.copy", runtime_nodes.CopyNode)
    register_node(registry, "test.identity_object", runtime_nodes.IdentityObjectNode)
    register_node(registry, "test.nan_output", runtime_nodes.NanOutputNode)
    register_node(registry, "test.runtime_fail", runtime_nodes.RuntimeFailNode, {"fail": {"type": "boolean"}}, {"fail": False})
    register_node(registry, "test.counting_init", runtime_nodes.CountingInitNode, {"value": {"type": "number"}}, {"value": 3})
    register_node(registry, "test.effect_request", runtime_nodes.EffectRequestNode)
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
        "provides": _provider_specs(provides or ["value.out"]),
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
    return {
        "id": node_id,
        "type_used": type_used,
        "display_name": node_id.replace("_", " ").title(),
        "description": default_description,
        **fields,
    }


def _seed_add_pipeline(*, seed: dict | None = None, add: dict | None = None) -> dict:
    seed_fields = dict(seed or {})
    seed_defaults = {"provides": [PROV_SPEC("value.in")], **seed_fields}
    seed_node = _node_call(str(seed_defaults.pop("id", seed_defaults.pop("name", "seed"))), str(seed_defaults.pop("type_used", seed_defaults.pop("type", "test.seed"))), "Produces the initial value.", **seed_defaults)
    add_fields = dict(add or {})
    add_defaults = {"requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("value.out")], **add_fields}
    add_node = _node_call(str(add_defaults.pop("id", add_defaults.pop("name", "add"))), str(add_defaults.pop("type_used", add_defaults.pop("type", "test.add"))), "Adds delta to value.in.", **add_defaults)
    return {
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            seed_node,
            add_node,
            _node_call("end", "test.out_end", "Ends after value.out is ready.", requires=[REQ_SPEC("value.out")]),
        ],
        "edges": _edge_chain("start", "seed", "add", "end"),
        "outputs": [REQ_SPEC("value.out")],
    }


def _seed_only_pipeline(*, seed: dict | None = None) -> dict:
    seed_fields = dict(seed or {})
    seed_defaults = {"provides": [PROV_SPEC("value.in")], **seed_fields}
    seed_node = _node_call(str(seed_defaults.pop("id", seed_defaults.pop("name", "seed"))), str(seed_defaults.pop("type_used", seed_defaults.pop("type", "test.seed"))), "Produces the initial value.", **seed_defaults)
    return {
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            seed_node,
            _node_call("end", "test.in_end", "Ends after value.in is ready.", requires=[REQ_SPEC("value.in")]),
        ],
        "edges": _edge_chain("start", "seed", "end"),
        "outputs": [REQ_SPEC("value.in")],
    }


def _input_add_pipeline(*, add: dict | None = None) -> dict:
    add_fields = dict(add or {})
    add_defaults = {"requires": [REQ_SPEC("value.in")], "provides": [PROV_SPEC("value.out")], **add_fields}
    add_node = _node_call(str(add_defaults.pop("id", add_defaults.pop("name", "add"))), str(add_defaults.pop("type_used", add_defaults.pop("type", "test.add"))), "Adds delta to value.in.", **add_defaults)
    add_name = str(add_node["id"])
    return {
        "inputs": [PROV_SPEC("value.in")],
        "nodes": [
            _node_call("start", "test.start", "Starts the flow."),
            add_node,
            _node_call("end", "test.out_end", "Ends after value.out is ready.", requires=[REQ_SPEC("value.out")]),
        ],
        "edges": _edge_chain("start", add_name, "end"),
        "outputs": [REQ_SPEC("value.out")],
    }


VALID_NODE_IMPORT = """from vibeflow import DataProvider, DataRequirement, NodeContract, NodeInfo


def REQ(data_type: str, cardinality: str = "exactly_one") -> DataRequirement:
    return DataRequirement(type=data_type, cardinality=cardinality)


def PROV(key: str, data_type: str | None = None) -> DataProvider:
    return DataProvider(key=key, type=data_type or key)


""".rstrip() + "\n\n"


VALID_NODE_INFO = """
    NODE_INFO = NodeInfo(
        type_key="demo.node",
        display_name="Demo",
        category="demo",
        description="Demo node.",
        version="0.1.0",
        flow_kind="process",
    )
""".rstrip()


VALID_NODE_CONTRACT = """
    CONTRACT = NodeContract(
        provides=(PROV("demo.out"),),
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}},),
    )
""".rstrip()


def _inspect_node_source(tmp_path, capsys, source: str, *, node_type: str = "demo.node", class_name: str = "DemoNode", extra_args=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(source.strip(), encoding="utf-8")
    args = ["inspect-node", "--type", node_type, "--module", str(module_path), "--class", class_name]
    if extra_args:
        args.extend(extra_args)
    code = cli_main(args)
    return code, json.loads(capsys.readouterr().out)


def _valid_node_source(*, run_body: str = '        return {"demo.out": 1}', contract: str = VALID_NODE_CONTRACT, info: str = VALID_NODE_INFO) -> str:
    return f"""
{VALID_NODE_IMPORT}
class DemoNode:
{info}
{contract}

    def run_pure(self, inputs, params):
{run_body}
"""


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
    return Path(__file__).resolve().parents[2]


def _load_module_from_path(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _failure_case_source(case: dict[str, object]) -> str:
    kind = str(case.get("kind", ""))
    if kind == "generated_giant_node":
        return _valid_node_source() + "\n" + "\n".join("    # filler line" for _ in range(510))
    if kind == "node_mutual_call":
        return f"""
{VALID_NODE_IMPORT}
class OtherNode:
    NODE_INFO = NodeInfo(type_key="demo.other", display_name="Other", category="demo", description="Other node.", version="0.1.0", flow_kind="process")
    CONTRACT = NodeContract(provides=(PROV("other.out"),), output_semantics={{"other.out": ("other output",)}}, output_schema={{"other.out": {{"type": "number"}}}}, examples=({{"inputs": {{}}, "params": {{}}}},))

    def run_pure(self, inputs, params):
        return {{"other.out": 1}}


class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        OtherNode().run_pure({{}}, {{}})
        return {{"demo.out": 1}}
"""
    if kind == "module_top_level_side_effect":
        return f"""
{VALID_NODE_IMPORT}
len([])

class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        return {{"demo.out": 1}}
"""
    return _valid_node_source(run_body=str(case["run_body"]))


__all__ = [name for name in globals() if not name.startswith("__")]
