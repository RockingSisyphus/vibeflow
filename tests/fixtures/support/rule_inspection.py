"""Canonical declarations for CLI source-rule tests; classes hold execution only."""

import json
from pathlib import Path


def node_document(*, type_key="demo.node", class_name="DemoNode", contract=None, rulesets=None):
    return {'node_type': 'vibeflow.node',
        "kind": "node", 'id': type_key, "display_name": "Demo",
        "description": "A fixture Node with one declared result.", "version": "1.0", "flow_kind": "process",
        "rulesets": ["vibeflow.process"] if rulesets is None else rulesets,
        "contract": contract if contract is not None else {
            "provides": [{"key": "demo.out", "type": "demo.out", "display_name": "Demo Out"}],
            "output_semantics": {"demo.out": ["demo output"]}, "examples": [{"inputs": {}, "params": {}}],
        },
        "implementations": [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": "nodes/demo_node.py", "export": class_name}}],
    }


VALID_NODE_IMPORT = "from pathlib import Path\n\n"


def _valid_node_source(*, run_body='        return {"demo.out": 1}'):
    return f'{VALID_NODE_IMPORT}class DemoNode:\n    def run_pure(self, inputs, params):\n{run_body}\n'


def _inspect_node_source(tmp_path, capsys, source, *, node_type="demo.node", class_name="DemoNode", extra_args=None, descriptor=None, additional_nodes=()):
    from tests.fixtures.support.strict_support import cli_main
    tmp_path.mkdir(parents=True, exist_ok=True)
    module_path = tmp_path / "nodes/demo_node.py"
    module_path.parent.mkdir(exist_ok=True)
    module_path.write_text(source.strip(), encoding="utf-8")
    from tests.fixtures.support.plugins import write_plugin
    declarations = [node_document(type_key=node_type, class_name=class_name) if descriptor is None else descriptor,
                    *additional_nodes]
    selection = write_plugin(tmp_path, declarations, target="python")
    (tmp_path / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python"}), encoding="utf-8")
    config = tmp_path / "inspect.jsonc"
    config.write_text(json.dumps({"rulesets": [], "plugins": [selection], "pipeline": {"nodes": [{"id":"inspect", "definition_id":node_type, "display_name":"Inspect", "description":"Inspect one resource"}]}}))
    args = ["inspect-node", "--config", str(config), "--node-id", node_type, "--module", str(module_path), "--class", class_name, *(extra_args or ())]
    code = cli_main(args)
    return code, json.loads(capsys.readouterr().out)


def write_registry_project(root, registry, keys):
    """Publish fixture declarations and implementation source as a real project."""
    import inspect
    import textwrap
    root.mkdir(parents=True, exist_ok=True)
    from tests.fixtures.support.plugins import write_plugin
    import ast
    declarations, modules, selected = [], {}, {}
    for key in keys:
        implementation = registry.get(key)
        module = inspect.getmodule(implementation)
        source_path = inspect.getsourcefile(implementation)
        if source_path not in modules:
            tree = ast.parse(Path(source_path).read_text())
            symbols = {}
            for statement in tree.body:
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols[statement.name] = statement
                elif isinstance(statement, (ast.Import, ast.ImportFrom)):
                    for alias in statement.names:
                        symbols[alias.asname or alias.name.split(".")[0]] = statement
                elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                    targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
                    for target in targets:
                        if isinstance(target, ast.Name):
                            symbols[target.id] = statement
            modules[source_path] = (module, symbols)
        module, symbols = modules[source_path]
        if implementation.__name__ not in symbols:
            symbols[implementation.__name__] = ast.parse(textwrap.dedent(inspect.getsource(implementation))).body[0]
        pending = [implementation.__name__]
        while pending:
            name = pending.pop()
            statement = symbols.get(name)
            if statement is None or (source_path, name) in selected:
                continue
            # Execution fixtures retain their actual helper functions and imports.
            selected[(source_path, name)] = statement
            if not isinstance(statement, (ast.Import, ast.ImportFrom)):
                pending.extend(node.id for node in ast.walk(statement)
                               if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load))
        declaration = registry.descriptor(key).to_dict()
        declaration["implementations"] = [{"language": "python", "targets": ["python"],
            "source": {"kind": "file", "ref": "nodes/fixture_implementations.py", "export": implementation.__name__}}]
        declarations.append(declaration)
    imports, implementations, seen = [], [], set()
    for statement in selected.values():
        code = ast.unparse(statement)
        if code in seen:
            continue
        seen.add(code)
        (imports if isinstance(statement, (ast.Import, ast.ImportFrom)) else implementations).append(code)
    # Imported V is the fixed value accessor used by the native runtime fixtures.
    if any("V" in {node.id for node in ast.walk(statement) if isinstance(node, ast.Name)}
           for statement in selected.values()) and not any(code.startswith("def V(") for code in implementations):
        implementations.insert(0, 'def V(inputs, data_type):\n    return inputs[data_type]["value"]')
        imports = [code for code in imports if not ("strict_support" in code and " V" in code)]
    (root / "nodes").mkdir(exist_ok=True)
    (root / "nodes/fixture_implementations.py").write_text("from __future__ import annotations\n\n" + "\n".join(imports) + "\n\n" + "\n\n".join(implementations) + "\n", encoding="utf-8")
    (root / "vibeflow_project.jsonc").write_text(json.dumps({"project_target": "python"}), encoding="utf-8")
    return write_plugin(root, declarations, target="python")


def depth_ruleset(maximum, identifier="test.depth"):
    """Select nesting policy through the same Rule parameters as authors."""
    from vibeflow.core.rules import RuleCall,RuleRelation,RulesetDescriptor
    return RulesetDescriptor(identifier, calls=(RuleCall("base",ruleset_id="vibeflow.workflow"),),
        relations=(RuleRelation("$self","base/nodeset_types","overrides",params={"nodeset_max_depth":maximum}),),
        graph_scope="effective_subtree")
