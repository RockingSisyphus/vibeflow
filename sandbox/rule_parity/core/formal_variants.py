"""Actual workflow validator dispatch, distinct from portable fact probes."""

from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
from pathlib import Path


def run_cases(work_root: Path, variant: str, toolchain_root: Path | None = None) -> list[dict]:
    spec = importlib.util.spec_from_file_location("core_formal_support", Path(__file__).with_name("support.py"))
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    from vibeflow.core.contracts import DataProvider, DataRequirement
    from vibeflow.core.flow import EdgeSpec, GraphConfig, IoSpec, LoopSpec, NodeMetadata, NodeSpec, NodesetSpec
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.targets.python.quality.workflow.validation import validate_graph_health

    def io(name, operation, signal):
        return NodeSpec(name, "vibeflow.io", io=IoSpec(operation), metadata=NodeMetadata(name, "Actual native IO boundary."),
            provides=(DataProvider(signal, signal, display_name="Received value"),) if operation == "receive" else (),
            requires=(DataRequirement(signal, "exactly_one", display_name="Sent value"),) if operation == "send" else ())

    def graph_for(kind, *, fanout=False, child_empty=False, root_empty=False, selected=None):
        body_nodes = (io("start", "receive", "child.signal"), io("left", "send", "child.signal"))
        body_edges = (EdgeSpec("start", "left"),)
        if fanout:
            body_nodes += (io("right", "send", "child.signal"),)
            body_edges += (EdgeSpec("start", "right"),)
        body = GraphConfig(body_nodes, body_edges)
        if variant == "current":
            body = replace(body, rulesets=() if child_empty else (selected,) if selected else body.rulesets)
        child = NodesetSpec("variant.body", "Body", "A loaded and invoked native graph.", (), (), body)
        count = 2 if kind == "repeat" else 1
        calls = tuple(NodeSpec("stage" + str(index), "vibeflow.loop.while" if kind == "loop" else child.type_key,
            loop=LoopSpec(body=child.type_key) if kind == "loop" else LoopSpec(), metadata=NodeMetadata("Stage", "Actual native body call.")) for index in range(count))
        nodes = (io("start", "receive", "root.signal"), *calls, io("end", "send", "root.signal"))
        edges = tuple(EdgeSpec(first.id, second.id, schedule=True) for first, second in zip(nodes, nodes[1:]))
        edges += (EdgeSpec("start", "end", schedule=False, transfer=True),)
        graph = GraphConfig(nodes, edges, nodesets={child.type_key: child})
        if variant == "current":
            graph = replace(graph, rulesets=() if root_empty else (selected,) if selected else graph.rulesets)
        return graph

    def validator(graph, phase="static", registry=None):
        report = validate_graph_health(graph, registry=registry or NodeRegistry(), **({"rule_phase": phase} if variant == "current" else {}))
        actual = support.observe(lambda: report)
        portable = report.to_dict()
        executions = portable["info"].get("rule_executions", ())
        actual["metrics"].update(rule_phases=[row["plan"]["entrypoint"] for row in executions],
            mainline_owners=sorted(portable["info"].get("mainline", {})),
            call_paths=[item.get("details", {}).get("call_path") for item in (*portable["errors"], *portable["warnings"]) if "call_path" in item.get("details", {})])
        return actual

    rows = []
    def emit(name, title, operation, expected, **kwargs):
        support.append(rows, "formal." + name, title, "workflow.formal_variants", operation, expected, **kwargs)

    for kind in ("repeat", "loop"):
        for fanout in (False, True):
            graph = graph_for(kind, fanout=fanout)
            emit(kind + ".default." + str(fanout), "实际重复Nodeset/Loop默认规则正负对照", lambda graph=graph: validator(graph),
                support.expectation(*(("GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT", "warning"),) if fanout else (),
                    **({"metrics": {"mainline_owners": ["nodeset:variant.body", "pipeline"]}} if fanout else {})),
                evidence="baseline workflow/{flow_data,mainline}.py declared recursion → current workflow/rule_phase.py actual invocations")
        graph = graph_for(kind, fanout=True, child_empty=True, root_empty=True)
        expected = support.expectation(("GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT", "warning")) if variant == "baseline" else support.expectation(metrics={"rule_phases": [], "mainline_owners": []})
        emit(kind + ".explicit_empty", "Root/body显式[]关闭审查并保留原生调用", lambda graph=graph: validator(graph), expected,
            classification="approved_change", notes="Baseline has no rule selection. Current explicitly opts out of Root and body review, without deleting native declarations.", evidence="GraphConfig.rulesets; validate_graph_health import/compile/selected phase")
        graph = graph_for(kind, child_empty=True)
        emit(kind + ".child_empty_identity", "默认父图仍须识别显式[]的实际body", lambda graph=graph: validator(graph), support.expectation(),
            classification="approved_change", notes="Known identity regression remains a failure; [] is a review opt-out, not declaration deletion.", evidence="targets/python/quality/rules/workflow.py:18,34-35")
    graph = graph_for("repeat", fanout=True)
    emit("repeat.run_default", "重复Nodeset在正式run审查阶段保留默认判断", lambda: validator(graph, "run"),
        support.expectation(("GRAPH.MAINLINE.UNDECLARED_SYNC_FANOUT", "warning")),
        notes="Baseline checked-run used the same public validator; current explicitly selects run. This case validates review dispatch, not business execution.", evidence="validate_graph_health(rule_phase='run'); builtin workflow static/run")

    if variant == "current":
        from vibeflow.core.descriptors.catalogs import DescriptorCatalogs
        from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleRecord, RuleResult, RulesetDescriptor
        catalogs = DescriptorCatalogs.empty()
        catalog_source = work_root / "phase_resources.jsonc"
        resources = {"rule": "variant.capture", "ruleset": "variant.phases", "entrypoints": {"import": ["capture"], "static": ["capture"], "run": ["capture"]}}
        catalog_source.parent.mkdir(parents=True, exist_ok=True)
        catalog_source.write_text(json.dumps(resources), encoding="utf-8")
        rule = RuleDescriptor("variant.capture", outputs={"snapshot": "variant.workflow_snapshot.v1"})
        selected = RulesetDescriptor("variant.phases", (RuleCall("capture", rule_id=rule.id),), entrypoints=resources["entrypoints"])
        catalogs.rules.register(rule, source=str(catalog_source))
        catalogs.rulesets.register(selected, source=str(catalog_source))
        def handler(context, inputs, params):
            return RuleResult(records={"snapshot": RuleRecord("variant.workflow_snapshot.v1", {
                "phase": context.phase, "owner": context.subject["id"], "call_path": context.subject["call_path"],
                "compiled_present": "compiled" in context.facts, "node_count": len(context.require("graph").nodes)})})
        registry = NodeRegistry()
        registry.rule_catalogs = (catalogs,)
        registry.rule_handler_loader = lambda plan: {rule.id: handler}
        for phase in ("import", "static", "run"):
            graph = graph_for("repeat", selected=selected.id)
            def capture(graph=graph, phase=phase):
                actual = validator(graph, phase, registry)
                executions = actual["metrics"]["info"]["rule_executions"]
                snapshots = [result["records"]["snapshot"]["value"] for execution in executions for result in execution["results"].values()]
                actual["metrics"].update(snapshots=snapshots,
                    compiled_presence=[item["compiled_present"] for item in snapshots],
                    captured_paths=[item["call_path"] for item in snapshots],
                    compilation_edges_present="explicit_edges" in actual["metrics"]["info"])
                return actual
            phases = ["import"] * 3 + ([phase] * 3 if phase != "import" else [])
            emit("phases.capture." + phase, "Root与每次实际body调用的真实phase资料 " + phase, capture,
                support.expectation(metrics={"rule_phases": phases, "compiled_presence": [False] * 3 + ([True] * 3 if phase != "import" else []),
                    "captured_paths": [[], ["stage0"], ["stage1"]] * (2 if phase != "import" else 1), "compilation_edges_present": phase != "import"}),
                classification="new_feature", notes="A real Rule callable records the supplied context; import must not fabricate compiled/binding facts.", evidence="NodeRegistry rule catalogs/handler loader; formal Target phase executor")
    return rows
