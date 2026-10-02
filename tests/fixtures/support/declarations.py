"""Small typed declaration builders for test data, independent of implementations."""

from dataclasses import replace
import ast
import json
from pathlib import Path

from vibeflow.core.descriptors import NodeContractDescriptor, NodeDescriptor


def node_declaration(info, contract, *, rulesets=("vibeflow.process",)):
    return NodeDescriptor(
        type_key=info.type_key, display_name=info.display_name, category=info.category,
        description=info.description, version=info.version, flow_kind=info.flow_kind,
        author=info.author, tags=info.tags, external=info.external, rulesets=rulesets,
        contract=NodeContractDescriptor(
            requires=contract.requires, provides=contract.provides,
            input_semantics=contract.input_semantics or {item.type: (f"Fixture input {item.type}",) for item in contract.requires},
            output_semantics=contract.output_semantics or {item.key: (f"Fixture output {item.key}",) for item in contract.provides},
            examples=contract.examples,
        ),
    )


def configured_declaration(descriptor, schema=None, defaults=None, **values):
    return replace(descriptor, contract=replace(descriptor.contract,
        params_schema=schema or {}, params_defaults=defaults or {}), **values)


def write_node_manifests(root, registrations):
    """Write canonical test resources and the selected, ordinary Node classes."""
    from tests.fixtures.support import strict_support_runtime_nodes as nodes
    from tests.fixtures.support import strict_support_runtime_implementations as implementations

    root = Path(root)
    manifests = root / "manifests" / "nodes"
    manifests.mkdir(parents=True, exist_ok=True)
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
        (manifests / (key.replace(".", "-") + ".jsonc")).write_text(json.dumps(payload), encoding="utf-8")
