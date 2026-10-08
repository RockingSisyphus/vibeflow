"""Architecture retains selected project source facts independently of SVG."""
from vibeflow.core.descriptors import ContributionBuilder, ResourceOrigin, compose_contributions
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.tooling.presentation.resource_architecture import resource_architecture


def _catalogs(definitions):
    builder = ContributionBuilder("example")
    for index, definition in enumerate(definitions):
        builder.add(decode_resource(definition), origin=ResourceOrigin("example", "plugin.py", index + 1))
    return compose_contributions((builder.finish(),))


def _node(identifier, **extra):
    return {"kind":"node", "type_key":identifier, "display_name":identifier,
            "description":"Selected project implementation", "version":"1.0",
            "flow_kind":"process", "contract":{}, **extra}


def _implementation(path, *, support=()):
    return {"language":"python", "targets":["python"],
            "source":{"kind":"file", "ref":path, "export":"implementation"},
            "implementation_files":[{"kind":"file", "ref":part} for part in support]}


def test_selected_resources_keep_effective_rule_facts_without_svg_projection(tmp_path):
    catalogs = _catalogs((
        {"kind":"rule", "id":"health", "handler":"health", "outputs":{}},
        {"kind":"ruleset", "id":"checks", "calls":[{"id":"check", "rule_id":"health"}]},
        _node("example.step", rulesets=["checks"]),
        _node("example.unused"),
    ))
    facts = resource_architecture(catalogs, project_root=tmp_path, selected_nodes={"example.step"})
    assert set(facts) == {"resources", "files", "relations"}
    assert set(facts["resources"]) == {"node:example.step"}
    resource = facts["resources"]["node:example.step"]
    assert resource["origin"] == {"plugin_id":"example", "path":"plugin.py", "line":3, "symbol":""}
    assert resource["rulesets"] == ["checks"]
    assert resource["effective_rules"]["static"][0]["calls"][0]["rule_id"] == "health"


def test_source_membership_imports_and_unowned_dependencies_remain_machine_facts(tmp_path):
    paths = {name:str(tmp_path / name) for name in ("node.py", "support.py", "math.py", "unknown.py")}
    definitions = (
        _node("example.step", implementations=[_implementation("node.py", support=("support.py",))],
              base_libs=["example.math"]),
        {"kind":"base_lib", "id":"example.math", "display_name":"Math", "description":"Project math helper",
         "version":"1.0", "implementations":[_implementation("math.py")]},
    )
    snapshots = ({"path":paths["node.py"], "load_state":"loaded", "imports":[
        {"path":paths["math.py"], "specifier":"math", "line":7, "type_only":True}]},
        {"path":paths["support.py"], "load_state":"not_loaded", "imports":[{"path":paths["unknown.py"]}]},
        {"path":paths["math.py"], "load_state":"loaded", "imports":[]},
        {"path":paths["unknown.py"], "load_state":"unknown", "imports":[]})
    facts = resource_architecture(_catalogs(definitions), project_root=tmp_path,
                                 selected_nodes={"example.step"}, source_facts=snapshots)
    files = {value["path"]:value for value in facts["files"].values()}
    assert set(files) == set(paths.values())
    assert files[paths["support.py"]]["owners"] == [
        {"kind":"node", "id":"example.step", "role":"support", "symbol":""}]
    assert files[paths["support.py"]]["load_state"] == "not_loaded"
    assert files[paths["unknown.py"]]["owners"] == []
    assert {"from":"node:example.step", "to":"base_lib:example.math", "relation":"base_lib"} in facts["relations"]
    imported = next(edge for edge in facts["relations"] if edge.get("specifier") == "math")
    assert imported["line"] == 7 and imported["type_only"] is True
    assert imported["from"] == files[paths["node.py"]]["id"]
    assert imported["to"] == files[paths["math.py"]]["id"]
