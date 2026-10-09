"""Review the declared Python implementation ABI from the Target's AST."""
import ast
from typing import Mapping
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_subject
from vibeflow.targets.python.quality.source_analysis.bindings import _function_definition_expressions


def node_interface(context, inputs, params):
    if context.subject.get("kind") == "plugin":
        source = context.require("resource_source_file")
        symbol = context.require("source_context").symbol(source.path, context.require("resource_symbol"))
        if symbol is None or not isinstance(symbol._node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return RuleResult(findings=(finding(context,"PLUGIN.IMPLEMENTATION.SYMBOL",
                "declared Python plugin must name a class or factory",path=source.path),))
        return RuleResult()
    sources, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol._node, ast.ClassDef):
        return RuleResult(findings=(finding(context,"NODE.IMPLEMENTATION.SYMBOL","declared Python implementation must name a class",path=node.path),))
    try:
        members = sources.class_members(symbol)
    except ValueError as exc:
        return RuleResult(findings=(finding(context, "NODE.CONTRACT.INHERITANCE", str(exc),
            path=node.path, line=symbol.line),))
    methods = {name:item._node for name,item in members.items()}
    findings=[]
    def report(code,message,method=None):
        owner = members.get(getattr(method, "name", "")) if method is not None else None
        findings.append(finding(context,"NODE.CONTRACT."+code.upper(),message,path=owner.path if owner else node.path,
            line=method.lineno if method is not None else symbol.line))
    method=methods.get("run_pure")
    if method is None:
        report("missing_run_pure","node must define run_pure(self, inputs, params)")
    elif isinstance(method,ast.AsyncFunctionDef):
        report("async_run_pure","run_pure must not be async",method)
    elif not _signature(method,("self","inputs","params")):
        report("run_pure_signature","run_pure must accept exactly self, inputs, params",method)
    if method is not None and any(isinstance(item, (ast.Yield, ast.YieldFrom))
            for item in _entry_body_nodes(method)):
        report("generator_run_pure", "run_pure must return a mapping rather than yield", method)
    init=methods.get("__init__")
    if init is not None and (not _signature(init,("self",)) or init.args.defaults):
        report("init_signature","__init__ must accept only self",init)
    if "run" in methods:
        report("context_run_forbidden","Node must execute through run_pure",methods["run"])
    allowed={"run_pure",*params.get("allowed_methods",())}
    for name,method in methods.items():
        if not name.startswith("_") and name not in allowed:
            report("public_callable",f"node must not expose public callable method: {name}",method)
    callable_names = set(methods)
    for statement in symbol._node.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        value = statement.value
        callable_value = isinstance(value, ast.Lambda) or isinstance(value, ast.Name) and value.id in callable_names
        if not callable_value:
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
        for target in targets:
            if isinstance(target, ast.Name):
                callable_names.add(target.id)
                if not target.id.startswith("_") and target.id not in allowed:
                    report("public_callable", f"node must not expose public callable method: {target.id}", statement)
    contract=node.descriptor.contract
    for index, example in enumerate(contract.examples):
        malformed = next((name for name in ("inputs", "params") if not isinstance(example.get(name), Mapping)), None)
        if malformed:
            findings.append(finding(context, "NODE.MAINTAINABILITY.EXAMPLE_SHAPE",
                f"contract.examples[{index}].{malformed} must be a mapping", path=node.path, line=symbol.line, severity="warning"))
    for label,keys,semantics in (("input_semantics",tuple(item.type for item in contract.requires),contract.input_semantics),
                                ("output_semantics",tuple(item.key for item in contract.provides),contract.output_semantics)):
        missing=set(keys)-set(semantics)
        extra=set(semantics)-set(keys)
        if missing:
            report("contract_semantics_missing",f"contract.{label} must describe declared keys: {sorted(missing)}")
        if extra:
            report("contract_semantics_unknown",f"contract.{label} contains undeclared keys: {sorted(extra)}")
    return RuleResult(findings=tuple(findings))


def _signature(method,names):
    args=method.args
    return tuple(item.arg for item in (*args.posonlyargs,*args.args)) == names and not args.vararg and not args.kwarg and not args.kwonlyargs




def _entry_body_nodes(method):
    def walk(node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            for expression in _function_definition_expressions(node):
                yield from walk(expression)
            return
        if isinstance(node, ast.ClassDef):
            for expression in (*node.bases, *(item.value for item in node.keywords), *node.decorator_list):
                yield from walk(expression)
            return
        yield node
        for child in ast.iter_child_nodes(node):
            yield from walk(child)
    for statement in method.body:
        yield from walk(statement)
