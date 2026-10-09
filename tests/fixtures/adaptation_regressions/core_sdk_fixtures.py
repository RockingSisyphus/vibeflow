"""Independent Python projects for SDK identity and record regression cases."""

import json
from pathlib import Path


PREAMBLE = '''from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset, SourceLocator
from vibeflow.core.rules import RuleRecord, RuleResult

@node(type_key="case.start", flow_kind="terminal", contract={}, rulesets=[])
class Start:
    def run_pure(self, inputs, params):
        return {}

@node(type_key="case.end", flow_kind="terminal", contract={}, rulesets=[])
class End:
    def run_pure(self, inputs, params):
        return {}
'''


def write_project(root: Path, *, body="", resources=(), selections=(), calls=1,
                  node_source=None, config=None):
    root.mkdir(parents=True, exist_ok=True)
    for marker in ("record.marker", "config.marker"):
        (root / marker).unlink(missing_ok=True)
    contract = {"provides": [{"key": "value", "type": "number", "display_name": "Value"}],
                "output_semantics": {"value": ["The standalone sandbox result."]}}
    if node_source is None:
        node_source = (f'@node(type_key="case.step", contract={contract!r}, rulesets={list(selections)!r})\n'
                       'class Step:\n'
                       '    def run_pure(self, inputs, params):\n'
                       '        return {"value": 7}\n')
    source = PREAMBLE + "\n" + body + "\n" + node_source
    names = ", ".join(("Start", "End", "Step", *resources))
    source += (f'\nplugin = Plugin(id="case.resources", resources=[{names}],\n'
               '    declaration_rulesets=[], config_schema={"mode":{"type":"integer"}},\n'
               '    config_defaults={"mode":0})\n')
    (root / "plugin.py").write_text(source)
    write_workflow(root, calls=calls, config=config)
    (root / "input.json").write_text("{}\n")
    (root / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "case", "path": "."}]}) + "\n")
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}\n')
    return root


def write_workflow(root, *, calls=1, config=None, name="workflow.jsonc"):
    def call(identifier, type_key):
        return {"id": identifier, "type_used": type_key, "display_name": identifier,
                "description": "Exercise a fixed SDK resource."}
    nodes = [call("start", "case.start"),
             *(call(f"step{index}", "case.step") for index in range(calls)),
             call("end", "case.end")]
    nodes[-1]["similar_to"] = {"node": "start", "relationship": "copy", "reason": "Empty boundary outputs."}
    value = {"plugins": [{"source": {"kind": "file", "ref": "plugin.py"}, "config": config or {}}],
             "rulesets": [], "pipeline": {"nodes": nodes,
                 "edges": [[left["id"], right["id"]] for left, right in zip(nodes, nodes[1:])],
                 "outputs": [{"type": "number", "as": "values", "cardinality": "all", "display_name": "Values"}]}}
    (root / name).write_text(json.dumps(value, indent=2) + "\n")


def implementation(path, symbol, *, kind="file", extra=None):
    return {"language": "python", "targets": ["python"],
            "source": {"kind": kind, "ref": str(path), "export": symbol}, **(extra or {})}
