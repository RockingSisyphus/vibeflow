from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SANDBOX_DIR = Path(__file__).resolve().parent
REPO_ROOT = SANDBOX_DIR.parents[1]
SRC_KERNEL = REPO_ROOT / "src" / "topology_kernel"
KERNEL_DIR = SANDBOX_DIR / "kernel"
KERNEL_LINK = KERNEL_DIR / "topology_kernel"
PROJECT_DIR = SANDBOX_DIR / "project"
CONFIG_DIR = PROJECT_DIR / "configs"
REPORT_DIR = SANDBOX_DIR / "reports"
ASCII_DIR = REPORT_DIR / "ascii"
MERMAID_DIR = REPORT_DIR / "mermaid"
RUN_ROOT = SANDBOX_DIR / "runs"
POLICY_PATH = PROJECT_DIR / "kernel_policy.jsonc"


VALID_RUN_CASES = [
    {"name": "linear", "config": "pass_linear.jsonc", "initial": {}, "expected_status": {"PASS", "CONCERNS"}, "expected_outputs": {"value.final": 14}},
    {"name": "free_nodes", "config": "pass_free_nodes.jsonc", "initial": {}, "expected_status": {"PASS", "CONCERNS"}},
    {"name": "decision_cycle_short", "config": "pass_decision_cycle_short.jsonc", "initial": {"value.in": 0}},
    {"name": "decision_cycle_long", "config": "pass_decision_cycle_long.jsonc", "initial": {"value.in": 0}},
    {"name": "nodeset_simple", "config": "pass_nodeset_simple.jsonc", "initial": {"value.in": 1}, "expected_outputs": {"value.out": 6}},
    {"name": "nodeset_nested", "config": "pass_nodeset_nested.jsonc", "initial": {"value.in": 1}, "expected_outputs": {"value.final": 11}},
    {"name": "io_data_store", "config": "pass_io_data_store.jsonc", "initial": {"io.result": 20}},
    {"name": "plugins", "config": "pass_plugins.jsonc", "initial": {"io.result": 20}},
    {"name": "comprehensive_flowchart", "config": "pass_comprehensive_flowchart.jsonc", "initial": {"value.in": 3}, "expected_outputs": {"io.output": "final=23;request=23"}},
]


INVALID_CASES = [
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingInfoNode", "type": "bad.missing_info", "expect": "NODE.CONTRACT.MISSING_NODE_INFO"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "InfoWrongTypeNode", "type": "bad.info_type", "expect": "MISSING_NODE_INFO"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "EmptyTypeKeyNode", "type": "bad.empty", "expect": "NODE_INFO_TYPE_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "NonPureNode", "type": "bad.non_pure", "expect": "NON_PURE_NODE"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingContractNode", "type": "bad.missing_contract", "expect": "NODE.CONTRACT.MISSING_CONTRACT"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "DuplicateKeysNode", "type": "bad.duplicate_keys", "expect": "CONTRACT_DUPLICATE_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/metadata_contract_cases.py", "class": "MissingSemanticsNode", "type": "bad.missing_semantics", "expect": "CONTRACT_SEMANTICS_MISSING"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "MissingRunPureNode", "type": "bad.missing_run_pure", "expect": "NODE.CONTRACT.MISSING_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ContextRunNode", "type": "bad.context_run", "expect": "NODE.CONTRACT.CONTEXT_RUN_FORBIDDEN"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "TooManyParamsNode", "type": "bad.too_many_params", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "VarArgsNode", "type": "bad.varargs", "expect": "NODE.CONTRACT.RUN_PURE_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "PublicHelperNode", "type": "bad.public_helper", "expect": "NODE.CONTRACT.PUBLIC_CALLABLE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "InitWithClientNode", "type": "bad.init_client", "expect": "NODE.CONTRACT.INIT_SIGNATURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "ResourceFieldNode", "type": "bad.resource_field", "expect": "NODE.PURITY.RESOURCE_FIELD"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "AsyncRunPureNode", "type": "bad.async_run_pure", "expect": "NODE.CONTRACT.ASYNC_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/signature_cases.py", "class": "GeneratorRunPureNode", "type": "bad.generator_run_pure", "expect": "NODE.PURITY.GENERATOR_RUN_PURE"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OpenFileNode", "type": "bad.open", "expect": "NODE.PURITY.BANNED_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "PathReadTextNode", "type": "bad.path_read", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "OsGetenvNode", "type": "bad.getenv", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SubprocessNode", "type": "bad.subprocess", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SocketNode", "type": "bad.socket", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "RequestsNode", "type": "bad.requests", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "SqliteNode", "type": "bad.sqlite", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "EvalNode", "type": "bad.eval", "expect": "NODE.PURITY.BANNED_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/side_effect_cases.py", "class": "DynamicImportNode", "type": "bad.dynamic_import", "expect": "NODE.PURITY.BANNED_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeImportNode", "type": "bad.node_import", "expect": "NODE_IMPORT"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "DirectNodeCallNode", "type": "bad.node_call", "expect": "NODE_DIRECT_CALL"},
    {"kind": "inspect_node", "module": "illegal_nodes/coupling_cases.py", "class": "NodeInternalReadNode", "type": "bad.node_internal", "expect": "NODE_INTERNAL_READ"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "DynamicOutputKeyNode", "type": "bad.dynamic_output", "expect": "NODE.PURITY.DYNAMIC_OUTPUT_KEY"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MissingOutputNode", "type": "bad.missing_output", "expect": "NODE.PURITY.MISSING_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "ExtraOutputNode", "type": "bad.extra_output", "expect": "NODE.PURITY.UNDECLARED_OUTPUT"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateInputsNode", "type": "bad.mutate_inputs", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "MutateNestedInputNode", "type": "bad.mutate_nested", "expect": "NODE.PURITY.INPUT_MUTATION"},
    {"kind": "inspect_node", "module": "illegal_nodes/contract_io_cases.py", "class": "UndeclaredParamNode", "type": "bad.undeclared_param", "expect": "UNDECLARED_PARAM"},
    {"kind": "runtime_node", "module": "illegal_nodes/contract_io_cases.py", "class": "SetOutputNode", "type": "bad.set_output", "expect": "not JSON snapshot serializable"},
    {"kind": "runtime_node", "module": "illegal_nodes/contract_io_cases.py", "class": "NaNOutputNode", "type": "bad.nan_output", "expect": "not JSON snapshot serializable"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "GlobalStateNode", "type": "bad.global_state", "expect": "MODULE_GLOBAL_STATE"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "SetAttrNode", "type": "bad.setattr", "expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "MonkeyPatchNode", "type": "bad.monkey_patch", "expect": "NODE.PURITY.MONKEY_PATCH"},
    {"kind": "inspect_node_small_source", "module": "illegal_nodes/maintainability_cases.py", "class": "LongSourceNode", "type": "bad.long_source", "expect": "NODE.PURITY.SOURCE_TOO_LARGE"},
    {"kind": "inspect_node_warn", "module": "illegal_nodes/maintainability_cases.py", "class": "WarnCallChainNode", "type": "bad.warn_call_chain", "expect": "CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "DeepCallChainNode", "type": "bad.deep_call_chain", "expect": "NODE.MAINTAINABILITY.CALL_CHAIN_TOO_DEEP"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "RecursiveNode", "type": "bad.recursive", "expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "inspect_node", "module": "illegal_nodes/maintainability_cases.py", "class": "IndirectRecursiveNode", "type": "bad.indirect_recursive", "expect": "NODE.MAINTAINABILITY.RECURSIVE_CALL_CHAIN"},
    {"kind": "health_node", "module": "illegal_nodes/maintainability_cases.py", "class": "DeepBaseLibNode", "type": "bad.deep_base_lib", "expect": "NODE.MAINTAINABILITY.DEPENDENCY_CHAIN_TOO_DEEP"},
    {"kind": "base_lib", "expect": "BASE_LIB.SIDE_EFFECT_CALL"},
    {"kind": "base_lib", "expect": "BASE_LIB.GLOBAL_STATE"},
    {"kind": "base_lib", "expect": "BASE_LIB.FORBIDDEN_PROJECT_IMPORT"},
    {"kind": "base_lib", "expect": "BASE_LIB.BANNED_IMPORT"},
    {"kind": "base_lib_chain", "expect_length_gt": 4},
    {"kind": "config", "config": "fail_schema_bad_edge.jsonc", "expect": "CONFIG.SCHEMA.EDGE_PAIR"},
    {"kind": "run", "config": "fail_unknown_node.jsonc", "expect": "NODE.TYPE.UNKNOWN"},
    {"kind": "config", "config": "fail_removed_loop_registration.jsonc", "expect": "CONFIG.LOOPS.REMOVED"},
    {"kind": "run", "config": "fail_nodeset_key_leak.jsonc", "expect": "NODESET.INTERNAL_KEY_LEAK"},
    {"kind": "run", "config": "fail_nodeset_recursion.jsonc", "expect": "NODESET.RECURSION"},
    {"kind": "config", "config": "fail_removed_boundary.jsonc", "expect": "CONFIG.BOUNDARY.REMOVED"},
    {"kind": "run", "config": "fail_planned_architecture_run.jsonc", "expect": "GRAPH.PLANNED.NODE_IN_RUN"},
    {"kind": "config", "config": "fail_plugin_load.jsonc", "expect": "PLUGIN.LOAD"},
    {"kind": "run", "config": "fail_plugin_unclosed_relaxation.jsonc", "expect": "PLUGIN.POLICY.RELAXATION_REQUIRED"},
    {"kind": "run", "config": "fail_plugin_execution.jsonc", "expect": "PLUGIN.EXECUTION"},
    {"kind": "config", "config": "fail_plugin_bad_shape.jsonc", "expect": "PLUGIN.POLICY.SHAPE"},
]


@dataclass
class CaseResult:
    name: str
    status: str
    detail: str = ""
    payload: dict[str, Any] | None = None


def main() -> int:
    try:
        _prepare_environment()
        _reset_outputs()
        results = [*_run_valid_cases(), *_run_invalid_cases()]
        _write_reports(results)
    except EnvironmentError as exc:
        print(f"ENVIRONMENT ERROR: {exc}")
        return 2
    failed = [result for result in results if result.status != "PASS"]
    print(f"integration sandbox: total={len(results)} passed={len(results) - len(failed)} failed={len(failed)}")
    for result in failed:
        print(f"FAIL {result.name}: {result.detail}")
    return 1 if failed else 0


def _prepare_environment() -> None:
    KERNEL_DIR.mkdir(parents=True, exist_ok=True)
    _ensure_kernel_link()
    for path in (KERNEL_DIR, PROJECT_DIR):
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
    os.chdir(SANDBOX_DIR)


def _ensure_kernel_link() -> None:
    target = SRC_KERNEL.resolve()
    if KERNEL_LINK.exists() or KERNEL_LINK.is_symlink():
        if KERNEL_LINK.resolve() == target:
            return
        raise EnvironmentError(f"kernel link exists but points elsewhere: {KERNEL_LINK}")
    try:
        os.symlink(target, KERNEL_LINK, target_is_directory=True)
        return
    except OSError as symlink_error:
        if os.name != "nt":
            raise EnvironmentError(f"cannot create kernel symlink: {symlink_error}") from symlink_error
    command = ["cmd", "/c", "mklink", "/J", str(KERNEL_LINK), str(target)]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise EnvironmentError(
            "cannot create kernel symlink or junction: "
            + (completed.stderr.strip() or completed.stdout.strip() or "unknown error")
        )


def _reset_outputs() -> None:
    for path in (REPORT_DIR, RUN_ROOT):
        if path.exists():
            shutil.rmtree(path)
    ASCII_DIR.mkdir(parents=True, exist_ok=True)
    MERMAID_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)


def _run_valid_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in VALID_RUN_CASES:
        try:
            result = _run_valid_case(case)
        except Exception as exc:
            result = CaseResult(f"valid:{case['name']}", "FAIL", str(exc))
        results.append(result)
    return results


def _run_valid_case(case: dict[str, Any]) -> CaseResult:
    from topology_kernel import GraphCompiler, export_ascii_flowchart, export_mermaid, load_config_document, parse_graph_config, resolve_effective_policy, run_checked, validate_graph_health
    from topology_kernel.config_schema import collect_config_schema_findings
    from topology_kernel.plugin import load_plugins_from_config

    from registry import build_node_registry

    name = str(case["name"])
    config_path = CONFIG_DIR / str(case["config"])
    document = load_config_document(config_path)
    schema_findings = collect_config_schema_findings(document.data)
    if schema_findings:
        raise AssertionError(f"schema findings: {[finding.rule_id for finding in schema_findings]}")
    plugin_registry, plugin_findings = load_plugins_from_config(document.data, base_path=config_path.parent)
    if plugin_findings:
        raise AssertionError(f"plugin findings: {[finding.rule_id for finding in plugin_findings]}")
    policy_result = resolve_effective_policy(document.data, config_path=config_path, explicit_policy_path=POLICY_PATH, plugin_registry=plugin_registry)
    graph = parse_graph_config(document.data)
    node_registry = build_node_registry()
    compiled = GraphCompiler().compile(graph, registry=node_registry, plugin_registry=plugin_registry)
    health = validate_graph_health(
        graph,
        registry=node_registry,
        plugin_registry=plugin_registry,
        purity_policy=policy_result.effective_policy.to_purity_policy(),
    )
    allowed = set(case.get("expected_status", {"PASS", "CONCERNS"}))
    if health.status not in allowed:
        raise AssertionError(f"health status {health.status}, expected {sorted(allowed)}")
    collapsed = export_mermaid(graph, compiled=compiled, registry=node_registry, health_report=health)
    expanded = export_mermaid(graph, compiled=compiled, registry=node_registry, expand_nodesets=True, health_report=health)
    ascii_collapsed = export_ascii_flowchart(graph, compiled=compiled, registry=node_registry, health_report=health)
    ascii_expanded = export_ascii_flowchart(graph, compiled=compiled, registry=node_registry, expand_nodesets=True, health_report=health)
    _assert_mermaid_contains(name, collapsed, expanded)
    _assert_ascii_contains(name, ascii_collapsed, ascii_expanded)
    (ASCII_DIR / f"{name}.txt").write_text(ascii_collapsed, encoding="utf-8")
    (ASCII_DIR / f"{name}.expanded.txt").write_text(ascii_expanded, encoding="utf-8")
    (MERMAID_DIR / f"{name}.mmd").write_text(collapsed, encoding="utf-8")
    (MERMAID_DIR / f"{name}.expanded.mmd").write_text(expanded, encoding="utf-8")
    run_result = run_checked(
        config_path,
        registry=node_registry,
        initial=case.get("initial", {}),
        policy_path=POLICY_PATH,
        run_root=RUN_ROOT,
        run_id=name,
    )
    _assert_artifacts(run_result.run_dir)
    for key, expected in dict(case.get("expected_outputs", {})).items():
        actual = run_result.context.get(str(key))
        if actual != expected:
            raise AssertionError(f"{key} expected {expected!r}, got {actual!r}")
    return CaseResult(f"valid:{name}", "PASS", payload={"health": health.status, "run_dir": str(run_result.run_dir)})


def _assert_mermaid_contains(name: str, collapsed: str, expanded: str) -> None:
    if "flowchart TD" not in collapsed:
        raise AssertionError("collapsed Mermaid missing flowchart TD")
    if "flowchart TD" not in expanded:
        raise AssertionError("expanded Mermaid missing flowchart TD")
    if "nodeset" in name and "subgraph" not in expanded:
        raise AssertionError("expanded nodeset Mermaid missing subgraph")


def _assert_ascii_contains(name: str, collapsed: str, expanded: str) -> None:
    if "TOPOLOGY FLOWCHART" not in collapsed:
        raise AssertionError("collapsed ASCII missing header")
    if "Flow edges:" not in collapsed:
        raise AssertionError("collapsed ASCII missing flow edges")
    if "nodeset" in name and "nodeset " not in expanded:
        raise AssertionError("expanded nodeset ASCII missing nodeset section")


def _assert_artifacts(run_dir: Path) -> None:
    required = (
        "health_report.json",
        "compiled_graph.json",
        "graph.txt",
        "graph.mmd",
        "runtime_trace.jsonl",
        "effective_policy.json",
        "input_summary.json",
        "output_summary.json",
    )
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        raise AssertionError(f"missing run artifacts: {missing}")


def _run_invalid_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    base_lib_report = None
    for index, case in enumerate(INVALID_CASES):
        name = f"invalid:{case['kind']}:{case.get('class', case.get('config', case.get('expect', index)))}"
        try:
            result, base_lib_report = _run_invalid_case(case, base_lib_report)
        except Exception as exc:
            result = CaseResult(name, "FAIL", str(exc))
        results.append(result)
    return results


def _run_invalid_case(case: dict[str, Any], base_lib_report):
    kind = case["kind"]
    if kind.startswith("inspect_node"):
        return _inspect_invalid_node(case, kind), base_lib_report
    if kind == "runtime_node":
        return _runtime_invalid_node(case), base_lib_report
    if kind == "health_node":
        return _health_invalid_node(case), base_lib_report
    if kind == "base_lib":
        report = base_lib_report or _bad_base_lib_report()
        _assert_report_has_rule(report.to_dict()["findings"], str(case["expect"]))
        return CaseResult(f"invalid:base_lib:{case['expect']}", "PASS"), report
    if kind == "base_lib_chain":
        report = base_lib_report or _bad_base_lib_report()
        from topology_kernel import summarize_base_lib_dependency_chain

        summary = summarize_base_lib_dependency_chain(("bad_base_lib.deep_chain_a",), report)
        if summary.longest_chain_length <= int(case["expect_length_gt"]):
            raise AssertionError(f"expected deep chain > {case['expect_length_gt']}, got {summary.longest_chain_length}")
        return CaseResult("invalid:base_lib_chain", "PASS", payload=summary.to_dict()), report
    if kind == "config":
        return _invalid_config(case), base_lib_report
    if kind == "run":
        return _invalid_run(case), base_lib_report
    raise AssertionError(f"unknown invalid case kind: {kind}")


def _inspect_invalid_node(case: dict[str, Any], kind: str) -> CaseResult:
    from topology_kernel.purity import validate_node_class
    from topology_kernel.purity_types import PurityPolicy

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    policy = PurityPolicy(max_source_lines=500, warn_source_lines=None, allowed_base_lib_modules=("base_lib",))
    if kind == "inspect_node_small_source":
        policy = PurityPolicy(max_source_lines=10, allowed_base_lib_modules=("base_lib",))
    elif kind == "inspect_node_warn":
        policy = PurityPolicy(max_source_lines=500, warn_call_chain_length=4, max_call_chain_length=99, allowed_base_lib_modules=("base_lib",))
    violations = validate_node_class(
        cls,
        policy=policy,
        expected_type=str(case["type"]),
        known_node_class_names=("ConstantNode",),
        known_node_modules=("nodes.legal_math_nodes",),
        scan_module=True,
    )
    _assert_violations_have_rule(violations, str(case["expect"]))
    return CaseResult(f"invalid:inspect_node:{case['class']}", "PASS", payload={"rules": [item.rule_id for item in violations]})


def _runtime_invalid_node(case: dict[str, Any]) -> CaseResult:
    from topology_kernel import EdgeSpec, GraphConfig, NodeContract, NodeInfo, NodeSpec, PipelineRuntime
    from topology_kernel.registry import NodeRegistry

    class RuntimeStartNode:
        NODE_INFO = NodeInfo("sandbox.runtime_start", "Runtime Start", "sandbox", "runtime test start", "0.1.0", "terminal")
        CONTRACT = NodeContract(examples=({"inputs": {}, "params": {}, "outputs": {}},))

        def run_pure(self, inputs, params):
            return {}

    class RuntimeEndNode:
        NODE_INFO = NodeInfo("sandbox.runtime_end", "Runtime End", "sandbox", "runtime test end", "0.1.0", "terminal")
        CONTRACT = NodeContract(requires=("bad.out",), input_semantics={"bad.out": ("bad output",)}, examples=({"inputs": {"bad.out": 1}, "params": {}, "outputs": {}},))

        def run_pure(self, inputs, params):
            return {}

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    registry = NodeRegistry()
    registry.register("sandbox.runtime_start", RuntimeStartNode, config_schema={}, config_defaults={})
    registry.register("sandbox.runtime_end", RuntimeEndNode, config_schema={}, config_defaults={})
    registry.register(str(case["type"]), cls, config_schema={}, config_defaults={})
    graph = GraphConfig(
        nodes=(
            NodeSpec(name="start", node_type="sandbox.runtime_start"),
            NodeSpec(name="bad", node_type=str(case["type"]), provides=("bad.out",)),
            NodeSpec(name="end", node_type="sandbox.runtime_end", requires=("bad.out",)),
        ),
        edges=(EdgeSpec("start", "bad"), EdgeSpec("bad", "end")),
    )
    try:
        PipelineRuntime(graph, registry=registry).run({})
    except Exception as exc:
        if str(case["expect"]) not in str(exc):
            raise AssertionError(f"runtime error did not include {case['expect']}: {exc}") from exc
        return CaseResult(f"invalid:runtime_node:{case['class']}", "PASS", str(exc))
    raise AssertionError("runtime node was not rejected")


def _health_invalid_node(case: dict[str, Any]) -> CaseResult:
    from topology_kernel import GraphConfig, NodeSpec, validate_graph_health
    from topology_kernel.purity_types import PurityPolicy
    from topology_kernel.registry import NodeRegistry

    cls = _load_class(PROJECT_DIR / str(case["module"]), str(case["class"]))
    registry = NodeRegistry()
    registry.register(str(case["type"]), cls, config_schema={}, config_defaults={})
    graph = GraphConfig(nodes=(NodeSpec(name="bad", node_type=str(case["type"]), provides=("bad.out",)),))
    report = validate_graph_health(
        graph,
        registry=registry,
        purity_policy=PurityPolicy(
            allowed_base_lib_paths=(str(PROJECT_DIR / "base_lib"),),
            allowed_base_lib_modules=("base_lib",),
            warn_dependency_chain_length=2,
            max_dependency_chain_length=4,
        ),
    )
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:health_node:{case['class']}", "PASS", payload=report.to_dict())


def _bad_base_lib_report():
    from topology_kernel import scan_base_lib
    from topology_kernel.purity_types import PurityPolicy

    return scan_base_lib(
        PROJECT_DIR,
        policy=PurityPolicy(
            allowed_base_lib_paths=(str(PROJECT_DIR / "bad_base_lib"),),
            max_source_lines=20,
            max_functions=3,
            max_branches=4,
            banned_import_roots=("subprocess",),
        ),
    )


def _invalid_config(case: dict[str, Any]) -> CaseResult:
    from topology_kernel.cli_config import validate_config_path

    report = validate_config_path(CONFIG_DIR / str(case["config"]), policy_path=POLICY_PATH)
    if report.status not in {"FAIL", "ERROR"}:
        raise AssertionError(f"config case was not rejected: {report.status}")
    _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
    return CaseResult(f"invalid:config:{case['config']}", "PASS", payload=report.to_dict())


def _invalid_run(case: dict[str, Any]) -> CaseResult:
    from registry import build_node_registry
    from topology_kernel import CheckedRunError, run_checked

    try:
        run_checked(
            CONFIG_DIR / str(case["config"]),
            registry=build_node_registry(),
            initial={"value.in": 0, "io.result": 1},
            policy_path=POLICY_PATH,
            run_root=RUN_ROOT,
            run_id=f"expected_fail_{Path(str(case['config'])).stem}",
        )
    except CheckedRunError as exc:
        report = exc.result.health
        if report.status not in {"FAIL", "ERROR"}:
            raise AssertionError(f"run case status was {report.status}")
        _assert_report_has_rule([item.to_dict() for item in (*report.errors, *report.warnings)], str(case["expect"]))
        return CaseResult(f"invalid:run:{case['config']}", "PASS", payload=report.to_dict())
    raise AssertionError("run case was not rejected")


def _load_class(path: Path, class_name: str):
    module_name = f"_sandbox_{path.stem}_{class_name}_{abs(hash(path))}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _assert_violations_have_rule(violations, expected: str) -> None:
    payloads = [
        {
            "rule_id": item.rule_id,
            "code": item.code,
            "message": item.message,
            "severity": item.severity,
            "failure_layer": item.failure_layer,
            "details": dict(item.details),
        }
        for item in violations
    ]
    _assert_report_has_rule(payloads, expected)


def _assert_report_has_rule(items: list[dict[str, Any]], expected: str) -> None:
    for item in items:
        rule_id = str(item.get("rule_id", ""))
        code = str(item.get("code", item.get("details", {}).get("legacy_code", "")))
        message = str(item.get("message", ""))
        if expected == rule_id or expected == code or expected in rule_id or expected in code or expected in message:
            return
    raise AssertionError(f"expected {expected}, got {[item.get('rule_id', item.get('code')) for item in items]}")


def _write_reports(results: list[CaseResult]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "total": len(results),
        "passed": sum(1 for item in results if item.status == "PASS"),
        "failed": sum(1 for item in results if item.status != "PASS"),
        "results": [
            {"name": item.name, "status": item.status, "detail": item.detail, "payload": item.payload or {}}
            for item in results
        ],
    }
    (REPORT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Integration Sandbox Summary",
        "",
        f"- total: {summary['total']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        "",
    ]
    for item in results:
        detail = f" - {item.detail}" if item.detail else ""
        lines.append(f"- {item.status}: {item.name}{detail}")
    (REPORT_DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
