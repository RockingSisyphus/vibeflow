"""Review the declared Python implementation ABI from the Target's AST."""
import ast
from typing import Mapping
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_subject


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
    if set(item.type for item in contract.requires) & set(item.key for item in contract.provides):
        report("contract_overlap", "contract.requires types and contract.provides keys must not overlap")
    if node.descriptor.flow_kind == "decision":
        if not any(_looks_route_key(item.key) for item in contract.provides):
            findings.append(finding(context, "NODE.DECISION.MISSING_ROUTE_OUTPUT",
                "decision nodes must provide a route/decision/branch output key", path=node.path, line=symbol.line))
    for index, example in enumerate(contract.examples):
        malformed = next((name for name in ("inputs", "params") if not isinstance(example.get(name), Mapping)), None)
        if malformed:
            findings.append(finding(context, "NODE.MAINTAINABILITY.EXAMPLE_SHAPE",
                f"contract.examples[{index}].{malformed} must be a mapping", path=node.path, line=symbol.line, severity="warning"))
        elif "outputs" in example:
            findings.append(finding(context, "NODE.PURITY.EXAMPLE_OUTPUTS_REMOVED",
                f"Python interface rule does not accept contract.examples[{index}].outputs; examples declare inputs and params", path=node.path, line=symbol.line))
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


def _looks_route_key(key):
    leaf = key.rsplit(".", 1)[-1].rsplit("_", 1)[-1]
    return key.startswith("flow.") or leaf in {"route", "decision", "branch", "selected", "done", "should_retry"} or key.endswith("selected_branch")
