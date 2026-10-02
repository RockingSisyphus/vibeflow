"""Check import-time execution without importing the project source."""

import ast

from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.quality.rules.helpers import finding, source_subject


def import_side_effects(context, inputs, params):
    sources = context.require("source_context")
    findings = []
    for source in sources.files:
        if source.tree is None:
            findings.append(finding(context, "QUALITY.SYNTAX.PYTHON", source.parse_error, path=source.path))
            continue
        visitor = _ImportExecutionVisitor(allow_mutable_state=params.get("effect_scope") == "global_state", tree=source.tree)
        visitor.visit(source.tree)
        findings.extend(finding(context, "NODE.IMPORT.SIDE_EFFECT", reason, path=source.path, line=item.lineno, column=item.col_offset + 1)
                        for item, reason in visitor.violations)
    return RuleResult(findings=tuple(findings))


class _ImportExecutionVisitor(ast.NodeVisitor):
    """Visit expressions evaluated by module/class/function declaration."""

    def __init__(self, *, allow_mutable_state=False, tree=None):
        self.violations = []
        self.allow_mutable_state = allow_mutable_state
        self.classes = {item.name:item for item in (tree.body if tree else ()) if isinstance(item,ast.ClassDef)}

    def _decorators(self, node):
        for expression in node.decorator_list:
            if not (isinstance(expression,ast.Name) and expression.id in {"staticmethod","classmethod"}):
                self.violations.append((expression, "a decorator executes code while importing source"))

    def visit_FunctionDef(self, node):
        self._decorators(node)
        for expression in (*node.args.defaults, *(value for value in node.args.kw_defaults if value is not None)):
            self.visit(expression)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._decorators(node)
        for base in node.bases:
            declaration = self.classes.get(base.id) if isinstance(base,ast.Name) else None
            if declaration is not None and any(isinstance(item,(ast.FunctionDef,ast.AsyncFunctionDef)) and item.name == "__init_subclass__" for item in declaration.body):
                self.violations.append((base, "the base class runs __init_subclass__ while importing source"))
        for keyword in node.keywords:
            if keyword.arg == "metaclass":
                self.violations.append((keyword.value,"a custom metaclass executes code while importing source"))
        for expression in (*node.bases, *(item.value for item in node.keywords)):
            self.visit(expression)
        for statement in node.body:
            self.visit(statement)

    def visit_Call(self, node):
        self.violations.append((node, "a call executed while importing source must be removed or covered by a replacement import rule"))

    def visit_Await(self, node):
        self.violations.append((node, "import-time await is not allowed by the selected import rule"))

    def visit_With(self, node):
        self.violations.append((node, "import-time context-manager execution is not allowed by the selected import rule"))

    visit_AsyncWith = visit_With

    def visit_For(self, node):
        self.violations.append((node, "import-time iteration is not allowed by the selected import rule"))

    visit_AsyncFor = visit_For
    visit_While = visit_For

    def visit_If(self, node):
        # TYPE_CHECKING is a static annotation convention, not an execution branch.
        if isinstance(node.test,ast.Name) and node.test.id == "TYPE_CHECKING":
            return
        self.violations.append((node,"import-time control flow is not allowed by the selected import rule"))

    def visit_Assign(self, node):
        if not self.allow_mutable_state and isinstance(node.value,(ast.List,ast.Set,ast.Dict)):
            self.violations.append((node,"mutable state created while importing source requires an explicit state import rule"))
        self.visit(node.value)

    def visit_AnnAssign(self, node):
        if node.value is not None:
            self.visit_Assign(ast.Assign(targets=[node.target],value=node.value,lineno=node.lineno,col_offset=node.col_offset))
