"""Product boundaries exercised through real native Rule handlers."""
from textwrap import indent
import pytest
from vibeflow.core.contracts import DataProvider, DataRequirement
from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
from vibeflow.core.rules import RuleContext
from vibeflow.targets.python.rules.node.effects import no_side_effects
from vibeflow.targets.python.rules.node.node_interface import node_interface
from vibeflow.targets.python.quality.source_context import PythonSourceFile, PythonSourceNode, build_python_source_context


def context(body, *, contract=None, flow_kind="process"):
    source=PythonSourceFile.parse("/virtual/task.py", "task", "class Task:\n    def run_pure(self, inputs, params):\n"+indent(body,"        ")+"\n")
    descriptor=NodeDescriptor(type_key="example.task", display_name="Task", description="Product boundary example.", version="1", flow_kind=flow_kind, contract=contract or NodeContractDescriptor())
    node=PythonSourceNode(descriptor, source.path,"Task")
    sources=build_python_source_context((node,), (source,))
    return RuleContext(subject={"kind":"node","type_key":"example.task"},target="python",facts={"source_context":sources,"node_catalog":(descriptor,),"source_owners":({"kind":"node","id":"example.task","role":"entry","path":source.path,"symbol":"Task"},)})


@pytest.mark.parametrize("body", (
    "count = 0\nwhile count < 3:\n    count += 1\nreturn {}",
    "self.client = 1\nself.value = 1\nreturn {}",
    "class Box: pass\nbox = Box()\nbox.count = 1\nsetattr(box, 'value', 2)\ndelattr(box, 'value')\nreturn {}",
))
def test_normal_algorithm_and_local_objects_are_allowed(body):
    assert not no_side_effects(context(body),{}, {"effect_scope":"none"}).findings


@pytest.mark.parametrize("variant", ("overlap", "route", "examples"))
def test_interface_names_and_documented_outputs_are_allowed(variant):
    kwargs={}
    if variant == "overlap":
        kwargs={"requires":(DataRequirement("value","exactly_one",display_name="Value"),),"provides":(DataProvider("value","value",display_name="Value"),),"input_semantics":{"value":("Value input",)},"output_semantics":{"value":("Value output",)}}
    elif variant == "route":
        kwargs={"provides":(DataProvider("status.ok","flag",display_name="Status"),),"output_semantics":{"status.ok":("Routing value",)}}
    else:
        kwargs={"examples":({"inputs":{},"params":{},"outputs":{}},)}
    result=node_interface(context("return {}",contract=NodeContractDescriptor(**kwargs),flow_kind="decision" if variant=="route" else "process"),{}, {})
    assert not result.findings


def test_selected_effect_policy_still_rejects_explicit_file_io():
    assert no_side_effects(context("return open('data').read()"),{}, {"effect_scope":"none"}).findings


@pytest.mark.parametrize(("shared", "used", "rejected"), (
    ("plugin", False, False), ("plugin", True, True), (None, False, True), ("node", False, True),
))
def test_node_import_ownership_distinguishes_shared_declarations(shared, used, rejected):
    from vibeflow.targets.python.rules.node.node_architecture import node_architecture
    body = "return Foreign().run_pure(inputs, params)" if used else "return {}"
    source = PythonSourceFile.parse("/virtual/task.py", "task",
        "from foreign import Foreign\nclass Task:\n    def run_pure(self, inputs, params):\n        " + body + "\n")
    other = PythonSourceFile.parse("/virtual/foreign.py", "foreign",
        "class Foreign:\n    def run_pure(self, inputs, params): return {}\n")
    task = NodeDescriptor(type_key="example.task", display_name="Task", description="Task", version="1", flow_kind="process", contract=NodeContractDescriptor())
    foreign = NodeDescriptor(type_key="example.foreign", display_name="Foreign", description="Foreign", version="1", flow_kind="process", contract=NodeContractDescriptor())
    nodes = (PythonSourceNode(task, source.path, "Task"), PythonSourceNode(foreign, other.path, "Foreign"))
    owners = [{"kind":"node", "id":item.type_key, "role":"entry", "path":item.path, "symbol":item.symbol} for item in nodes]
    if shared:
        owners.append({"kind":shared, "id":"example.other", "role":"entry", "path":source.path, "symbol":"other"})
    context_ = RuleContext(subject={"kind":"node", "type_key":task.type_key}, target="python",
        facts={"source_context":build_python_source_context(nodes, (source, other)), "node_catalog":(task, foreign), "source_owners":owners})
    result = node_architecture(context_, {}, {})
    assert bool(result.findings) is rejected
