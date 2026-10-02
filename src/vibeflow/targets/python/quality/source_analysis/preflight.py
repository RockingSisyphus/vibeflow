"""Immutable loader facts and explicit import Ruleset evaluation."""
from __future__ import annotations
import ast
from dataclasses import dataclass, field
from vibeflow.core.rules import RuleContext, compile_ruleset, execute_rule_plan
from vibeflow.core.rules.builtin import builtin_effect_resources
from vibeflow.targets.python.quality.source_context import PythonSourceFile, build_python_source_context

@dataclass(frozen=True)
class PythonPreflightFinding:
    path: str
    line: int
    column: int
    message: str
    code: str = ""

@dataclass(frozen=True)
class PythonSourceFact:
    source_id: str
    path: str
    source: str
    module_name: str = ""
    import_time_dependencies: tuple[str, ...] = ()
    runtime_dependencies: tuple[str, ...] = ()
    is_base_lib: bool = False
    load_error: str = ""
    _tree: ast.Module | None = field(default=None, compare=False, repr=False)
    parse_error: str = ""
    root_path: str = ""
    parse_line: int = 1
    parse_column: int = 1

class PythonSourcePreflightError(ValueError):
    def __init__(self, findings):
        self.findings = tuple(findings)
        first = self.findings[0]
        super().__init__(f"{first.path}:{first.line}:{first.column}: {first.message}")


def preflight_python_source_facts(entry_source_id, sources, *, rulesets=("vibeflow.base_lib",)):
    """Loader default is an explicit Ruleset, independent of flow_kind/classes."""
    from vibeflow.targets.python.quality.rules import python_rule_handlers
    snapshots = tuple(PythonSourceFile(item.path, item.module_name, item.source, _tree=item._tree, parse_error=item.parse_error or item.load_error,parse_line=item.parse_line,parse_column=item.parse_column)
                      if item._tree is not None or item.parse_error or item.load_error else PythonSourceFile.parse(item.path, item.module_name, item.source)
                      for item in sources)
    context = build_python_source_context((), snapshots)
    rules, sets = builtin_effect_resources()
    rules = {item.id:item for item in rules}
    sets = {item.id:item for item in sets}
    findings = []
    for selected in rulesets:
        plan = compile_ruleset(selected, rules=rules, rulesets=sets, entrypoint="import")
        result = execute_rule_plan(plan, RuleContext(facts={"source_context":context}, subject={"kind":"source", "id":entry_source_id}, phase="import", target="python"), handlers=python_rule_handlers())
        for item in result.findings:
            if item.severity == "error":
                findings.append(PythonPreflightFinding(str(item.source_location.get("path", entry_source_id)), int(item.source_location.get("line",1)),
                    int(item.source_location.get("column",1)), item.message, item.rule_id))
    if findings:
        raise PythonSourcePreflightError(findings)

__all__ = ["PythonSourceFact", "PythonPreflightFinding", "PythonSourcePreflightError", "preflight_python_source_facts"]
