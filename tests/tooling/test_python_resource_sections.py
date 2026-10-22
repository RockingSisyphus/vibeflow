"""User directories exclude framework definitions and source-review graphs."""
import json
import re

import pytest

from tests.targets.python.test_code_plugins import executable_project
from vibeflow.tooling.application.python.presentation.architecture_document import build_architecture_document
from vibeflow.tooling.application.python.presentation.mermaid import export_mermaid, review_fragments, review_svg
from vibeflow.tooling.presentation.mermaid.types import SvgFragment
from vibeflow.tooling.application.python.workspace_service import load_workspace_graph_for_export


SOURCE = '''from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,base_lib
from vibeflow.core.rules import RuleResult
@node(node_type='vibeflow.node', id="demo.start",flow_kind="terminal",contract={},rulesets=[])
class Start:
    def run_pure(self,inputs,params):
        raise AssertionError("business must remain untouched")
@node(node_type='vibeflow.node', id="demo",contract={"provides":[{"key":"result","type":"number","display_name":"Result"}],"output_semantics":{"result":["A result"]}},rulesets=["demo.rules"])
class Demo:
    def run_pure(self,inputs,params):
        raise AssertionError("business must remain untouched")
@base_lib(id="demo.library",rulesets=[])
def library(value):
    return value
@base_lib(id="demo.other",rulesets=[])
def other(value):
    return value
@rule(id="demo.check")
def check(context,inputs,params):
    check.calls += 1
    return RuleResult()
check.calls = 0
rules=ruleset(id="demo.rules",calls=[{"id":"check","rule_id":"demo.check"}])
def runtime(context):
    raise AssertionError("runtime factory must remain untouched")
plugin=Plugin(id="demo",resources=[Start,Demo,library,other,check,rules],runtime=runtime,rulesets=[],declaration_rulesets=[])
'''


@pytest.fixture
def checked(tmp_path):
    start = SOURCE.index('@base_lib')
    end = SOURCE.index('@rule')
    business, libraries = SOURCE[:start], SOURCE[start:end]
    plugin = SOURCE[:SOURCE.index('@node')] + SOURCE[end:]
    plugin = plugin.replace('resources=[Start,Demo,library,other,check,rules]', 'resources=[check,rules]')
    workspace, config = executable_project(tmp_path, business, plugin_source=plugin)
    (tmp_path / "base_lib").mkdir()
    (tmp_path / "base_lib/libraries.py").write_text('from vibeflow.targets.python.sdk import base_lib\n' + libraries)
    value = json.loads(config.read_text())
    value["base_lib"] = {"modules":[{"id":"demo.library","style":{"fill":"#ffeebb"}},"demo.other"]}
    config.write_text(json.dumps(value))
    graph,compiled,registry,resources,error,health,prepared = load_workspace_graph_for_export(
        config,workspace=workspace,validate_health=True,_include_presentation=True)
    assert error is None and not health.errors
    check = registry.direct_bindings[("rule","demo.check")]
    assert check.calls == 1
    # Populate the immutable document before observing view-only operations.
    document = build_architecture_document(graph,prepared=prepared)
    return graph,compiled,registry,resources,prepared,document,check


def _forbid_execution(monkeypatch):
    from vibeflow.targets.python.project import GraphCompiler, NodeRegistry
    from vibeflow.targets.python.quality import rule_adapter
    from vibeflow.targets.python.project import resource_rules, source_closure
    from vibeflow.tooling.architecture import resources as resource_architecture

    def unexpected(*_args,**_kwargs):
        raise AssertionError("a prepared presentation must not compile, bind, check or scan")

    monkeypatch.setattr(GraphCompiler,"compile_with_findings",unexpected)
    monkeypatch.setattr(GraphCompiler,"prepare_implementation_facts",unexpected)
    monkeypatch.setattr(NodeRegistry,"get",unexpected)
    monkeypatch.setattr(rule_adapter,"execute_python_node_rules",unexpected)
    monkeypatch.setattr(resource_rules,"review_python_resource",unexpected)
    monkeypatch.setattr(source_closure,"collect_python_source_facts",unexpected)
    monkeypatch.setattr(resource_architecture,"compile_ruleset",unexpected)


def assert_user_diagram(text):
    for forbidden in ("Node types", "Rule: demo.check", "Ruleset: demo.rules",
                      "reference", "implementation files", "rule_implementation",
                      "relation: contributes", "file:"):
        assert forbidden not in text


def test_user_directories_reuse_the_checked_snapshot(checked,monkeypatch):
    graph,_,_,resources,prepared,document,check = checked
    _forbid_execution(monkeypatch)
    text = export_mermaid(graph,resources=resources,prepared=prepared,
        mermaid_layout="review-columns")
    assert_user_diagram(text)
    assert "resource_plugins" in text and "resource_base_lib" in text
    assert text.split('subgraph __vibeflow_layout_plugins',1)[1].split("  end",1)[0].count("id: demo\\n") == 1
    assert "id: demo.runtime" not in text
    assert "id: demo.library" in text and "id: demo.other" in text
    assert "style resource_base_lib_0 fill:#ffeebb" in text
    assert check.calls == 1
    assert build_architecture_document(graph,prepared=prepared) == document
    assert set(document["implementation_graph"]) == {"resources", "files", "relations"}


@pytest.mark.parametrize("selection",["empty","library","plugins"])
def test_real_sdk_explicit_subset_preserves_only_selected_resources(checked,selection,monkeypatch):
    graph,_,_,resources,prepared,document,check = checked
    _forbid_execution(monkeypatch)
    payload = resources.to_dict()
    if selection == "empty":
        selected = {}
    elif selection == "library":
        selected = {"base_lib":{"modules":[payload["base_lib"]["modules"][0]]}}
    else:
        selected = {"plugins":payload["plugins"]}
    text = export_mermaid(graph,resources=selected,prepared=prepared,
        mermaid_layout="review-columns")
    sections = set(re.findall(r'subgraph __vibeflow_layout_(plugins|base_lib|host_extensions)\[',text))
    expected = {"base_lib"} if selection == "library" else {"plugins"} if selection == "plugins" else set()
    assert sections == expected
    assert "id: demo.other" not in text
    assert_user_diagram(text)
    assert build_architecture_document(graph,prepared=prepared) == document and check.calls == 1


def test_svg_uses_simple_directories_and_preserves_empty_selection(checked,tmp_path,monkeypatch):
    graph,compiled,_,resources,prepared,document,check = checked
    _forbid_execution(monkeypatch)
    fragments = []

    def render(title,text,*_args,**_kwargs):
        fragments.append((title,text))
        return SvgFragment(title,'<svg viewBox="0 0 100 40"><rect width="100" height="40"/></svg>',100,40)

    monkeypatch.setattr(review_fragments,"_render_fragment",render)
    review_svg.render_review_columns_svg(graph,compiled,tmp_path/"full.svg",prepared=prepared,
        resources=resources)
    assert [title for title,_ in fragments] == ["main pipeline", "plugins", "base_lib"]
    for _,text in fragments:
        assert_user_diagram(text)
    assert fragments[1][1].count("id: demo\\n") == 1
    assert fragments[2][1].count("resource_base_lib -.->") == 2
    fragments.clear()
    review_svg.render_review_columns_svg(graph,compiled,tmp_path/"empty.svg",prepared=prepared,resources={})
    assert len(fragments) == 1 and fragments[0][0] == "main pipeline"
    assert check.calls == 1 and build_architecture_document(graph,prepared=prepared) == document


def test_removed_internal_diagram_option_is_not_a_public_api(checked):
    graph,_,_,resources,prepared,_,_=checked
    with pytest.raises(TypeError,match="show_rules"):
        export_mermaid(graph,resources=resources,prepared=prepared,show_rules=True)


def test_user_renderers_never_request_source_review_architecture(checked,tmp_path,monkeypatch):
    from importlib.util import find_spec
    from vibeflow.tooling.application.python.presentation.prepared import PreparedPythonPresentation

    graph,compiled,_,resources,prepared,_,_=checked
    assert find_spec("vibeflow.tooling.presentation.resource_mermaid") is None

    def forbidden(*_args,**_kwargs):
        raise AssertionError("a user SVG must not project source-review architecture")

    monkeypatch.setattr(PreparedPythonPresentation,"architecture",forbidden)
    monkeypatch.setattr(review_fragments,"_render_fragment",lambda title,*args,**kwargs:
        SvgFragment(title,'<svg viewBox="0 0 100 40"><rect width="100" height="40"/></svg>',100,40))
    for layout in ("default","review-columns"):
        assert_user_diagram(export_mermaid(graph,resources=resources,prepared=prepared,mermaid_layout=layout))
    review_svg.render_review_columns_svg(graph,compiled,tmp_path/"user.svg",prepared=prepared,resources=resources)
