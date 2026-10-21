"""A fixed SDK workflow with nested, repeated and Loop review neighbours."""

import json
from pathlib import Path


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def call(identifier, definition_id, **extra):
    return {"id": identifier, "definition_id": definition_id,
            "display_name": identifier, "description": "Layout fixture " + identifier, **extra}


def pipeline(nodes):
    return {"nodes": nodes, "edges": [[a["id"], b["id"]] for a, b in zip(nodes, nodes[1:])]}


def write_project(root: Path):
    root.mkdir(parents=True, exist_ok=False)
    for directory in ("nodes", "base_lib", "plugins"):
        (root / directory).mkdir()
        (root / directory / "__init__.py").write_text("")
    (root / "base_lib/helper.py").write_text('''from vibeflow.targets.python.sdk import base_lib
@base_lib(id="layout.helper", rulesets=["vibeflow.base_lib"],
          presentation={"fill":"#ffe6b3", "shape":"hex"})
def calculate(value):
    return value + 1
''')
    (root / "nodes/steps.py").write_text('''from vibeflow.targets.python.sdk import node
from ..base_lib.helper import calculate
@node(node_type='vibeflow.node', id="layout.start", flow_kind="terminal", contract={}, rulesets=["vibeflow.process"])
class Start:
    def run_pure(self, inputs, params):
        return {}
@node(node_type='vibeflow.node', id="layout.end", flow_kind="terminal", contract={}, rulesets=["vibeflow.process"])
class End:
    def run_pure(self, inputs, params):
        return {}
@node(node_type='vibeflow.node', id="layout.step", rulesets=["vibeflow.process"], base_libs=["layout.helper"],
      contract={"provides":[{"key":"result", "type":"number", "display_name":"Result"}],
                "output_semantics":{"result":["The calculated fixture value."]}},
      presentation={"fill":"#d6eaff", "stroke":"#425a78", "text":"#172b45", "shape":"rounded"})
class Step:
    def run_pure(self, inputs, params):
        return {"result": calculate(1)}
@node(node_type='vibeflow.node', id="layout.step_right", rulesets=["vibeflow.process"], base_libs=["layout.helper"],
      contract={"provides":[{"key":"right_result", "type":"number", "display_name":"Right result"}],
                "output_semantics":{"right_result":["A separately named calculated fixture value."]}},
      presentation={"fill":"#d6eaff", "stroke":"#425a78", "text":"#172b45", "shape":"rounded"})
class Right:
    def run_pure(self, inputs, params):
        return {"right_result": calculate(2)}
''')
    (root / "plugins/layout").mkdir()
    (root / "plugins/layout/lifecycle.py").write_text('''class Compiler:
    def after_compile(self, graph, compiled):
        return None
class Runtime:
    def before_run(self, state):
        return None
def create_compiler(context):
    return Compiler()
def create_runtime(context):
    return Runtime()
''')
    (root / "plugins/layout/plugin.py").write_text('''from vibeflow.targets.python.sdk import Plugin
from .lifecycle import create_compiler, create_runtime
plugin = Plugin(id="layout.resources", resources=[],
    compiler=create_compiler, runtime=create_runtime, rulesets=["vibeflow.plugin"],
    declaration_rulesets=["vibeflow.plugin_declaration"],
    display_name="Layout lifecycle", description="Real compiler and runtime declarations.",
    presentation={"fill":"#d9e6ff", "shape":"hex"})
''')
    for filename, type_key, display, nodes in (
        ("leaf_a.jsonc", "layout.leaf_a", "Leaf A", [call("a_start", "layout.start"),
         call("left", "layout.step"), call("right", "layout.step_right", style={"fill":"#bde8d0"}),
         call("a_end", "layout.end")]),
        ("leaf_b.jsonc", "layout.leaf_b", "Leaf B", [call("b_start", "layout.start"),
         call("middle", "layout.step"), call("b_end", "layout.end")]),
        ("outer.jsonc", "layout.outer", "Outer", [call("outer_start", "layout.start"),
         call("inner_a", "layout.leaf_a"), call("inner_b", "layout.leaf_a"),
         call("inner_c", "layout.leaf_b"), call("outer_end", "layout.end")]),
    ):
        nodes[-1]["similar_to"] = {"node":nodes[0]["id"], "relationship":"copy",
                                   "reason":"Both fixture boundaries return empty outputs."}
        write_json(root / filename, {"type_key":type_key, "display_name":display,
            "description":"A concrete layout fixture body.", "requires":[], "provides":[],
            "pipeline":pipeline(nodes)})
    nodes = [call("start", "layout.start"), call("outer_a", "layout.outer"),
             call("outer_b", "layout.outer", style={"fill":"#efe0f8"}),
             call("loop", "vibeflow.loop.while", requires=[], provides=[],
                  loop={"body":"layout.outer", "max_iterations":1, "stop_after":1}),
             call("end", "layout.end")]
    nodes[-1]["similar_to"] = {"node":"start", "relationship":"copy",
                               "reason":"Empty start and end boundary outputs."}
    write_json(root / "workflow.jsonc", {"plugins":[{"id":"layout.resources",
        "source":{"kind":"file", "ref":"plugins/layout/plugin.py"}}],
        "base_lib":{"modules":["layout.helper"]}, "rulesets":["vibeflow.workflow"],
        "nodeset_imports":[{"path":name} for name in ("leaf_a.jsonc", "leaf_b.jsonc", "outer.jsonc")],
        "pipeline":pipeline(nodes)})
    from tests.fixtures.support.projects import register_root
    register_root(root)
    write_json(root / "vibeflow_project.jsonc", {"project_target":"python", "architecture":{
        "documents":[{"workflow":"workflow.jsonc", "document":"ARCHITECTURE.jsonc"}]}})
