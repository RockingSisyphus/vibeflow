"""Fixed SDK resources for standalone, reproducible review-cost observations."""

import json
from pathlib import Path
import shutil


def node_call(name, kind):
    return {"id": name, "type_used": kind, "display_name": name,
            "description": f"Execute the {name} resource."}


def write_project(root: Path, *, nodes=8, libraries=1, lines=100, repeats=1,
                  nested=False, loop=False, late=False, violation=False,
                  relative=False, cross_root=False):
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("nodes", "base_lib", "plugins"):
        (root / directory).mkdir()
        (root / directory / "__init__.py").write_text("")
    imports, resources = [], []
    for index in range(libraries):
        source = ("from vibeflow.targets.python.sdk import base_lib\n"
                  + ("from .shared import identity\n" if relative else "")
                  +
                  f"@base_lib(id='perf.library.{index}', rulesets=['vibeflow.base_lib'], "
                  + ("implementation_files=['shared.py'], " if relative else "")
                  + "presentation={'fill':'#d6eaff','shape':'hex'})\n"
                  f"def calculate{index}(value):\n"
                  + ("    print('forbidden library output')\n" if violation and index == 0 else "")
                  + f"    return {'identity(value)' if relative else 'value'} + {index + 1}\n")
        source += "# Explicitly registered source padding.\n" * max(0, lines-len(source.splitlines()))
        (root / "base_lib" / f"lib{index}.py").write_text(source)
        imports.append(f"from base_lib.lib{index} import calculate{index}")
        resources.append(f"calculate{index}")
    if relative:
        (root/'base_lib/shared.py').write_text('def identity(value):\n    return value\n')
    groups = []
    for group in range((nodes+7)//8):
        code = ["from vibeflow.targets.python.sdk import node",
                *[f"from base_lib.lib{i} import calculate{i}" for i in range(libraries)]]
        names = []
        for index in range(group*8, min(nodes, (group+1)*8)):
            names.append(f"Step{index}")
            contract = {"provides": [{"key": f"value{index}", "type": "number", "display_name": f"Value {index}"}],
                        "output_semantics": {f"value{index}": [f"The computed value of step {index}."]}}
            code.extend([f"@node(type_key='perf.step.{index}', contract={contract!r},",
                         "      rulesets=['vibeflow.process','perf.calls'], "
                         f"base_libs={[f'perf.library.{i}' for i in range(libraries)]!r},",
                         "      presentation={'fill':'#d6eaff','shape':'rounded'})",
                         f"class Step{index}:",
                         "    def run_pure(self, inputs, params):",
                         f"        value = {index}",
                         *[f"        value = calculate{i}(value)" for i in range(libraries)],
                         f"        if value != {index + sum(range(1, libraries+1))}:",
                         "            raise ValueError('Unexpected sandbox arithmetic')",
                         f"        return {{'value{index}': value}}", ""])
        (root / "nodes" / f"group{group}.py").write_text("\n".join(code)+"\n")
        groups.extend(names)
        imports.append(f"from nodes.group{group} import {', '.join(names)}")
    terminal = """from vibeflow.targets.python.sdk import node
@node(type_key='perf.start', flow_kind='terminal', contract={}, rulesets=['vibeflow.io'])
class Start:
    def run_pure(self, inputs, params):
        return {}
@node(type_key='perf.end', flow_kind='terminal', contract={}, rulesets=['vibeflow.io'])
class End:
    def run_pure(self, inputs, params):
        return {}
"""
    (root / "nodes" / "terminal.py").write_text(terminal)
    imports.append("from nodes.terminal import Start, End")
    resources.extend(["Start", "End", *groups])
    if late:
        (root / "late.py").write_text("from pathlib import Path\n"
            "Path(__file__).with_name('late.marker').write_text('imported')\n"
            "class Late:\n    def run_pure(self, inputs, params):\n        return {}\n")
        imports.append("from vibeflow.targets.python.sdk import node, SourceLocator")
        imports.append("late = node(type_key='perf.late', contract={}, rulesets=[], "
                       f"source=SourceLocator('file', {str(root / 'late.py')!r}, 'Late'))")
        resources.append("late")
    imports.extend(["from vibeflow.targets.python.sdk import rule, ruleset",
                    "@rule(id='perf.call', scope='call')",
                    "def count_call(context, inputs, params):",
                    "    return {'state':'completed','records':{},'findings':[]}",
                    "call_rules = ruleset(id='perf.calls', calls=[{'id':'check','rule_id':'perf.call'}], "
                    "entrypoints={'static':['check']})"])
    resources.extend(["count_call", "call_rules"])
    bundle = "\n".join(["from vibeflow.targets.python.sdk import Plugin", *imports,
                         f"plugin = Plugin(id='perf.resources', resources=[{', '.join(resources)}],",
                         "                declaration_rulesets=['vibeflow.plugin_declaration'])", ""])
    (root / "code_plugin.py").write_text(bundle)
    calls = [node_call(f"step{i}", f"perf.step.{i}") for i in range(nodes)]
    if late:
        calls.append(node_call("late", "perf.late"))
    workflow = {"plugins": [{"source": {"kind": "file", "ref": "code_plugin.py"}}],
                "rulesets": ["vibeflow.workflow"]}
    if nested:
        calls = [node_call('body_start', 'perf.start'), *calls, node_call('body_end', 'perf.end')]
        calls[-1]['similar_to'] = {'node':'body_start', 'relationship':'copy',
                                   'reason':'Empty boundary outputs.'}
        body = {"type_key": "perf.body", "display_name": "Shared body",
                "description": "A fixed reusable body.", "requires": [], "provides": [],
                "pipeline": {"nodes": calls, "edges": _edges(calls)}}
        (root / "body.jsonc").write_text(json.dumps(body, indent=2)+"\n")
        workflow["nodeset_imports"] = [{'path': 'body.jsonc'}]
        calls = [node_call(f"body{i}", "perf.body") for i in range(repeats)]
        if loop:
            calls = [{**node_call(f"loop{i}", "vibeflow.loop.while"),
                      'requires': [], 'provides': [],
                      'loop': {'body': 'perf.body', 'max_iterations': 1, 'stop_after': 1}}
                     for i in range(repeats)]
    calls = [node_call("start", "perf.start"), *calls, node_call("end", "perf.end")]
    calls[-1]["similar_to"] = {"node": "start", "relationship": "copy",
                               "reason": "Both boundary nodes return no data."}
    workflow["pipeline"] = {"nodes": calls, "edges": _edges(calls)}
    if not nested:
        workflow["pipeline"]["outputs"] = [{"type": "number", "as": "values",
                                             "cardinality": "all", "display_name": "Computed values"}]
    (root / "workflow.jsonc").write_text(json.dumps(workflow, indent=2)+"\n")
    (root / "input.json").write_text("{}\n")
    (root / "vibeflow_config.jsonc").write_text(json.dumps({"roots": [{"id": "perf", "path": "."}]}))
    (root / "vibeflow_project.jsonc").write_text('{"project_target":"python"}\n')
    if cross_root:
        support = root.parent/(root.name+'-support')
        support.mkdir()
        shutil.move(str(root/'base_lib'),str(support/'base_lib'))
        (support/'vibeflow_project.jsonc').write_text('{"project_target":"python"}\n')
        (root/'vibeflow_config.jsonc').write_text(json.dumps({'roots':[
            {'id':'perf','path':'.'}, {'id':'support','path':'../'+support.name}]}))
    return root / "workflow.jsonc"


def register_architecture(root):
    path = root / "vibeflow_project.jsonc"
    data = json.loads(path.read_text())
    data["architecture"] = {"documents": [{"workflow": "workflow.jsonc", "document": "ARCHITECTURE.jsonc"}]}
    path.write_text(json.dumps(data)+"\n")


def _edges(calls):
    return [[left["id"], right["id"]] for left, right in zip(calls, calls[1:])]
