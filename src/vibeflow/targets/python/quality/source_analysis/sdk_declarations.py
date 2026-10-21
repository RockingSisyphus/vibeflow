"""Recognize SDK construction by imported identity, including local aliases."""

import ast


CONSTRUCTORS = frozenset({"Plugin", "node", "node_type", "rule", "ruleset", "data_schema", "base_lib", "lifecycle",
    "capability",  "RuleCall", "RuleRelation", "SourceLocator",
    "DataProvider", "DataRequirement", "NodeContractDescriptor"})


def declaration_calls(tree):
    bindings, result = {}, set()
    for statement in tree.body:
        if isinstance(statement, ast.ImportFrom):
            for name in statement.names:
                bindings[name.asname or name.name] = (statement.module or "") + "." + name.name
        elif isinstance(statement, ast.Import):
            for name in statement.names:
                bindings[name.asname or name.name.split(".")[0]] = name.name if name.asname else name.name.split(".")[0]
        else:
            for expression in ast.walk(statement):
                if isinstance(expression, ast.Call):
                    parts, value = [], expression.func
                    while isinstance(value, ast.Attribute):
                        parts.insert(0, value.attr)
                        value = value.value
                    if isinstance(value, ast.Name):
                        qualified = ".".join([bindings.get(value.id, value.id), *parts])
                        if qualified.startswith("vibeflow.targets.python.sdk.") and qualified.rsplit(".", 1)[-1] in CONSTRUCTORS:
                            result.add(expression)
            if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                for target in targets:
                    for name in ast.walk(target):
                        if isinstance(name, ast.Name):
                            bindings.pop(name.id, None)
            elif isinstance(statement, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                bindings.pop(statement.name, None)
    return frozenset(result)
