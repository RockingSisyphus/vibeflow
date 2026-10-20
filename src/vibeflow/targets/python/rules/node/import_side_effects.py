"""Check import-time execution without importing the project source."""

import ast

from vibeflow.core.rules import RuleResult
from vibeflow.targets.python.rules.node.helpers import finding, rule_effect_scope
from vibeflow.targets.python.quality.policy_parameters import source_policy
from vibeflow.targets.python.quality.source_analysis.ast_facts import import_modules
from vibeflow.targets.python.rules.node.effect_policy import policy_import_violation_code


def import_side_effects(context, inputs, params):
    scope = rule_effect_scope(params)
    policy = source_policy(params, sections=("imports",), effect_defaults=False)
    sources = context.require("source_context")
    findings = []
    from vibeflow.targets.python.project.source_membership import subject_files
    from vibeflow.targets.python.rules.node.source_ownership import ownership_findings
    files = subject_files(context)
    findings.extend(ownership_findings(context))
    for source in files:
        if source._tree is None:
            findings.append(finding(context, "QUALITY.SYNTAX.PYTHON", source.parse_error, path=source.path))
            continue
        for statement in ast.walk(source._tree):
            if not isinstance(statement, (ast.Import, ast.ImportFrom)):
                continue
            for module in import_modules(statement):
                if isinstance(statement, ast.ImportFrom) and module == "urllib" and {alias.name for alias in statement.names} == {"parse"}:
                    module = "urllib.parse"
                if policy_import_violation_code(module, policy=policy):
                    findings.append(finding(context, "NODE.IMPORT.POLICY_FORBIDDEN", f"import forbidden by the selected policy: {module}",
                        path=source.path, line=statement.lineno, column=statement.col_offset + 1))
        visitor = _ImportExecutionVisitor(allow_mutable_state=scope == "global_state", tree=source._tree)
        visitor.visit(source._tree)
        findings.extend(finding(context, "NODE.IMPORT.SIDE_EFFECT", reason, path=source.path, line=item.lineno, column=item.col_offset + 1)
                        for item, reason in visitor.violations)
    return RuleResult(findings=tuple(findings))


class _ImportExecutionVisitor(ast.NodeVisitor):
    """Visit expressions evaluated by module/class/function declaration."""

    def __init__(self, *, allow_mutable_state=False, tree=None):
        self.violations = []
        self.allow_mutable_state = allow_mutable_state
        self.classes = {item.name:item for item in (tree.body if tree else ()) if isinstance(item,ast.ClassDef)}
        self.bindings = {name: "builtins." + name for name in ("staticmethod", "classmethod", "property")}
        self.module_bindings = dict(self.bindings)
        self._collect_bindings(tree.body if tree else (), self.module_bindings)
        self.bindings = dict(self.module_bindings)

    @staticmethod
    def _collect_bindings(body, bindings):
        for statement in body:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    bindings[alias.asname or alias.name.split(".")[0]] = alias.name
            elif isinstance(statement, ast.ImportFrom):
                for alias in statement.names:
                    bindings[alias.asname or alias.name] = (statement.module or "") + "." + alias.name if not statement.level else ""
            elif isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                bindings[statement.name] = ""
            elif isinstance(statement, (ast.Assign, ast.AnnAssign)):
                targets = statement.targets if isinstance(statement, ast.Assign) else (statement.target,)
                for target in targets:
                    for item in ast.walk(target):
                        if isinstance(item, ast.Name):
                            bindings[item.id] = ""

    def _builtin_decorator(self, expression):
        if isinstance(expression, ast.Name):
            name = self.bindings.get(expression.id, "")
        elif isinstance(expression, ast.Attribute) and isinstance(expression.value, ast.Name):
            name = self.bindings.get(expression.value.id, "") + "." + expression.attr
        else:
            name = ""
        return name in {"builtins.staticmethod", "builtins.classmethod", "builtins.property"}

    def _decorators(self, node):
        for expression in node.decorator_list:
            if self._sdk_call(expression):
                for argument in (*expression.args, *(item.value for item in expression.keywords)):
                    self.visit(argument)
            elif not self._builtin_decorator(expression):
                self.violations.append((expression, "a decorator executes code while importing source"))

    def _sdk_call(self, expression):
        if not isinstance(expression, ast.Call):
            return False
        def name(value):
            if isinstance(value, ast.Name):
                return self.bindings.get(value.id, "")
            if isinstance(value, ast.Attribute):
                return name(value.value) + "." + value.attr
            return ""
        prefix = "vibeflow.targets.python.sdk."
        return name(expression.func) in {prefix + item for item in (
            "Plugin", "node", "rule", "ruleset", "data_schema", "base_lib", "lifecycle", "capability",
            "host_extension", "SourceLocator", "RuleCall", "RuleRelation", "DataProvider",
            "DataRequirement", "NodeContractDescriptor")}

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
        previous = self.bindings
        self.bindings = dict(self.module_bindings)
        self._collect_bindings(node.body, self.bindings)
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self.bindings = previous

    def visit_Call(self, node):
        if self._sdk_call(node):
            for argument in (*node.args, *(item.value for item in node.keywords)):
                self.visit(argument)
        else:
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

    def visit_Try(self, node):
        self.violations.append((node, "import-time try control flow is not allowed by the selected import rule"))

    visit_TryStar = visit_Try
    visit_Match = visit_Try

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
