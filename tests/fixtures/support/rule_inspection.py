"""Canonical declarations for CLI source-rule tests; classes hold execution only."""

import json
from pathlib import Path


def node_document(*, type_key="demo.node", class_name="DemoNode", contract=None, rulesets=None):
    return {
        "kind": "node", "type_key": type_key, "display_name": "Demo",
        "description": "A fixture Node with one declared result.", "version": "1.0", "flow_kind": "process",
        "rulesets": ["vibeflow.process"] if rulesets is None else rulesets,
        "contract": contract if contract is not None else {
            "provides": [{"key": "demo.out", "type": "demo.out", "display_name": "Demo Out"}],
            "output_semantics": {"demo.out": ["demo output"]}, "examples": [{"inputs": {}, "params": {}}],
        },
        "implementations": [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": "demo_node.py", "export": class_name}}],
    }


VALID_NODE_IMPORT = "from pathlib import Path\n\n"


def _valid_node_source(*, run_body='        return {"demo.out": 1}'):
    return f'{VALID_NODE_IMPORT}class DemoNode:\n    def run_pure(self, inputs, params):\n{run_body}\n'


def _inspect_node_source(tmp_path, capsys, source, *, node_type="demo.node", class_name="DemoNode", extra_args=None, descriptor=None, additional_nodes=()):
    from tests.fixtures.support.strict_support import cli_main
    tmp_path.mkdir(parents=True, exist_ok=True)
    module_path = tmp_path / "demo_node.py"
    module_path.write_text(source.strip(), encoding="utf-8")
    manifests = tmp_path / "manifests/nodes"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "node.jsonc").write_text(json.dumps(node_document(class_name=class_name) if descriptor is None else descriptor), encoding="utf-8")
    for index, declaration in enumerate(additional_nodes):
        (manifests / f"other-{index}.jsonc").write_text(json.dumps(declaration), encoding="utf-8")
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python", "descriptors": {"nodes": ["manifests/nodes"]}}), encoding="utf-8")
    args = ["inspect-node", "--type", node_type, "--module", str(module_path), "--class", class_name, *(extra_args or ())]
    code = cli_main(args)
    return code, json.loads(capsys.readouterr().out)


def write_registry_project(root, registry, keys):
    """Publish fixture declarations and implementation source as a real project."""
    import inspect
    import textwrap
    root.mkdir(parents=True, exist_ok=True)
    manifests = root / "manifests/nodes"
    manifests.mkdir(parents=True, exist_ok=True)
    classes = []
    for key in keys:
        implementation = registry.get(key)
        classes.append(textwrap.dedent(inspect.getsource(implementation)))
        declaration = registry.descriptor(key).to_dict()
        declaration["implementations"] = [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": "nodes.py", "export": implementation.__name__}}]
        (manifests / f"{key}.jsonc").write_text(json.dumps(declaration), encoding="utf-8")
    helpers = 'def V(inputs, data_type):\n    return inputs[data_type]["value"]\n\n'
    (root / "nodes.py").write_text(helpers + "\n\n".join(classes), encoding="utf-8")
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python", "descriptors": {"nodes": ["manifests/nodes"]}}), encoding="utf-8")
