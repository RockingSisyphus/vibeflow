from __future__ import annotations

import json
from pathlib import Path

from vibeflow import PluginInfo


def _record(value):
    marker = Path("reports/plugin_hooks.jsonl")
    marker.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


class CompilerPlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_compiler_hook",
        plugin_type="compiler",
        display_name="Sandbox Compiler Hook",
        category="compiler",
        description="Records compiler hook calls in the sandbox.",
        version="0.1.0",
    )
    name = "sandbox_compiler_hook"
    priority = 10

    def after_compile(self, graph, compiled):
        _record({"hook": "after_compile", "nodes": len(graph.nodes)})


class RuntimePlugin:
    PLUGIN_INFO = PluginInfo(
        name="sandbox_runtime_hook",
        plugin_type="runtime",
        display_name="Sandbox Runtime Hook",
        category="runtime",
        description="Records runtime hook calls in the sandbox.",
        version="0.1.0",
    )
    name = "sandbox_runtime_hook"
    priority = 10

    def before_node(self, name, node_type, input_summary):
        _record({"hook": "before_node", "name": name, "type": node_type})

    def after_node(self, name, node_type, output_summary):
        _record({"hook": "after_node", "name": name, "type": node_type})

    def before_nodeset(self, name, node_type):
        _record({"hook": "before_nodeset", "name": name, "type": node_type})

    def after_run(self, state, trace):
        _record({"hook": "after_run", "event_count": trace.get("event_count"), "trace_path": trace.get("trace_path")})
