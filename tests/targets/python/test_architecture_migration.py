"""The official SDK/CLI chain is invariant to resource directory vocabulary."""
import json
from pathlib import Path

import pytest

from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
from vibeflow.tooling.project.workspace_loader import load_project_workspace


def _project(root, library_path, library_text, *, node_text=None, support=None,
             library_rules=("vibeflow.base_lib",), node_rules=("vibeflow.process",), dependency=True, other_node=None,
             policy=None, rule_call_policy=None):
    def write(relative, text):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    write(library_path, library_text)
    for name, text in (support or {}).items():
        write(name, text)
    extra_node = ""
    if other_node is not None:
        path, export, text = other_node
        write(path, text)
        extra_node = ('node(type_key="test.other",display_name="Other",description="Another declared Node",version="1",flow_kind="process",'
            f'source=SourceLocator(kind="file",ref={path!r},export={export!r}),contract=NodeContractDescriptor(),rulesets=()),\n')
    module = library_path.removesuffix(".py").replace("/", ".")
    write("leaf.py", node_text or f'class Leaf:\n    def run_pure(self, inputs, params):\n        from {module} import add\n        return {{"value.out": add(1, 2)}}\n')
    extra_ruleset = ('ruleset(id="test.policy",calls=(RuleCall("health",rule_id="vibeflow.maintainability",'
        f'params={{"policy":{rule_call_policy!r}}}),)),\n') if rule_call_policy is not None else ""
    write("plugin.py", 'from vibeflow.targets.python.sdk import Plugin, node, base_lib, ruleset, RuleCall, SourceLocator, NodeContractDescriptor, DataProvider\n'
        'plugin=Plugin(id="migration", resources=(\n'
        'node(type_key="test.leaf",display_name="Leaf",description="A declared leaf",version="1",flow_kind="process",'
        'source=SourceLocator(kind="file",ref="leaf.py",export="Leaf"),'
        'contract=NodeContractDescriptor(provides=(DataProvider("value.out","value.out",display_name="Value"),),'
        'output_semantics={"value.out":("Computed value",)}),'
        f'base_libs={(("test.math",) if dependency else ())!r},rulesets={node_rules!r}),\n'
        'base_lib(id="test.math",display_name="Math",description="Declared math library",'
        f'source=SourceLocator(kind="file",ref={library_path!r}),implementation_files={tuple((support or {}).keys())!r},'
        f'rulesets={library_rules!r}),\n' + extra_node + extra_ruleset + '))\n')
    write("vibeflow_project.jsonc", json.dumps({"project_target":"python","quality_enabled":False}))
    write("main.jsonc", json.dumps({**({"policy":policy} if policy is not None else {}),"plugins":[{"source":{"kind":"file","ref":"plugin.py"}}],
        "rulesets":[], "pipeline":{"nodes":[{"id":"leaf","type_used":"test.leaf",
        "display_name":"Leaf","description":"Exercise canonical ownership"}]}}))
    path = root / "main.jsonc"
    if policy is not None:
        from vibeflow.tooling.application.python.cli.config import validate_config_path
        return validate_config_path(path)
    return validate_workspace_config_path(path, workspace=load_project_workspace(path))


@pytest.mark.parametrize("directory", ["ordinary", "base_lib", "boundary", "nodes", "runtime"])
@pytest.mark.parametrize("import_position", ["module", "method"])
def test_declared_library_has_same_result_for_all_names_and_import_positions(tmp_path, directory, import_position):
    module = directory + ".math"
    node = (f'from {module} import add\nclass Leaf:\n    def run_pure(self,inputs,params): return {{"value.out":add(1,2)}}\n'
        if import_position == "module" else None)
    report = _project(tmp_path, directory + "/math.py", 'def add(left,right): return left+right\n', node_text=node)
    assert report.status == "PASS", report.to_dict()


@pytest.mark.parametrize("directory", ["parts", "runtime", "nodes", "plugins", "boundary"])
def test_declared_library_support_membership_is_independent_of_directory_name(tmp_path, directory):
    report = _project(tmp_path, "library.py", f'from {directory}.support import add\n',
        support={directory+"/support.py":'def add(left,right): return left+right\n'})
    assert report.status == "PASS", report.to_dict()


def test_actual_undeclared_library_is_rejected_without_old_policy_allowlist(tmp_path):
    report = _project(tmp_path, "ordinary/math.py", 'def add(left,right): return left+right\n', dependency=False)
    assert "VF_IMPORT_LAYER" in {item.code for item in report.errors}


def test_callers_selected_effect_rule_checks_transitive_helpers_even_with_unchecked_library(tmp_path):
    report = _project(tmp_path, "ordinary/math.py",
        'def add(left,right):\n    return save(left+right)\ndef save(value):\n    print(value)\n    return value\n',
        library_rules=())
    assert any(item.code == "NODE.EFFECT.CALL_FORBIDDEN" for item in report.errors), report.to_dict()


def test_empty_node_and_library_rulesets_leave_effects_unselected(tmp_path):
    report = _project(tmp_path, "ordinary/math.py", 'def add(left,right):\n    print(left)\n    return left+right\n',
        library_rules=(), node_rules=())
    assert report.status == "PASS", report.to_dict()


@pytest.mark.parametrize("override", [None, {"node_source":{"max_lines":100}}])
def test_application_config_policy_is_the_policy_recorded_and_used_by_the_selected_rule(tmp_path, override):
    report = _project(tmp_path, "math.py", 'def add(left,right): return left+right\n', library_rules=(),
        node_rules=("test.policy",) if override is not None else ("vibeflow.process",),
        policy={"node_source":{"max_lines":1},"complexity":{"max_functions":9},
                "imports":{"allowed_modules":["math","vibeflow"]}}, rule_call_policy=override)
    expected = 100 if override is not None else 1
    assert (report.status == "PASS") == (override is not None), report.to_dict()
    calls = [call for execution in report.info["rule_executions"] for call in execution["plan"]["calls"]
             if call["rule_id"] == "vibeflow.maintainability"]
    assert calls and calls[0]["params"]["policy"]["node_source"]["max_lines"] == expected
    assert calls[0]["params"]["policy"]["complexity"]["max_functions"] == 9
    assert "imports" not in calls[0]["params"]["policy"]
    assert ("NODE.PURITY.SOURCE_TOO_LARGE" in {item.code for item in report.errors}) == (override is None)
    from vibeflow.tooling.application.rule_review import effective_rule_plans
    preview = effective_rule_plans(tmp_path / "main.jsonc")
    plan = preview["nodes"][0]["plans"][0]
    preview_call = next(call for call in plan["calls"] if call["rule_id"] == "vibeflow.maintainability")
    assert preview_call["params"] == calls[0]["params"]


@pytest.mark.parametrize("expression", ["Helper().run_pure({}, {})", "instance.run_pure({}, {})"])
def test_ordinary_helper_run_pure_method_has_no_node_identity(tmp_path, expression):
    setup = "        instance = Helper()\n" if expression.startswith("instance") else ""
    report = _project(tmp_path, "ordinary.py",
        'class Helper:\n    def run_pure(self, inputs, params): return 3\n    def unused(self): print("unused")\n',
        node_text='from ordinary import Helper\nclass Leaf:\n    def run_pure(self,inputs,params):\n' + setup +
            f'        return {{"value.out": {expression}}}\n', library_rules=())
    assert report.status == "PASS", report.to_dict()


def test_same_class_name_and_private_field_do_not_inherit_another_nodes_identity(tmp_path):
    report = _project(tmp_path, "ordinary.py", 'class OtherNode:\n    _private=4\n',
        node_text='from ordinary import OtherNode\nclass Leaf:\n    def run_pure(self,inputs,params):\n        OtherNode()\n        return {"value.out":OtherNode._private}\n',
        library_rules=(), other_node=("actual.py", "OtherNode", 'class OtherNode:\n    def run_pure(self,inputs,params): return {}\n'))
    assert report.status == "PASS", report.to_dict()


@pytest.mark.parametrize("expression", ["Helper().calculate()", "instance.calculate()"])
def test_reachable_instance_helper_effects_belong_to_callers_rule(tmp_path, expression):
    setup = "        instance = Helper()\n" if expression.startswith("instance") else ""
    report = _project(tmp_path, "ordinary.py",
        'class Helper:\n    def calculate(self):\n        print("reached")\n        return 3\n',
        node_text='from ordinary import Helper\nclass Leaf:\n    def run_pure(self,inputs,params):\n' + setup +
            f'        return {{"value.out":{expression}}}\n', library_rules=())
    assert any(item.code == "NODE.EFFECT.CALL_FORBIDDEN" for item in report.errors), report.to_dict()


def test_source_resolved_alias_of_real_node_remains_a_forbidden_direct_call(tmp_path):
    source = ('class OtherNode:\n    def run_pure(self,inputs,params): return {}\n'
        'class Leaf:\n    def run_pure(self,inputs,params):\n        Foreign = OtherNode\n'
        '        Foreign().run_pure({}, {})\n        return {"value.out":1}\n')
    report = _project(tmp_path, "ordinary.py", 'def add(a,b): return a+b\n',
        node_text=source, library_rules=(), other_node=("leaf.py", "OtherNode", source))
    assert "NODE.METADATA.NODE_DIRECT_CALL" in {item.code for item in report.errors}, report.to_dict()


def test_source_visible_helper_constructor_effect_is_checked_without_unused_methods(tmp_path):
    report = _project(tmp_path, "ordinary.py",
        'class Helper:\n    def __init__(self): print("constructed")\n    def calculate(self): return 3\n',
        node_text='from ordinary import Helper\nclass Leaf:\n    def run_pure(self,inputs,params):\n        return {"value.out":Helper().calculate()}\n',
        library_rules=())
    assert any(item.code == "NODE.EFFECT.CALL_FORBIDDEN" for item in report.errors), report.to_dict()


def test_effect_preview_recognizes_an_ordinary_rule_by_its_typed_output():
    from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor
    from vibeflow.core.descriptors.contributions import ContributionBuilder, compose_contributions
    from vibeflow.core.rules import EFFECT_POLICY_TYPE, RuleCall, RuleDescriptor, RulesetDescriptor
    from vibeflow.targets.python.project.registry import NodeRegistry
    from vibeflow.targets.python.quality.rule_adapter import selected_effect_scope
    contribution = ContributionBuilder("custom")
    contribution.add(RuleDescriptor("custom.effects", outputs={"policy": EFFECT_POLICY_TYPE},
        params_schema={"effect_scope":{"type":"string"}}, params_defaults={"effect_scope":"global_state"}))
    contribution.add(RulesetDescriptor("custom.state", calls=(RuleCall("effects", rule_id="custom.effects"),)))
    registry = NodeRegistry()
    registry.rule_catalogs = (compose_contributions((contribution.finish(),)),)
    registry.register(NodeDescriptor("custom.node", "Node", "One selected rule", "1", "process", contract=NodeContractDescriptor(), rulesets=("custom.state",)))
    assert selected_effect_scope(registry, "custom.node") == "global_state"


@pytest.mark.parametrize("library,forbidden", [
    ("from urllib.parse import urlparse\ndef add(left,right): return len(urlparse('https://example.test').path)\n", False),
    ("from urllib.request import urlopen\ndef add(left,right): return urlopen('https://example.test')\n", True),
    ("import builtins\nimport sys\ndef add(left,right):\n    builtins.open('artifact.txt','w')\n    value=sys.argv\n    raise SystemExit(len(value))\n", True),
])
def test_declared_library_retains_external_import_and_effect_checks(tmp_path, library, forbidden):
    report = _project(tmp_path, "ordinary/math.py", library, node_rules=())
    assert bool(report.errors) == forbidden, report.to_dict()
    if forbidden:
        assert {item.code for item in report.errors} & {"BASE_LIB.BANNED_IMPORT", "BASE_LIB.SIDE_EFFECT_CALL"}
    assert not (tmp_path / "artifact.txt").exists()
