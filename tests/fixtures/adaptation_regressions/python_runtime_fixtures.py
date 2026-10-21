"""Generated SDK projects for compiler, source scope and inspection regressions."""

from pathlib import Path

from tests.fixtures.adaptation_regressions.common import write_json


def call(identifier, type_key):
    return {"id": identifier, "definition_id": type_key, "display_name": identifier,
            "description": "Exercise one explicitly selected SDK implementation."}


def project(root, source, *, node_source, rulesets=(), nodes=None, extra=None):
    root.mkdir(parents=True, exist_ok=True)
    from tests.fixtures.support.projects import register_root
    register_root(root)
    (root / "nodes").mkdir(exist_ok=True)
    (root / "nodes/declarations.py").write_text(node_source)
    (root / "plugins/audit").mkdir(parents=True,exist_ok=True)
    (root / "plugins/audit/plugin.py").write_text(source, encoding="utf-8")
    write_json(root / "vibeflow_project.jsonc", {"project_target": "python"})
    data = {"plugins": [{"source": {"kind": "file", "ref": "plugins/audit/plugin.py"}}],
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

@rule(id="audit.artifact", level="graph", scope="call")
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

@node(node_type="vibeflow.node", id="audit.leaf", flow_kind="terminal", contract={}, rulesets=["audit.node_checks"])
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
        boundaries = ('@node(node_type="vibeflow.node", id="audit.start",flow_kind="terminal",contract={},rulesets=[])\n'
            'class Start:\n    def run_pure(self,inputs,params):\n        return {}\n'
            '@node(node_type="vibeflow.node", id="audit.end",flow_kind="terminal",contract={},rulesets=[])\n'
            'class End:\n    def run_pure(self,inputs,params):\n        return {}\n')
        source = source.replace('plugin = Plugin(',boundaries + '\nplugin = Plugin(')
        source = source.replace('resources=[Leaf,','resources=[Start,End,Leaf,')
        extra = {"pipeline":{"nodes":[call("start","audit.start"),call("leaf","audit.leaf"),call("end","audit.end")],
            "edges":[["start","leaf"],["leaf","end"]],
            "outputs":[{"type":"number","as":"result","cardinality":"exactly_one","display_name":"Result"}]}}
    node_start=source.index('@node(')
    node_end=source.index('class Compiler:')
    node_source='from pathlib import Path\nfrom vibeflow.targets.python.sdk import node\n'
    node_source+='def record(value):\n    with Path('+repr(str(root/'hooks.jsonl'))+').open("a") as stream:\n        stream.write(value+"\\n")\n'
    node_source+=source[node_start:node_end]
    source=source[:node_start]+source[node_end:]
    if runnable:
        boundary_start=source.index('@node(')
        boundary_end=source.index('plugin = Plugin(',boundary_start)
        node_source+=source[boundary_start:boundary_end]
        source=source[:boundary_start]+source[boundary_end:]
    source=source.replace('resources=[Start,End,Leaf,','resources=[').replace('resources=[Leaf,','resources=[')
    source=source.replace('Path(__file__).with_name("hooks.jsonl")','Path('+repr(str(root/'hooks.jsonl'))+')')
    return project(root,source,node_source=node_source,rulesets=["audit.workflow_checks"],extra=extra)



SCOPE = '''from pathlib import Path
from vibeflow.targets.python.sdk import Plugin, node, rule, ruleset, SourceLocator
from vibeflow.core.rules import RuleResult
from vibeflow.core.findings import HealthFinding

@rule(id="audit.load_state", scope="source")
def load_state(context, inputs, params):
    source = context.require("source_context")
    node = next(item for item in source.nodes if item.definition_id == context.subject["definition_id"])
    present = source.file(node.path) is not None
    assert "source_load_states" not in context.facts
    with Path(__file__).with_name("rule.jsonl").open("a") as stream:
        stream.write(str(present) + "\\n")
    if REFUSE or not present:
        return RuleResult(findings=(HealthFinding(rule_id="AUDIT.IMPORT.REFUSED" if REFUSE else "AUDIT.LOAD_STATE.MISSING",
            severity="error", message="Import rejected." if REFUSE else "Actual source absent from current load states.",
            source_location={"path":node.path,"line":1}, object_type="node", object_id=node.definition_id),))
    return RuleResult()

checks = ruleset(id="audit.import", calls=[{"id":"check","rule_id":"audit.load_state"}],
    entrypoints={"import":["check"]})
a = node(node_type="vibeflow.node", id="audit.a", flow_kind="terminal", contract={}, rulesets=["audit.import"],
    source=SourceLocator("file","a.py","A"))
b = node(node_type="vibeflow.node", id="audit.b", flow_kind="terminal", contract={}, rulesets=[],
    source=SourceLocator("file","b.py","B"))
plugin = Plugin(id="audit", resources=[a,b,load_state,checks], declaration_rulesets=[])
'''


def scope_project(root, *, unused=True, refuse=False):
    start=SCOPE.index('a = node(')
    end=SCOPE.index('plugin = Plugin(')
    node_source='from vibeflow.targets.python.sdk import node,SourceLocator\n'+SCOPE[start:end]
    source=f"REFUSE = {refuse!r}\n"+SCOPE[:start]+SCOPE[end:]
    source=source.replace('resources=[a,b,load_state,checks]','resources=[load_state,checks]')
    project(root,source,node_source=node_source,nodes=[call("a","audit.a")])
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
