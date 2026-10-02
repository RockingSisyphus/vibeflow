"""An explicit, inspectable domain convention for this example's model code.

The convention recognizes methods/functions named ``model_forward``. It does
not claim to recognize arbitrary machine learning code or infer a topology.
"""

import ast

from vibeflow.core.findings import HealthFinding
from vibeflow.core.rules import RuleRecord, RuleResult


def check(context, inputs, params):
    sources = context.require("source_context")
    descriptor = context.subject["descriptor"]
    current = next(node for node in sources.nodes if node.type_key == descriptor.type_key)
    implementation = sources.symbol(current.path, current.symbol)
    marker = params["marker_method"]
    category = params["model_category"]
    owned = {symbol.id for symbol in sources.helpers(descriptor.type_key)}
    definitions = tuple(symbol for symbol in sources.symbols
                        if symbol.name.rsplit(".", 1)[-1] == marker
                        and (symbol.id in owned or symbol.path == current.path
                             and "." not in symbol.name))
    direct = tuple(symbol for symbol in definitions
                   if symbol.path == current.path and symbol.name == current.symbol + "." + marker)
    findings = []
    for symbol in definitions:
        allowed = descriptor.category == category and symbol in direct
        if allowed:
            continue
        owners = sources.owners(symbol.id)
        findings.append(HealthFinding(
            rule_id="EXAMPLE.MODEL.LOCATION", severity="error", object_type="node",
            object_id=descriptor.type_key, failure_layer="implementation",
            message=f"{marker} must be defined directly in a {category} Node; referencing a helper does not grant model ownership.",
            source_location={"path": symbol.path, "line": symbol.line, "column": 1},
            details={"symbol": symbol.name, "ownership": [
                {"node_type": owner.type_key, "relation": owner.relation} for owner in owners]},
        ))
    if descriptor.category == category and len(direct) != 1:
        line = implementation.line if implementation is not None else 1
        findings.append(HealthFinding(
            rule_id="EXAMPLE.MODEL.ONE_BLOCK", severity="error", object_type="node",
            object_id=descriptor.type_key, failure_layer="implementation",
            message=f"A {category} Node must contain exactly one direct {marker} method; found {len(direct)}.",
            source_location={"path": current.path, "line": line, "column": 1},
            details={"count": len(direct)},
        ))
    # Inspect the copied AST as part of the public source interface. A domain
    # can choose a richer convention without rescanning files or importing Nodes.
    class_ast = implementation.node if implementation is not None else None
    helper_evidence = [{"symbol": symbol.name, "path": symbol.path,
                        "owners": [owner.type_key for owner in sources.owners(symbol.id)]}
                       for symbol in sources.helpers(descriptor.type_key)
                       if symbol.path != current.path]
    evidence = {"node_type": descriptor.type_key, "category": descriptor.category,
                "ast_kind": type(class_ast).__name__ if isinstance(class_ast, ast.AST) else "unavailable",
                "definitions": [{"symbol": symbol.name, "path": symbol.path, "line": symbol.line}
                                for symbol in definitions], "helpers": helper_evidence}
    return RuleResult({"evidence": RuleRecord("example.model_definition.v1", evidence)}, tuple(findings))
