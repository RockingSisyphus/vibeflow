from __future__ import annotations

import json
from pathlib import Path

from vibeflow.targets.python.sdk import Plugin, RuleCall, ruleset


def _record(value):
    marker = Path("reports/plugin_hooks.jsonl")
    marker.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


class CompilerPlugin:

    def after_compile(self, graph, compiled):
        _record({"hook": "after_compile", "nodes": len(graph.nodes)})


class RuntimePlugin:

    def before_node(self, name, node_type, input_summary):
        _record({"hook": "before_node", "name": name, "type": node_type})

    def after_node(self, name, node_type, output_summary):
        _record({"hook": "after_node", "name": name, "type": node_type})

    def before_nodeset(self, name, node_type):
        _record({"hook": "before_nodeset", "name": name, "type": node_type})

    def after_run(self, state, trace):
        _record({"hook": "after_run", "event_count": trace.get("event_count"), "trace_path": trace.get("trace_path")})


def create_compiler(context):
    return CompilerPlugin()


def create_runtime(context):
    return RuntimePlugin()


review = ruleset(
    id="sandbox.hook_plugin",
    calls=[
        RuleCall("imports", rule_id="vibeflow.import_side_effects"),
        RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope": "python_io"}),
        RuleCall("interface", rule_id="vibeflow.node_interface"),
    ],
    entrypoints={"import": ["imports"], "static": ["effects", "interface"], "run": ["effects", "interface"]},
)
plugin = Plugin(
    id="sandbox.hooks", resources=[review], compiler=create_compiler, runtime=create_runtime,
    rulesets=["sandbox.hook_plugin"], priority=10,
    display_name="Sandbox Hook Recorder", description="Records compiler and runtime hook calls.",
)
