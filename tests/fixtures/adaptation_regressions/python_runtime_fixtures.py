"""Generated SDK projects for compiler, source scope and inspection regressions."""

from pathlib import Path

from tests.fixtures.adaptation_regressions.common import write_json


def call(identifier, type_key):
    return {"id": identifier, "type_used": type_key, "display_name": identifier,
            "description": "Exercise one explicitly selected SDK implementation."}


def project(root, source, *, rulesets=(), nodes=None, extra=None):
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.py").write_text(source, encoding="utf-8")
    write_json(root / "vibeflow_config.jsonc", {"roots": [{"id": "case", "path": "."}]})
    write_json(root / "vibeflow_project.jsonc", {"project_target": "python"})
    data = {"plugins": [{"source": {"kind": "file", "ref": "plugin.py"}}],
            "rulesets": list(rulesets),
            "pipeline": {"nodes": nodes or [call("leaf", "audit.leaf")], "edges": []},
            **(extra or {})}
    write_json(root / "workflow.jsonc", data)
    write_json(root / "input.json", {})
    return root


COMPILER = '''from pathlib import Path
from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset
from vibeflow.core.rules import RuleResult
from vibeflow.core.findings import HealthFinding

def record(value):
    with Path(__file__).with_name("hooks.jsonl").open("a") as stream:
        stream.write(value + "\\n")

@rule(id="audit.static", scope="source")
def static(context, inputs, params):
    record("node-static")
    return RuleResult()

@rule(id="audit.artifact", scope="call")
def artifact(context, inputs, params):
    kept = context.require("compiled").providers.get("audit.compiler") == "kept"
    record("workflow:" + str(kept))
    if not kept:
        return RuleResult(findings=(HealthFinding(rule_id="AUDIT.COMPILER.ARTIFACT_LOST",
            severity="error", message="The compiler stage artifact was replaced.",
            source_location={"path":__file__,"line":17}),))
    return RuleResult()

node_checks = ruleset(id="audit.node_checks", calls=[{"id":"static","rule_id":"audit.static"}],
    entrypoints={"static":["static"],"run":["static"]})
workflow_checks = ruleset(id="audit.workflow_checks", calls=[{"id":"artifact","rule_id":"audit.artifact"}],
    entrypoints={"static":["artifact"],"run":["artifact"]})

@node(type_key="audit.leaf", flow_kind="terminal", contract={}, rulesets=["audit.node_checks"])
class Leaf:
    def run_pure(self, inputs, params):
        raise RuntimeError("Business entry must not run during inspection.")

class Compiler:
    def __init__(self):
        self.disposed = False
        record("created")
    def before_compile(self, graph):
        record("before:" + str(self.disposed))
        if self.disposed:
            raise RuntimeError("compiler already disposed")
        if MODE == "before-failure":
            raise RuntimeError("AUDIT_BEFORE_FAILURE")
    def after_compile(self, graph, compiled):
        record("after:" + str(self.disposed))
        if MODE == "after-failure":
            raise RuntimeError("AUDIT_AFTER_FAILURE")
        compiled.providers["audit.compiler"] = "kept"
    def dispose(self):
        self.disposed = True
        record("dispose")

def compiler(context):
    return Compiler()
plugin = Plugin(id="audit", resources=[Leaf,static,artifact,node_checks,workflow_checks],
    compiler=compiler, rulesets=[], declaration_rulesets=[])
'''


def compiler_project(root, mode="success", *, runnable=False):
    source = f"MODE = {mode!r}\n" + COMPILER
    extra = None
    if runnable:
        contract = {"provides":[{"key":"value","type":"number","display_name":"Value"}],
                    "output_semantics":{"value":["The actual runtime number."]}}
        source = source.replace('flow_kind="terminal", contract={}', f'flow_kind="process", contract={contract!r}')
        source = source.replace('raise RuntimeError("Business entry must not run during inspection.")',
                                'record("business:7")\n        return {"value":7}')
        boundaries = ('@node(type_key="audit.start",flow_kind="terminal",contract={},rulesets=[])\n'
            'class Start:\n    def run_pure(self,inputs,params):\n        return {}\n'
            '@node(type_key="audit.end",flow_kind="terminal",contract={},rulesets=[])\n'
            'class End:\n    def run_pure(self,inputs,params):\n        return {}\n')
        source = source.replace('plugin = Plugin(',boundaries + '\nplugin = Plugin(')
        source = source.replace('resources=[Leaf,','resources=[Start,End,Leaf,')
        extra = {"pipeline":{"nodes":[call("start","audit.start"),call("leaf","audit.leaf"),call("end","audit.end")],
            "edges":[["start","leaf"],["leaf","end"]],
            "outputs":[{"type":"number","as":"result","cardinality":"exactly_one","display_name":"Result"}]}}
    return project(root, source, rulesets=["audit.workflow_checks"], extra=extra)


SCOPE = '''from pathlib import Path
from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset, SourceLocator
from vibeflow.core.rules import RuleResult
from vibeflow.core.findings import HealthFinding

@rule(id="audit.load_state", scope="source")
def load_state(context, inputs, params):
    source = context.require("source_context")
    node = next(item for item in source.nodes if item.type_key == context.subject["type_key"])
    present = node.path in context.facts["source_load_states"]
    with Path(__file__).with_name("rule.jsonl").open("a") as stream:
        stream.write(str(present) + "\\n")
    if REFUSE or not present:
        return RuleResult(findings=(HealthFinding(rule_id="AUDIT.IMPORT.REFUSED" if REFUSE else "AUDIT.LOAD_STATE.MISSING",
            severity="error", message="Import rejected." if REFUSE else "Actual source absent from current load states.",
            source_location={"path":node.path,"line":1}, object_type="node", object_id=node.type_key),))
    return RuleResult()

checks = ruleset(id="audit.import", calls=[{"id":"check","rule_id":"audit.load_state"}],
    entrypoints={"import":["check"]})
a = node(type_key="audit.a", flow_kind="terminal", contract={}, rulesets=["audit.import"],
    source=SourceLocator("file","a.py","A"))
b = node(type_key="audit.b", flow_kind="terminal", contract={}, rulesets=[],
    source=SourceLocator("file","b.py","B"))
plugin = Plugin(id="audit", resources=[a,b,load_state,checks], declaration_rulesets=[])
'''


def scope_project(root, *, unused=True, refuse=False):
    project(root, f"REFUSE = {refuse!r}\n" + SCOPE, nodes=[call("a", "audit.a")])
    (root / "a.py").write_text('from pathlib import Path\n'
        'Path(__file__).with_name("a.imported").write_text("loaded")\n'
        'class A:\n    def run_pure(self, inputs, params):\n'
        '        Path(__file__).with_name("a.ran").write_text("ran")\n        return {}\n')
    (root / "b.py").write_text('from pathlib import Path\n'
        'Path(__file__).with_name("b.imported").write_text("loaded")\n'
        'class B:\n    def run_pure(self, inputs, params):\n        return {}\n')
    if unused:
        write_json(root / "unused.jsonc", {"type_key":"audit.unused", "display_name":"Unused",
            "description":"An imported definition without a runtime call.", "requires":[], "provides":[],
            "rulesets":[], "pipeline":{"nodes":[call("b", "audit.b")]}})
        import json
        data = json.loads((root / "workflow.jsonc").read_text())
        data["nodeset_imports"] = [{"path":"unused.jsonc"}]
        write_json(root / "workflow.jsonc", data)
    return root


def policy_project(root, *, inline=None, discovered=None, explicit=None, nested=False,
                   override=False, unrelated=False):
    contract = {"provides":[{"key":"result","type":"number","display_name":"Result"}],
                "output_semantics":{"result":["The sandbox number."]}}
    code = 'from vibeflow.targets.python.sdk import Plugin,node,SourceLocator,ruleset\n'
    selection = "['audit.size']" if override else "['vibeflow.process']"
    code += (f'leaf=node(type_key="audit.leaf",contract={contract!r},rulesets={selection},'
             'source=SourceLocator("file","leaf.py","Leaf"))\n')
    resources = ["leaf"]
    if override:
        code += ('size=ruleset(id="audit.size",calls=[{"id":"size","rule_id":"vibeflow.maintainability",'
                 '"params":{"policy":{"node_source":{"max_lines":40}}}}],entrypoints={"static":["size"]})\n')
        resources.append("size")
    if unrelated:
        code += (f'bad=node(type_key="audit.bad",contract={contract!r},rulesets=["vibeflow.process"],'
                 'source=SourceLocator("file","bad.py","Bad"))\n')
        resources.append("bad")
    code += f'plugin=Plugin(id="audit",resources=[{",".join(resources)}],declaration_rulesets=[])\n'
    project(root, code)
    leaf = 'class Leaf:\n    def run_pure(self, inputs, params):\n        return {"result":7}\n'
    (root / "leaf.py").write_text(leaf + "\n" * (28 - len(leaf.splitlines())))
    (root / "bad.py").write_text('class Bad:\n    def run_pure(self, inputs, params):\n'
        '        print("unrelated forbidden output")\n        return {"result":7}\n')
    import json
    data = json.loads((root / "workflow.jsonc").read_text())
    if inline is not None:
        data["policy"] = {"node_source":{"max_lines":inline}}
    config = root / ("configs/workflow.jsonc" if nested else "workflow.jsonc")
    config.parent.mkdir(exist_ok=True)
    write_json(config, data)
    if discovered is not None:
        write_json(config.parent / "kernel_policy.jsonc", {"node_source":{"max_lines":discovered}})
    if explicit is not None:
        write_json(root / "explicit.jsonc", {"node_source":{"max_lines":explicit}})
    return root, config
