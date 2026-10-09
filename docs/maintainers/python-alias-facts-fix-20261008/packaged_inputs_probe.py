#!/usr/bin/env python3
"""Exercise canonical input contracts using only one generated product package.

Run with the installed wheel's Python interpreter, or pass --kernel to load a
distribution kernel ZIP. This script deliberately imports no source test code.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import traceback


def _input(key: str, required: bool) -> dict[str, object]:
    return {"key": key, "type": key, "display_name": key, "required": required}


def _document(inputs: list[dict[str, object]] | None) -> dict[str, object]:
    pipeline = {
        "nodes": [
            {"id": "start", "type_used": "probe.terminal", "display_name": "Start", "description": "Records the start invocation."},
            {"id": "record", "type_used": "probe.record", "display_name": "Record", "description": "Records the process invocation."},
            {"id": "end", "type_used": "probe.terminal", "display_name": "End", "description": "Records the end invocation."},
        ],
        "edges": [{"from": "start", "to": "record"}, {"from": "record", "to": "end"}],
        "outputs": [],
    }
    if inputs is not None:
        pipeline["inputs"] = inputs
    return {"pipeline": pipeline}


def _root_message(exc: BaseException) -> str:
    while exc.__cause__ is not None:
        exc = exc.__cause__
    return str(exc)


def _run(args: argparse.Namespace, report: dict[str, object]) -> None:
    if args.kernel:
        kernel = args.kernel.resolve(strict=True)
        sys.path.insert(0, str(kernel))
    else:
        kernel = None

    import vibeflow
    from vibeflow.block_compiler import SourceRef, compile_graph_plan
    from vibeflow.core.compiler import compile_core
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.models import CoreCompileRequest, ImplementationFact, ImplementationFacts, TargetFeatureSet
    from vibeflow.targets.javascript.frontend.bindings import build_javascript_binding_plan
    from vibeflow.targets.javascript.frontend.emitter import emit_workflow_module
    from vibeflow.targets.javascript.frontend.facts import native_workflow_facts
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.targets.python.runtime import PipelineRuntime, RuntimeOptions
    from vibeflow.tooling.project.graph_config import parse_graph_config

    origin = str(vibeflow.__file__)
    if kernel:
        assert origin.startswith(str(kernel) + "/vibeflow/"), origin
        report["product"] = {"kind": "kernel_zip", "path": str(kernel), "sha256": hashlib.sha256(kernel.read_bytes()).hexdigest(), "origin": origin}
    else:
        distribution = importlib.metadata.distribution("vibeflow")
        installed_origin = Path(distribution.locate_file("vibeflow/__init__.py")).resolve()
        assert installed_origin == Path(origin).resolve(), (installed_origin, origin)
        assert distribution.read_text("WHEEL"), "An installed wheel is required without --kernel."
        report["product"] = {"kind": "installed_wheel", "version": distribution.version, "origin": origin}

    counter = {"calls": 0}

    class RecordingNode:
        def run_pure(self, inputs, params):
            counter["calls"] += 1
            return {}

    registry = NodeRegistry()
    for type_key, flow_kind in (("probe.terminal", "terminal"), ("probe.record", "process")):
        registry.register(
            NodeDescriptor(type_key, "Invocation recorder", "Records each actual node implementation invocation.", "1", flow_kind, contract=NodeContractDescriptor(), rulesets=()),
            RecordingNode,
        )

    sources = {
        "probe.terminal": SourceRef(kind="javascript", ref="./nodes.mjs", export="terminal"),
        "probe.record": SourceRef(kind="javascript", ref="./nodes.mjs", export="record"),
    }
    facts = ImplementationFacts(tuple(
        ImplementationFact(
            type_key=type_key,
            flow_kind=registry.descriptor(type_key).flow_kind,
            requires=registry.descriptor(type_key).contract.requires,
            provides=registry.descriptor(type_key).contract.provides,
            completion="immediate",
            executor="current",
            async_executor="event_loop",
            source_kind=source.kind,
            source_ref=source.ref,
            source_export=source.export,
        )
        for type_key, source in sources.items()
    ), strict=True)
    features = TargetFeatureSet(target="javascript")
    failures = report["failures"]
    parse_observations = report["parse"]
    runtime_observations = report["runtime"]

    def check(condition, message):
        if not condition:
            failures.append(message)

    invalid_values = [("missing", ...), ("null", None), ("integer_zero", 0), ("integer_one", 1), ("string_true", "true"), ("string_false", "false"), ("list", []), ("object", {})]
    for name, value in invalid_values:
        spec = _input("request", True)
        if value is ...:
            del spec["required"]
        else:
            spec["required"] = value
        counter["calls"] = 0
        rejected = False
        message = ""
        try:
            parse_graph_config(_document([spec]))
        except ValueError as exc:
            rejected = True
            message = str(exc)
        parse_observations.append({"case": name, "rejected": rejected, "message": message, "node_calls": counter["calls"]})
        check(rejected and "required must be explicitly true or false" in message, f"parse/{name}: invalid required was not rejected for its input contract")
        check(counter["calls"] == 0, f"parse/{name}: a node executed")

    cases = [
        ("required_present", [_input("request", True)], {"request": 7}, True, ""),
        ("required_missing", [_input("request", True)], {}, False, "required workflow input 'request' is missing"),
        ("required_present_null", [_input("request", True)], {"request": None}, True, ""),
        ("unknown", [_input("request", True)], {"request": 7, "extra": 2}, False, "unknown workflow input 'extra'"),
        ("optional_missing", [_input("request", False)], {}, True, ""),
        ("optional_present_null", [_input("request", False)], {"request": None}, True, ""),
        ("optional_unknown", [_input("request", False)], {"extra": 2}, False, "unknown workflow input 'extra'"),
        ("mixed_required_missing", [_input("optional", False), _input("request", True)], {"optional": 7}, False, "required workflow input 'request' is missing"),
        ("empty_accepts_empty", [], {}, True, ""),
        ("empty_rejects_unknown", [], {"extra": 2}, False, "unknown workflow input 'extra'"),
        ("omitted_accepts_empty", None, {}, True, ""),
        ("omitted_rejects_unknown", None, {"extra": 2}, False, "unknown workflow input 'extra'"),
    ]
    for name, input_specs, inputs, accepted, expected_message in cases:
        case_dir = args.work.resolve() / name
        case_dir.mkdir(parents=True, exist_ok=True)
        try:
            graph = parse_graph_config(_document(input_specs))
            runtime = PipelineRuntime(graph, registry=registry, run_dir=case_dir / "python", runtime_options=RuntimeOptions(trace="full"))
            native_plan = runtime._plan.to_workflow_plan(workflow_id="probe." + name, source_by_type=sources)
            compilation = compile_core(CoreCompileRequest(graph=graph, implementation_facts=facts, target_features=features, known_nodesets=frozenset(graph.nodesets)))
            portable = compile_graph_plan(
                compilation.workflow.graph,
                compilation.compiled_graph,
                workflow_id="probe." + name,
                source_by_type=sources,
                implementation_facts=facts,
                native_execution_facts=native_workflow_facts(compilation.workflow.graph),
                target_features=features,
                compile_nested=True,
            )
            expected_contract = [(item.key, item.type, item.required) for item in graph.inputs]
            for label, plan in (("native_portable", native_plan), ("javascript_portable", portable)):
                check([(item.key, item.type, item.required) for item in plan.inputs] == expected_contract, f"{name}/{label}: lost input contract")
                (case_dir / (label + ".json")).write_text(json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            counter["calls"] = 0
            native_error = None
            try:
                runtime.run(inputs)
            except Exception as exc:
                native_error = {"type": type(exc).__name__, "public_message": str(exc), "message": _root_message(exc).removeprefix("Pipeline runtime error: ")}
            native = {"accepted": native_error is None, "node_calls": counter["calls"], "error": native_error, "trace_steps": runtime.trace.step_count}
            js_dir = case_dir / "javascript"
            js_dir.mkdir(exist_ok=True)
            nodes_path = js_dir / "nodes.mjs"
            nodes_path.write_text("export let calls = 0;\nexport function terminal() { calls += 1; return {}; }\nexport function record() { calls += 1; return {}; }\n", encoding="utf-8")
            emitted = emit_workflow_module(portable, javascript_bindings=build_javascript_binding_plan(portable, capabilities={}))
            workflow_path = js_dir / "workflow.mjs"
            workflow_path.write_text(emitted.source, encoding="utf-8")
            runner = js_dir / "run.mjs"
            runner.write_text(
                'import * as nodes from "./nodes.mjs";\n'
                'import * as workflow from "./workflow.mjs";\n'
                'let error = null;\n'
                'try { await workflow.runWorkflow(' + json.dumps(inputs, ensure_ascii=False) + '); }\n'
                'catch (cause) { error = {type: String(cause?.name || ""), code: String(cause?.code || ""), message: String(cause?.cause?.message || cause?.message || cause)}; }\n'
                'console.log(JSON.stringify({accepted: error === null, node_calls: nodes.calls, error}));\n',
                encoding="utf-8",
            )
            process = subprocess.run([args.node, str(runner)], cwd=js_dir, text=True, capture_output=True, timeout=30, check=True)
            javascript = json.loads(process.stdout)
            observation = {"case": name, "expected_accepted": accepted, "contract": input_specs, "inputs": inputs, "python": native, "javascript": javascript}
            runtime_observations.append(observation)
            expected_calls = 3 if accepted else 0
            for target, observed in (("python", native), ("javascript", javascript)):
                check(observed["accepted"] == accepted, f"{name}/{target}: wrong acceptance")
                check(observed["node_calls"] == expected_calls, f"{name}/{target}: expected {expected_calls} node calls, saw {observed['node_calls']}")
                if not accepted:
                    check(observed["error"] and observed["error"]["message"] == expected_message, f"{name}/{target}: wrong input rejection reason")
            if not accepted:
                check(native["trace_steps"] == 0, f"{name}/python: input failure advanced runtime steps")
        except Exception as exc:
            failures.append(f"{name}: {type(exc).__name__}: {exc}")
            runtime_observations.append({"case": name, "probe_error": traceback.format_exc()})

    product_modules = {name: str(getattr(module, "__file__", "")) for name, module in sys.modules.items() if name == "vibeflow" or name.startswith("vibeflow.")}
    if kernel:
        wrong_origins = {name: path for name, path in product_modules.items() if path and not path.startswith(str(kernel) + "/vibeflow/")}
    else:
        package_root = str(Path(origin).resolve().parent) + "/"
        wrong_origins = {name: path for name, path in product_modules.items() if path and not str(Path(path).resolve()).startswith(package_root)}
    check(not wrong_origins, f"mixed product module origins: {wrong_origins}")
    report["loaded_product_module_count"] = len(product_modules)
    report["foreign_product_modules"] = wrong_origins


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel", type=Path, help="Use this generated vibeflow_kernel.zip instead of an installed wheel.")
    parser.add_argument("--work", type=Path, required=True, help="Dedicated output directory for portable plans and emitted JavaScript.")
    parser.add_argument("--report", type=Path, required=True, help="JSON observation report.")
    parser.add_argument("--node", default="node", help="Node.js executable used for the actual emitted workflow.")
    args = parser.parse_args()
    report = {"probe": "canonical generated-package input contracts", "parse": [], "runtime": [], "failures": []}
    try:
        _run(args, report)
    except Exception:
        report["failures"].append(traceback.format_exc())
    report["passed"] = not report["failures"]
    args.report.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "parse_cases": len(report["parse"]), "runtime_cases": len(report["runtime"]), "report": str(args.report.resolve()), "failures": report["failures"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
