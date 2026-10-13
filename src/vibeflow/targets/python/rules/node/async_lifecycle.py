"""Check the public task-controller boundary separately from the Node ABI."""
import ast
from vibeflow.core.rules import RuleResult
from .helpers import finding, source_subject


def async_lifecycle(context, inputs, params):
    if context.subject.get("kind") == "plugin":
        return RuleResult()
    sources, node, symbol = source_subject(context)
    if symbol is None:
        return RuleResult()
    members = sources.class_members(symbol)
    entry = members.get("run_pure")
    if entry is None:
        return RuleResult()
    method = entry._node
    arguments = (*method.args.posonlyargs, *method.args.args)
    manager = node.descriptor.flow_kind == "task_manager"
    findings = []
    if manager and len(arguments) != 4:
        findings.append(finding(context, "VF_TASK_CONTEXT_REQUIRED",
            "task_manager must accept run_pure(self, inputs, params, context)",
            path=entry.path, line=method.lineno))
    if not manager and len(arguments) == 4:
        context_name = arguments[3].arg
        for item in ast.walk(method):
            if isinstance(item, ast.Attribute) and item.attr == "tasks" and isinstance(item.value, ast.Name) and item.value.id == context_name:
                findings.append(finding(context, "VF_TASK_CONTROL_FORBIDDEN",
                    "task controller is available only to task_manager Nodes",
                    path=entry.path, line=item.lineno))
    findings.extend(_OwnedWorkScanner.findings(context,sources,node,symbol))
    return RuleResult(findings=tuple(findings))


class _OwnedWorkScanner:
    """Reuse the effect walker's lexical binding facts for native work handles."""
    @staticmethod
    def findings(context, sources, node, symbol):
        from .effect_visitors import ModulePurityVisitor, qualified_reference_name
        from .helpers import source_info, source_policy
        from vibeflow.targets.python.quality.source_analysis.resource_slices import node_source_slices
        constructors = {'threading.Thread', 'multiprocessing.Process',
                        'concurrent.futures.ThreadPoolExecutor', 'concurrent.futures.ProcessPoolExecutor'}
        diagnostics = []
        for source, tree in node_source_slices(context, node, symbol):
            parents = {id(child): parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
            class Scanner(ModulePurityVisitor):
                def __init__(self):
                    super().__init__(policy=source_policy({},sections=('imports',)),
                        source=source_info(source), effect_scope='python_io', audit_all_definitions=True,
                        resolved_calls=sources.resolved_function_calls(source.path))
                    self.handles = {}

                def visit_FunctionDef(self, item):
                    previous=self.handles;self.handles={}
                    try:super().visit_FunctionDef(item)
                    finally:self.handles=previous

                def visit_Assign(self, item):
                    for target in item.targets:
                        self.handles.pop(ast.unparse(target),None)
                    super().visit_Assign(item)

                def visit_AnnAssign(self, item):
                    self.handles.pop(ast.unparse(item.target),None)
                    super().visit_AnnAssign(item)

                visit_AsyncFunctionDef = visit_FunctionDef

                def _owned(self, call, handle, cleanup):
                    ancestor=call
                    method=None
                    while id(ancestor) in parents:
                        ancestor=parents[id(ancestor)]
                        if isinstance(ancestor,(ast.With,ast.AsyncWith)):
                            for entry in ancestor.items:
                                if entry.optional_vars and ast.unparse(entry.optional_vars)==handle:return True
                        if isinstance(ancestor,(ast.FunctionDef,ast.AsyncFunctionDef)):
                            method=ancestor;break
                    if method is None:return False
                    for statement in ast.walk(method):
                        if not isinstance(statement,ast.Try):continue
                        for final in statement.finalbody:
                            for item in ast.walk(final):
                                if isinstance(item,ast.Call) and isinstance(item.func,ast.Attribute) and item.func.attr==cleanup and ast.unparse(item.func.value)==handle:
                                    if cleanup=='join':
                                        if not item.args and all(k.arg=='timeout' and isinstance(k.value,ast.Constant) and k.value.value is None for k in item.keywords):return True
                                    elif (not item.args or len(item.args)==1 and isinstance(item.args[0],ast.Constant) and item.args[0].value is True) and all(k.arg!='wait' or isinstance(k.value,ast.Constant) and k.value.value is True for k in item.keywords):return True
                    return False

                def _check_effect_call(self, call):
                    names={qualified_reference_name(call.func,a) for a in self._call_alias_views(call)}
                    native=next((name for name in names if name in constructors),'')
                    parent=parents.get(id(call))
                    if native and isinstance(parent,ast.Assign) and len(parent.targets)==1:
                        self.handles[ast.unparse(parent.targets[0])]=native
                    if native and isinstance(parent,ast.AnnAssign):
                        self.handles[ast.unparse(parent.target)]=native
                    if native and isinstance(parent,ast.withitem) and parent.optional_vars:
                        self.handles[ast.unparse(parent.optional_vars)]=native
                    if isinstance(call.func,ast.Attribute):
                        handle=ast.unparse(call.func.value)
                        kind=self.handles.get(handle,'')
                        if isinstance(call.func.value,ast.Call):
                            kind=next((qualified_reference_name(call.func.value.func,a) for a in self._call_alias_views(call) if qualified_reference_name(call.func.value.func,a) in constructors),'')
                        if kind and call.func.attr in ('start','submit','map'):
                            cleanup='shutdown' if kind.endswith('Executor') else 'join'
                            if not self._owned(call,handle,cleanup):
                                diagnostics.append(finding(context,'VF_NODE_RESOURCE_UNOWNED',
                                    'native background work must be joined in finally or owned by an executor context; use declared task_targets for workflow tasks',
                                    path=source.path,line=call.lineno))
                    if '_thread.start_new_thread' in names:
                        diagnostics.append(finding(context,'VF_NODE_RESOURCE_UNOWNED',
                            'unowned native thread callback is forbidden; use declared task_targets',path=source.path,line=call.lineno))
            Scanner().visit(tree)
        return diagnostics
