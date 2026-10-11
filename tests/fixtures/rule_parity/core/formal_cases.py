"""Formal Target consumption controls for language-neutral graph findings.

Both kernels use their public Python workflow validator. The graph contains
only native IO and Nodeset declarations; no business implementation executes.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.flow import EdgeSpec, GraphConfig, IoSpec, NodeMetadata, NodeSpec, NodesetSpec
    from vibeflow.targets.python.project.registry import NodeRegistry
    if variant == "current":
        from vibeflow.tooling.application.python.project.declarations import default_python_registry as NodeRegistry
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health

    def plain(value):
        if hasattr(value, "items"):
            return {str(key): plain(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        return value

    def io(name, operation, *, missing_metadata=False, signal="child.signal"):
        metadata = NodeMetadata() if missing_metadata else NodeMetadata(name, "Declared native IO boundary.")
        return NodeSpec(name, "vibeflow.io", io=IoSpec(operation), metadata=metadata,
            provides=(DataProvider(signal, signal, display_name="Received value"),) if operation == "receive" else (),
            requires=(DataRequirement(signal, "exactly_one", display_name="Sent value"),) if operation == "send" else ())

    def healthy():
        return GraphConfig((io("start", "receive"), io("end", "send")), (EdgeSpec("start", "end"),), **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))

    observations = []
    cases = (
        ("normal", (), "Healthy declared child: used and unused controls."),
        ("metadata", (("GRAPH.SMELL.MISSING_NODE_DESCRIPTION", "warning"),
                      ("GRAPH.SMELL.MISSING_NODE_DISPLAY_NAME", "warning")), "Missing call metadata in the declared child."),
        ("mainline", (("GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT", "warning"),), "Ambiguous synchronous fanout in the declared child."),
        ("flow", (("GRAPH.FLOW.ORPHAN_NODE", "error"),
                  ("GRAPH.FLOW.CANNOT_REACH_END", "error"),
                  ("GRAPH.DATA.UNCONSUMED_PROVIDER", "warning")), "Disconnected receiving node has no end path or consumer."),
    )
    for topic, expected_codes, note in cases:
        for used in (False, True):
            case_id = "core.formal.nodeset." + topic + (".used" if used else ".unused")
            root = work_root / case_id
            root.mkdir(parents=True, exist_ok=True)
            if topic == "metadata":
                body = GraphConfig((io("start", "receive", missing_metadata=True), io("end", "send", missing_metadata=True)), (EdgeSpec("start", "end"),), **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
            elif topic == "mainline":
                body = GraphConfig((io("start", "receive"), io("left", "send"), io("right", "send")),
                    (EdgeSpec("start", "left"), EdgeSpec("start", "right")), **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
            elif topic == "flow":
                body = GraphConfig((io("start", "receive"), io("end", "send"), io("orphan", "receive", signal="orphan.signal")), (EdgeSpec("start", "end"),), **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
            else:
                body = healthy()
            required = (DataRequirement("root.signal", "exactly_one", display_name="Root value"),)
            provided = (DataProvider("child.signal", "child.signal", display_name="Child value"),)
            child = NodesetSpec("probe.child", "Child", "Declared source-free block with default workflow review.", required, provided, body)
            graph = healthy()
            if used:
                stage = NodeSpec("stage", child.type_key, metadata=NodeMetadata("Stage", "Calls the declared child."), requires=required, provides=provided)
                graph = GraphConfig((io("start", "receive", signal="root.signal"), stage, io("end", "send")), (EdgeSpec("start", "stage"), EdgeSpec("stage", "end")), **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
            graph = replace(graph, nodesets={child.type_key: child})
            try:
                report = validate_graph_health(graph, registry=NodeRegistry())
                findings = (*report.errors, *report.warnings)
                actual = {"status": report.status,
                    "codes": [{"code": code, "severity": severity} for code, severity in sorted({(item.rule_id, item.severity) for item in findings})],
                    "positions": [{"code": item.rule_id, **plain(item.source_location)} for item in findings if item.source_location],
                    "metrics": {"finding_details": [{"code": item.rule_id, "object_id": item.object_id, "details": plain(item.details)} for item in findings],
                        "mainline_owners": sorted(report.info.get("mainline", {}))},
                    "message": "; ".join(item.message for item in findings)}
            except Exception as error:
                actual = {"status": "ERROR", "codes": [{"code": str(getattr(error, "code", type(error).__name__)), "severity": "error"}],
                    "positions": [], "metrics": {}, "message": str(error)}
            observations.append({"id": case_id,
                "title": "正式报告保留已载入 Nodeset 声明的 " + topic + ("（实际调用）" if used else "（未调用）"),
                "family": "workflow.formal_consumption",
                "classification": "preserved",
                "expected": {"codes": [{"code": code, "severity": severity} for code, severity in expected_codes], "exact_codes": True,
                    **({"metrics": {"mainline_owners": ["nodeset:probe.child", "pipeline"]}} if topic == "mainline" else {})},
                "actual": actual,
                "notes": note + " An already loaded declaration remains within the existing command scope; this is not an isolated-source scan. Child default selection is unchanged.",
                "evidence": {"entrypoint": "vibeflow.targets.python.quality.workflow.validate_graph_health", "fixture": str(root),
                    "baseline": "workflow/validation.py:93-97; workflow/flow_data.py:57-100; workflow/mainline.py:26-34",
                    "current": "workflow/rule_phase.py:22-37,64-73; rules/workflow.py:46-58"}})
    observations.extend(_source_consumption_cases(work_root, variant))
    return observations


def _source_consumption_cases(work_root: Path, variant: str) -> list[dict]:
    """Real implementation text supplies fingerprints and compiler identity."""
    import importlib.util
    import sys
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.flow import EdgeSpec, ExecutionLockSpec, GraphConfig, IoSpec, NodeMetadata, NodeSimilarity, NodeSpec
    from vibeflow.targets.python.project.registry import NodeRegistry
    if variant == "current":
        from vibeflow.tooling.application.python.project.declarations import default_python_registry as NodeRegistry
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health

    cases = (
        ("duplicate", (("GRAPH.SMELL.DUPLICATE_LOGIC", "warning"),)),
        ("distinct", ()),
        ("similar", ()),
        ("advisory", (("GRAPH.EXECUTION_LOCK.GLOBAL_STATE_UNCOORDINATED", "warning"),)),
        ("advisory_locked", ()),
    )
    observations = []
    for mode, expected_codes in cases:
        case_id = "core.formal.root." + mode
        root = work_root / case_id
        root.mkdir(parents=True, exist_ok=True)
        registry, selected, files, calls = NodeRegistry(), [], [], []
        kinds = ("global_state",) if mode.startswith("advisory") else ("process", "process")
        for index, kind in enumerate(kinds):
            key, name = "probe.node" + str(index), "DemoNode" + str(index)
            path = root / ("node" + str(index) + ".py")
            source = "class " + name + ":\n"
            required_type = "root.signal" if index == 0 else "node" + str(index - 1) + ".signal"
            output_key = "node" + str(index) + ".signal"
            required = (DataRequirement(required_type, "exactly_one", display_name="Received value"),)
            provided = (DataProvider(output_key, output_key, display_name="Computed value"),)
            if variant == "baseline":
                source = "from vibeflow.targets.python.nodetypes.protocols import NodeInfo, NodeContract\nfrom vibeflow.core.contracts import DataProvider, DataRequirement\n" + source
                source += f"    NODE_INFO = NodeInfo({key!r}, 'Node', 'probe', 'Declared source fact.', '1.0', {kind!r})\n"
                source += (f"    CONTRACT = NodeContract(requires=(DataRequirement({required_type!r}, 'exactly_one', display_name='Received value'),), "
                    f"provides=(DataProvider({output_key!r}, {output_key!r}, display_name='Computed value'),), "
                    f"input_semantics={{{required_type!r}: ('Received value',)}}, output_semantics={{{output_key!r}: ('Computed value',)}}, "
                    f"examples=({{'inputs': {{{required_type!r}: 1}}, 'params': {{}}}},))\n")
            body = f"        result = {{{output_key!r}: 1}}\n        return result\n"
            if mode == "distinct" and index == 1:
                body = f"        if params:\n            return {{{output_key!r}: 1}}\n        return {{{output_key!r}: 2}}\n"
            source += "    def run_pure(self, inputs, params):\n" + body
            path.write_text(source, encoding="utf-8")
            if variant == "baseline":
                module_spec = importlib.util.spec_from_file_location("core_parity_" + mode + str(index), path)
                module = importlib.util.module_from_spec(module_spec)
                sys.modules[module_spec.name] = module
                module_spec.loader.exec_module(module)
                registry.register(key, getattr(module, name), config_schema={}, config_defaults={})
            else:
                from vibeflow.core.descriptors.models import ImplementationDescriptor, NodeContractDescriptor, NodeDescriptor, SourceLocator
                from vibeflow.targets.python.quality.source_context import PythonSourceCall, PythonSourceFile, PythonSourceNode, build_python_source_context
                descriptor = NodeDescriptor(key, "Node", "Declared source fact.", "1.0", kind,
                    NodeContractDescriptor(requires=required, provides=provided,
                        input_semantics={required_type: ("Received value",)}, output_semantics={output_key: ("Computed value",)},
                        examples=({"inputs": {required_type: 1}, "params": {}},)),
                    (ImplementationDescriptor("python", ("python",), SourceLocator("file", str(path), name)),),
                    rulesets=("vibeflow.global_state",) if kind == "global_state" else ("vibeflow.process",))
                registry.register(descriptor, source=str(path))
                node_id = "work" + str(index)
                selected.append(PythonSourceNode(descriptor, str(path), name, calls=(("pipeline", node_id),)))
                files.append(PythonSourceFile.parse(str(path), "core_parity_" + mode + str(index), source))
                calls.append(PythonSourceCall("pipeline", node_id, key, {}, str(path), node_id))
        def io(name, operation):
            signal = "root.signal" if operation == "receive" else "node" + str(len(kinds) - 1) + ".signal"
            return NodeSpec(name, "vibeflow.io", io=IoSpec(operation), metadata=NodeMetadata(name, "Declared native IO boundary."),
                provides=(DataProvider(signal, signal, display_name="Received value"),) if operation == "receive" else (),
                requires=(DataRequirement(signal, "exactly_one", display_name="Sent value"),) if operation == "send" else ())
        nodes = (io("start", "receive"), *(NodeSpec("work" + str(index), "probe.node" + str(index),
            metadata=NodeMetadata("Work", "Declared source call."),
            similar_to=NodeSimilarity("work0", "copy", "Intentional equivalent implementation.") if mode == "similar" and index else NodeSimilarity())
            for index in range(len(kinds))), io("end", "send"))
        graph = GraphConfig(nodes, tuple(EdgeSpec(first.id, second.id) for first, second in zip(nodes, nodes[1:])),
            execution_lock=ExecutionLockSpec("shared") if mode == "advisory_locked" else None, **({"rulesets": ("vibeflow.workflow",)} if variant == "current" else {}))
        try:
            kwargs = {"source_context": build_python_source_context(selected, files, calls=calls)} if variant == "current" else {}
            report = validate_graph_health(graph, registry=registry, **kwargs)
            portable = report.to_dict()
            findings = (*portable["errors"], *portable["warnings"])
            actual = {"status": report.status,
                "codes": [{"code": code, "severity": severity} for code, severity in sorted({(item.get("code", item["rule_id"]), item["severity"]) for item in findings})],
                "positions": [{"code": item.get("code", item["rule_id"]), **item["source_location"]} for item in findings if item["source_location"]],
                "metrics": {"node_metrics": portable["info"]["node_metrics"], "finding_details": [item["details"] for item in findings]},
                "message": "; ".join(item["message"] for item in findings)}
        except Exception as error:
            actual = {"status": "ERROR", "codes": [{"code": str(getattr(error, "code", type(error).__name__)), "severity": "error"}],
                "positions": [], "metrics": {}, "message": str(error)}
        observations.append({"id": case_id, "title": "正式报告消费真实源码/编译事实：" + mode,
            "family": "workflow.formal_consumption", "classification": "preserved",
            "expected": {"codes": [{"code": code, "severity": severity} for code, severity in expected_codes], "exact_codes": True},
            "actual": actual, "notes": "Baseline imports the real declared classes; current obtains their real parsed source snapshot and canonical declarations. The workflow validator is the consumer in both variants.",
            "evidence": {"entrypoint": "vibeflow.targets.python.quality.workflow.validate_graph_health", "source": [str(root / ("node" + str(index) + ".py")) for index in range(len(kinds))],
                "baseline": "workflow/validation.py:97,104,174-184,406-416,439-455",
                "current": "workflow/rule_phase.py:95-98; rules/workflow.py:22-23,60-64; rules/maintainability.py:83-91"}})
    return observations
