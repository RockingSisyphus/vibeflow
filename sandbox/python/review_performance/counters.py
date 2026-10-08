"""Observe calls in memory without replacing checks or business implementations."""

import ast
from collections import Counter, defaultdict
from contextlib import ExitStack
from time import perf_counter
from unittest.mock import patch


class Observations:
    def __init__(self):
        self.calls = Counter()
        self.seconds = defaultdict(float)
        self.stage_calls = Counter()
        self.stack = []
        self.rules = Counter()
        self.compilations = Counter()
        self.parses = Counter()
        self.mermaid = []
        self._patches = ExitStack()

    def wrap(self, owner, name, label=None, *, stage=False):
        original = getattr(owner, name)
        label = label or name
        def wrapped(*args, **kwargs):
            self.calls[label] += 1
            if "presentation" in self.stack:
                self.stage_calls[label] += 1
            if label == "compile" and args:
                graph = args[1] if len(args)>1 else kwargs.get("graph")
                self.compilations[id(graph)] += 1
            started = perf_counter()
            if label == 'svg_fragment':
                self.mermaid.append(args[0] if args else kwargs.get('mermaid_text',''))
            if stage:
                self.stack.append("presentation")
            try:
                result = original(*args, **kwargs)
                if label == "rule_plan":
                    invocations = {item.id:item for item in result.plan.invocations}
                    for key in result.executed:
                        invocation = invocations[key]
                        self.rules[(invocation.rule.id, invocation.rule.scope)] += 1
                return result
            finally:
                self.seconds[label] += perf_counter()-started
                if stage:
                    self.stack.pop()
        self._patches.enter_context(patch.object(owner, name, wrapped))

    def __enter__(self):
        from vibeflow.targets.python.quality import source_context, analysis_metrics, rule_adapter
        from vibeflow.targets.python.quality.workflow import validation, rule_phase
        from vibeflow.targets.python.project import resource_rules, compiler
        from vibeflow.tooling.application.python.project import declarations
        from vibeflow.tooling.application.python.presentation import architecture_document
        from vibeflow.tooling.application.python import workspace_service
        self.wrap(declarations, "_bind_node", "bind")
        self.wrap(declarations, "collect_workflow_source_context", "collect_sources")
        self.wrap(resource_rules, "review_reached_base_libs", "library_review")
        self.wrap(compiler.GraphCompiler, "compile_with_findings", "compile")
        self.wrap(analysis_metrics, "measure_tree", "measure")
        self.wrap(architecture_document, "build_architecture_document", "architecture", stage=True)
        from vibeflow.tooling.application.python.presentation import ascii_flowchart, mermaid
        from vibeflow.tooling.application.python.presentation.mermaid import review, review_svg, review_fragments
        for owner, name in ((ascii_flowchart,'export_ascii_flowchart'),(mermaid,'export_mermaid'),
                            (review,'render_review_columns'),(review_svg,'render_review_columns_svg')):
            if hasattr(owner, name):
                self.wrap(owner, name, name, stage=True)
        self.wrap(review_fragments, 'render_mermaid_svg', 'svg_fragment')
        self.wrap(workspace_service, "_environment_or_report", "environment")
        self.wrap(workspace_service, "_prepare_workspace_graph", "prepare")
        self.wrap(workspace_service, "_validate_prepared_workspace_graph", "health")
        for owner in (rule_adapter, resource_rules, rule_phase):
            self.wrap(owner, "execute_rule_plan", "rule_plan")
        for cls, name in ((source_context.PythonSourceFile,"tree"),(source_context.PythonSymbol,"node")):
            original = getattr(cls, name)
            def getter(instance, original=original, name=name):
                self.calls[name+"_reads"] += 1
                return original.fget(instance)
            self._patches.enter_context(patch.object(cls, name, property(getter)))
        original_copy = source_context.deepcopy
        def copying(value, *args, **kwargs):
            if isinstance(value, ast.AST):
                self.calls["ast_copy"] += 1
            return original_copy(value, *args, **kwargs)
        self._patches.enter_context(patch.object(source_context,"deepcopy",copying))
        original_parse = ast.parse
        def parse(*args, **kwargs):
            self.calls["parse"] += 1
            filename = kwargs.get('filename',args[1] if len(args)>1 else '<unknown>')
            self.parses[str(filename)] += 1
            return original_parse(*args, **kwargs)
        self._patches.enter_context(patch.object(ast,"parse",parse))
        return self

    def __exit__(self, *args):
        self._patches.close()

    def to_dict(self):
        return {"calls":dict(self.calls), "inclusive_seconds":dict(self.seconds),
                "presentation_calls":dict(self.stage_calls),
                "rules":[{"id":key[0],"scope":key[1],"executions":value} for key,value in sorted(self.rules.items())],
                "compiled_graphs":len(self.compilations),
                "parsing_counts":dict(sorted(self.parses.items())),
                "compilation_counts":sorted(self.compilations.values())}
