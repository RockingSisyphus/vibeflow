"""Independent Python projects for SDK identity and record regression cases."""

import json
from pathlib import Path


PREAMBLE = '''from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset, SourceLocator
from vibeflow.core.rules import RuleRecord, RuleResult

@node(node_type='vibeflow.node', id="case.start", flow_kind="terminal", contract={}, rulesets=[])
class Start:
    def run_pure(self, inputs, params):
        return {}

@node(node_type='vibeflow.node', id="case.end", flow_kind="terminal", contract={}, rulesets=[])
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
        node_source = (f'@node(node_type="vibeflow.node", id="case.step", contract={contract!r}, rulesets={list(selections)!r})\n'
                       'class Step:\n'
                       '    def run_pure(self, inputs, params):\n'
                       '        return {"value": 7}\n')
    from tests.fixtures.support.projects import register_root
    register_root(root)
    (root / "nodes").mkdir(exist_ok=True)
    package = root / "plugins/case"
    package.mkdir(parents=True,exist_ok=True)
    node_body, plugin_body = ("",body) if resources else (body,"")
    source = PREAMBLE + "\n" + node_body + "\n" + node_source
    (root / "nodes/steps.py").write_text(source)
    plugin_source = 'from vibeflow.targets.python.sdk import Plugin,rule,ruleset,SourceLocator\nfrom vibeflow.core.rules import RuleRecord,RuleResult\n' + plugin_body
    for marker in ("record.marker","config.marker"):
        plugin_source = plugin_source.replace('Path(__file__).with_name(' + repr(marker) + ')','Path(' + repr(str(root/marker)) + ')')
        plugin_source = plugin_source.replace('Path(__file__).with_name("' + marker + '")','Path(' + repr(str(root/marker)) + ')')
    plugin_source += (f'\nplugin=Plugin(id="case.resources",resources=[{", ".join(resources)}],'
        'declaration_rulesets=[],config_schema={"mode":{"type":"integer"}},config_defaults={"mode":0})\n')
    (package / "plugin.py").write_text(plugin_source)
    write_workflow(root, calls=calls, config=config)
    (root / "input.json").write_text("{}\n")
    return root


def write_workflow(root, *, calls=1, config=None, name="workflow.jsonc"):
    def call(identifier, type_key):
        return {"id": identifier, "definition_id": type_key, "display_name": identifier,
                "description": "Exercise a fixed SDK resource."}
    nodes = [call("start", "case.start"),
             *(call(f"step{index}", "case.step") for index in range(calls)),
             call("end", "case.end")]
    nodes[-1]["similar_to"] = {"node": "start", "relationship": "copy", "reason": "Empty boundary outputs."}
    value = {"plugins": [{"source": {"kind": "file", "ref": "plugins/case/plugin.py"}, "config": config or {}}],
             "rulesets": [], "pipeline": {"nodes": nodes,
                 "edges": [[left["id"], right["id"]] for left, right in zip(nodes, nodes[1:])],
                 "outputs": [{"type": "number", "as": "values", "cardinality": "all", "display_name": "Values"}]}}
    (root / name).write_text(json.dumps(value, indent=2) + "\n")


def implementation(path, symbol, *, kind="file", extra=None):
    return {"language": "python", "targets": ["python"],
            "source": {"kind": kind, "ref": str(path), "export": symbol}, **(extra or {})}
