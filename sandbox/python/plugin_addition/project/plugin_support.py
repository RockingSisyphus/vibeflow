import json
from pathlib import Path

def record(hook, name=""):
    with Path("hooks.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"hook": hook, "name": name}) + "\n")

class Compiler:
    def after_compile(self, graph, compiled):
        record("after_compile")

class Runtime:
    def before_node(self, name, node_type, input_summary):
        record("before_node", name)
    def after_node(self, name, node_type, output_summary):
        record("after_node", name)
    def before_nodeset(self, name, node_type):
        record("before_nodeset", name)
    def after_run(self, state, trace):
        record("after_run")

def compiler(context):
    return Compiler()

def runtime(context):
    return Runtime()
