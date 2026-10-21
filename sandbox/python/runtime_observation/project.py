"""Public SDK project shared by runtime-observation cases and default-value tests."""

import json

PLUGIN = '''from vibeflow.targets.python.sdk import Plugin, node, data_schema

@node(node_type="vibeflow.node",id="probe.start", flow_kind="terminal", contract={{}}, rulesets=["vibeflow.io"])
class Start:
    def run_pure(self, inputs, params):
        return {{}}

@node(node_type="vibeflow.node",id="probe.defaults", contract={{
    "params_schema": {{"cleanup_record_roots": {{"type": {schema_type!r}}}}},
    "params_defaults": {{"cleanup_record_roots": {value!r}}},
    "provides": [{{"key": "result", "type": "probe.inspection", "display_name": "Default inspection"}}],
    "output_semantics": {{"result": ["The actual parameter value and Python container type"]}},
}}, rulesets=["vibeflow.process"])
class Defaults:
    def run_pure(self, inputs, params):
        value = params["cleanup_record_roots"]
        return {{"result": {{"value": value, "native_type": type(value).__name__}}}}

@node(node_type="vibeflow.node",id="probe.end", flow_kind="terminal", contract={{}}, rulesets=["vibeflow.io"])
class End:
    def run_pure(self, inputs, params):
        return {{}}

'''


def write_project(root, schema_type, value):
    root.mkdir(parents=True, exist_ok=True)
    (root / "nodes").mkdir(exist_ok=True)
    (root / "nodes/steps.py").write_text(PLUGIN.format(schema_type=schema_type, value=value), encoding="utf-8")
    (root / "plugins/schemas").mkdir(parents=True, exist_ok=True)
    (root / "plugins/schemas/plugin.py").write_text('from vibeflow.targets.python.sdk import Plugin,data_schema\ninspection=data_schema(type_key="probe.inspection",schema={"type":"object"})\nplugin=Plugin(id="probe.defaults",resources=[inspection])\n')
    (root.parent / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "probe", "path": root.name}]}))
    # Each probe owns its root; sibling probe directories are not a layout subject.
    (root.parent / "project_rules.jsonc").write_text('{"rulesets":[]}')
    (root / "root_rules.jsonc").write_text('{"rulesets":[]}')
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}')
    (root / "input.json").write_text("{}")
    workflow = {
        "plugins": [{"source": {"kind": "file", "ref": "plugins/schemas/plugin.py"}}],
        "rulesets": ["vibeflow.workflow"],
        "pipeline": {
            "nodes": [
                {"id": "start", "definition_id": "probe.start", "display_name": "Start", "description": "Begin inspection"},
                {"id": "inspect", "definition_id": "probe.defaults", "display_name": "Inspect defaults", "description": "Observe native parameters"},
                {"id": "end", "definition_id": "probe.end", "display_name": "End", "description": "Finish inspection",
                 "similar_to": {"node": "start", "relationship": "copy", "reason": "Both terminal nodes return no data"}},
            ],
            "edges": [["start", "inspect"], ["inspect", "end"]],
            "outputs": [{"type": "probe.inspection", "as": "inspection", "display_name": "Inspection", "cardinality": "exactly_one"}],
        },
    }
    (root / "workflow.jsonc").write_text(json.dumps(workflow, indent=2))
