from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from topology_kernel import (
    ConfigLoadError,
    GraphCompileError,
    GraphCompiler,
    HealthFinding,
    HealthReport,
    NodeContract,
    NodeInfo,
    NodeRegistry,
    PipelineRuntime,
    PipelineRuntimeError,
    CheckedRunError,
    PluginRegistry,
    STABLE_PUBLIC_API,
    schema_text,
    export_ascii_flowchart,
    export_mermaid,
    load_config_document,
    parse_graph_config,
    resolve_effective_policy,
    run_checked,
    scan_base_lib,
    validate_graph_health,
)
from topology_kernel.graph_config import GraphConfigError
from topology_kernel.config_schema import collect_config_schema_findings
from topology_kernel.devtools import QualityThresholds, scan_code_quality
from topology_kernel.purity_types import PurityPolicy


def cli_main(args):
    from topology_kernel.cli import main

    return main(args)


def collect_node_metrics(*args, **kwargs):
    from topology_kernel.purity import collect_node_metrics as impl

    return impl(*args, **kwargs)


def validate_node_class(*args, **kwargs):
    from topology_kernel.purity import validate_node_class as impl

    return impl(*args, **kwargs)


def register_node(registry: NodeRegistry, key: str, node_cls: type, schema: dict | None = None, defaults: dict | None = None, **kwargs):
    registry.register(key, node_cls, config_schema=schema or {}, config_defaults=defaults or {}, **kwargs)


class StartNode:
    NODE_INFO = NodeInfo("test.start", "Start", "test", "Starts a test flow.", "0.1.0", "terminal")
    CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}, "outputs": {}},))

    def run_pure(self, inputs, params):
        return {}


class ValueInputNode:
    NODE_INFO = NodeInfo("test.value_input", "Value Input", "test", "Reads value.in.", "0.1.0", "io")
    CONTRACT = NodeContract(
        requires=("value.in",),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class OutEndNode:
    NODE_INFO = NodeInfo("test.out_end", "Out End", "test", "Ends after value.out.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=("value.out",),
        input_semantics={"value.out": ("output value",)},
        examples=({"inputs": {"value.out": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class InEndNode:
    NODE_INFO = NodeInfo("test.in_end", "In End", "test", "Ends after value.in.", "0.1.0", "terminal")
    CONTRACT = NodeContract(
        requires=("value.in",),
        input_semantics={"value.in": ("input value",)},
        examples=({"inputs": {"value.in": 1}, "params": {}, "outputs": {}},),
    )

    def run_pure(self, inputs, params):
        return {}


class SeedNode:
    NODE_INFO = NodeInfo(
        type_key="test.seed",
        display_name="Seed",
        category="test",
        description="Produces a seed value.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.in",),
        output_semantics={"value.in": ("seed value",)},
        params_schema={"value": {"type": "number"}},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {}, "params": {"value": 4}, "outputs": {"value.in": 4}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": params.get("value", 1)}


class AddNode:
    NODE_INFO = NodeInfo(
        type_key="test.add",
        display_name="Add",
        category="test",
        description="Adds delta to input.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        params_schema={"delta": {"type": "number"}},
        output_schema={"value.out": {"type": "number"}},
        examples=({"inputs": {"value.in": 4}, "params": {"delta": 3}, "outputs": {"value.out": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.out": inputs["value.in"] + params.get("delta", 1)}


class CopyNode:
    NODE_INFO = NodeInfo(
        type_key="test.copy",
        display_name="Copy",
        category="test",
        description="Copies a value.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.out",),
        provides=("value.in",),
        input_semantics={"value.out": ("output value",)},
        output_semantics={"value.in": ("input value",)},
        output_schema={"value.in": {"type": "number"}},
        examples=({"inputs": {"value.out": 7}, "params": {}, "outputs": {"value.in": 7}},),
    )

    def run_pure(self, inputs, params):
        return {"value.in": inputs["value.out"]}


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
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        time.sleep(0)
        return {"value.out": 1}


class NanOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.nan_output",
        display_name="NaN Output",
        category="test",
        description="Returns a runtime-invalid JSON value.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "number"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": float("nan")}


class EffectRequestNode:
    NODE_INFO = NodeInfo(
        type_key="test.effect_request",
        display_name="Effect Request",
        category="test",
        description="Emits a structured effect request.",
        version="0.1.0",
        flow_kind="data_store",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("effects.request",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"effects.request": ("structured effect request",)},
        output_schema={"effects.request": {"type": "object"}},
    )

    def run_pure(self, inputs, params):
        return {"effects.request": {"value": inputs["value.in"]}}


def _registry() -> NodeRegistry:
    registry = NodeRegistry()
    register_node(registry, "test.start", StartNode)
    register_node(registry, "test.value_input", ValueInputNode)
    register_node(registry, "test.out_end", OutEndNode)
    register_node(registry, "test.in_end", InEndNode)
    register_node(registry, "test.seed", SeedNode, {"value": {"type": "number"}}, {"value": 1})
    register_node(registry, "test.add", AddNode, {"delta": {"type": "number"}}, {"delta": 1})
    register_node(registry, "test.copy", CopyNode)
    register_node(registry, "test.nan_output", NanOutputNode)
    register_node(registry, "test.effect_request", EffectRequestNode)
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
        "name": name,
        "display_name": name.replace(".", " ").title(),
        "category": "test",
        "description": f"Composite flow for {name}.",
        "version": "0.1.0",
        "purity": "pure",
        "requires": requires or [],
        "provides": provides or ["value.out"],
        "exports": exports or ["value.out"],
        "pipeline": pipeline,
    }


def _edge_chain(*names: str) -> list[dict[str, str]]:
    return [{"from": source, "to": target} for source, target in zip(names, names[1:])]


def _seed_add_pipeline(*, seed: dict | None = None, add: dict | None = None) -> dict:
    seed_node = {"name": "seed", "type": "test.seed", "provides": ["value.in"], **(seed or {})}
    add_node = {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], **(add or {})}
    return {
        "nodes": [
            {"name": "start", "type": "test.start"},
            seed_node,
            add_node,
            {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
        ],
        "edges": _edge_chain("start", "seed", "add", "end"),
    }


def _seed_only_pipeline(*, seed: dict | None = None) -> dict:
    seed_node = {"name": "seed", "type": "test.seed", "provides": ["value.in"], **(seed or {})}
    return {
        "nodes": [
            {"name": "start", "type": "test.start"},
            seed_node,
            {"name": "end", "type": "test.in_end", "requires": ["value.in"]},
        ],
        "edges": _edge_chain("start", "seed", "end"),
    }


def _input_add_pipeline(*, add: dict | None = None) -> dict:
    add_node = {"name": "add", "type": "test.add", "requires": ["value.in"], "provides": ["value.out"], **(add or {})}
    add_name = str(add_node["name"])
    return {
        "inputs": ["value.in"],
        "nodes": [
            {"name": "start", "type": "test.start"},
            {"name": "input", "type": "test.value_input", "requires": ["value.in"]},
            add_node,
            {"name": "end", "type": "test.out_end", "requires": ["value.out"]},
        ],
        "edges": _edge_chain("start", "input", add_name, "end"),
    }


class DemoBoundary:
    calls: list[str] = []

    def __init__(self):
        self.run_dir = None

    def before_run(self, run_config):
        self.__class__.calls.append("before_run")
        self.run_dir = Path(run_config["run_dir"])
        return {}

    def after_run(self, outputs, run_config):
        self.__class__.calls.append("after_run")
        return {}

    def before_iteration(self, iteration, state):
        self.__class__.calls.append(f"before_iteration:{iteration}")
        return {}

    def after_iteration(self, iteration, outputs, state):
        self.__class__.calls.append(f"after_iteration:{iteration}")
        value = outputs.get("effects.request", {}).get("value", 0)
        run_dir = self.run_dir
        return {"io.result": value + iteration + 1, "artifacts": [str(run_dir / f"artifact_{iteration}.txt")]}


class FailingBoundary(DemoBoundary):
    def after_iteration(self, iteration, outputs, state):
        raise RuntimeError("boundary failed")


VALID_NODE_IMPORT = "from topology_kernel import NodeContract, NodeInfo\n\n"


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
        provides=("demo.out",),
        output_semantics={"demo.out": ("demo output",)},
        output_schema={"demo.out": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"demo.out": 1}},),
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


class SetOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.set_output",
        display_name="Set Output",
        category="test",
        description="Returns a non-json output.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class OpaqueOutputNode:
    NODE_INFO = NodeInfo(
        type_key="test.opaque_output",
        display_name="Opaque Output",
        category="test",
        description="Returns an explicitly opaque output.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        provides=("value.out",),
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"snapshot": "opaque"}},
    )

    def run_pure(self, inputs, params):
        return {"value.out": {1, 2}}


class MutatingInputNode:
    NODE_INFO = NodeInfo(
        type_key="test.mutating_input",
        display_name="Mutating Input",
        category="test",
        description="Mutates its input.",
        version="0.1.0",
        flow_kind="process",
    )
    CONTRACT = NodeContract(
        requires=("value.in",),
        provides=("value.out",),
        input_semantics={"value.in": ("input value",)},
        output_semantics={"value.out": ("output value",)},
        output_schema={"value.out": {"type": "array"}},
    )

    def run_pure(self, inputs, params):
        inputs["value.in"].append(3)
        return {"value.out": inputs["value.in"]}


class DuplicateOneNode:
    NODE_INFO = NodeInfo("test.duplicate_one", "Duplicate One", "test", "Duplicates output.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("dup.one",),
        output_semantics={"dup.one": ("duplicate value",)},
        output_schema={"dup.one": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.one": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.one": 1}


class DuplicateTwoNode:
    NODE_INFO = NodeInfo("test.duplicate_two", "Duplicate Two", "test", "Duplicates output.", "0.1.0", "process")
    CONTRACT = NodeContract(
        provides=("dup.two",),
        output_semantics={"dup.two": ("duplicate value",)},
        output_schema={"dup.two": {"type": "number"}},
        examples=({"inputs": {}, "params": {}, "outputs": {"dup.two": 1}},),
    )

    def run_pure(self, inputs, params):
        return {"dup.two": 1}


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
    CONTRACT = NodeContract(provides=("other.out",), output_semantics={{"other.out": ("other output",)}}, output_schema={{"other.out": {{"type": "number"}}}}, examples=({{"inputs": {{}}, "params": {{}}, "outputs": {{"other.out": 1}}}},))

    def run_pure(self, inputs, params):
        return {{"other.out": 1}}


class DemoNode:
{VALID_NODE_INFO}
{VALID_NODE_CONTRACT}

    def run_pure(self, inputs, params):
        OtherNode().run_pure({{}}, {{}})
        return {{"demo.out": 1}}
"""
    return _valid_node_source(run_body=str(case["run_body"]))


__all__ = [name for name in globals() if not name.startswith("__")]
