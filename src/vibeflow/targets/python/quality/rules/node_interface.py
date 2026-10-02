"""Review the declared Python implementation ABI from an isolated AST view."""
import ast
from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_subject


def node_interface(context, inputs, params):
    _, node, symbol = source_subject(context)
    if symbol is None or not isinstance(symbol.node, ast.ClassDef):
        return RuleResult(findings=(finding(context,"NODE.IMPLEMENTATION.SYMBOL","declared Python implementation must name a class",path=node.path),))
    methods = {item.name:item for item in symbol.node.body if isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef))}
    findings=[]
    def report(code,message,method=None):
        findings.append(finding(context,"NODE.CONTRACT."+code.upper(),message,path=node.path,line=method.lineno if method is not None else symbol.line))
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
    contract=node.descriptor.contract
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
