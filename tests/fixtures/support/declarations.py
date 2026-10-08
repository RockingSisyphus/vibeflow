"""Small typed declaration builders for test data, independent of implementations."""

from dataclasses import replace
import ast
import json
from pathlib import Path

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor


def native_registry():
    """Explicitly assemble the standard SDK resources for native ABI tests."""
    from vibeflow.tooling.application.python.project.declarations import default_python_registry
    return default_python_registry()


def node_declaration(descriptor, contract, *, rulesets=("vibeflow.process",)):
    """Select a canonical contract and rules on an already canonical Node."""
    return replace(descriptor, contract=contract, rulesets=rulesets)


def configured_declaration(descriptor, schema=None, defaults=None, **values):
    return replace(descriptor, contract=replace(descriptor.contract,
        params_schema=schema or {}, params_defaults=defaults or {}), **values)


def write_node_plugin(root, registrations):
    """Write canonical test resources and the selected, ordinary Node classes."""
    from tests.fixtures.support import strict_support_runtime_nodes as nodes
    from tests.fixtures.support import strict_support_runtime_implementations as implementations

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    from tests.fixtures.support.plugins import write_plugin
    declarations = []
    source = ast.parse(Path(implementations.__file__).read_text(encoding="utf-8"))
    selected = {name for _, name, _, _ in registrations}
    body = [item for item in source.body if
            isinstance(item, ast.ClassDef) and item.name in selected or
            isinstance(item, ast.FunctionDef) and item.name == "V"]
    implementation = root / "fixture_nodes.py"
    implementation.write_text(ast.unparse(ast.Module(body=body, type_ignores=[])) + "\n", encoding="utf-8")
    for key, class_name, schema, defaults in registrations:
        declaration = configured_declaration(getattr(nodes, class_name + "_DECLARATION"), schema, defaults, type_key=key)
        payload = declaration.to_dict()
        payload["implementations"] = [{"language": "python", "targets": ["python"], "completion": "immediate",
                                      "source": {"kind": "file", "ref": "fixture_nodes.py", "export": class_name}}]
        declarations.append(payload)
    return write_plugin(root, declarations, target="python", plugin_id=f"fixture.{root.name}")
