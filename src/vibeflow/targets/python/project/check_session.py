"""Private, command-local source snapshots and review-result reuse.

A session belongs to one explicit check/run boundary. Its caches are discarded
at that boundary; a bare registry lookup never creates persistent eligibility.
"""
from contextlib import contextmanager
from vibeflow.targets.shared.facts import fact_key
from vibeflow.targets.python.project.fact_views import PythonFacts


class PythonCheckSession:
    def __init__(self, *, _parse_cache=None):
        self.parse_cache = {} if _parse_cache is None else _parse_cache
        self.parsed_sources = {}
        self.facts = PythonFacts()
        self.project_facts = {}
        self.rules = {}
        self.plans = {}
        self.library_sources = {}
        self.resource_sources = {}
        self.handlers = {}
        self.source_caches = {}
        self.node_import_results = {}
        self.call_effect_scopes = {}
        self.call_metrics = {}
        self.compilation = None
        self.compilation_input = None
        self.compilation_stages = {}
        self.sources = None

    def remember_compiler_stage(self, graph, compilation):
        for value in (graph, compilation.workflow.graph):
            self.compilation_stages[id(value)] = value, compilation

    def compiler_stage(self, graph):
        stage = self.compilation_stages.get(id(graph))
        return stage[1] if stage is not None and stage[0] is graph else None

    def checked_compilation(self, graph):
        if self.compilation is not None and (self.compilation_input is graph or self.compilation.workflow.graph is graph):
            return self.compilation
        return None

    @property
    def views(self):
        return self.facts.views

    def declarations(self, registry):
        return self.facts.declarations(registry)

    def snapshot(self, sources):
        return self.facts.snapshot(sources)

    def view(self, registry, sources, *, extra_facts=None):
        return self.facts.view(registry, sources, extra_facts=extra_facts)

    def source_cache(self, phase):
        return self.source_caches.setdefault(phase, {})

    def project_facts_for(self, view):
        return self.project_facts.setdefault(view.identity, {})

    def plan(self, selected, rules, rulesets, phase):
        from vibeflow.core.rules import compile_ruleset
        key = fact_key(selected), phase, tuple((key,id(value)) for key,value in rules.items()), tuple((key,id(value)) for key,value in rulesets.items())
        if key not in self.plans:
            self.plans[key] = compile_ruleset(selected, rules=rules, rulesets=rulesets, entrypoint=phase)
        return self.plans[key]

    def implementation_identity(self, plan, handlers):
        identities = []
        for invocation in plan.invocations:
            handler = handlers.get(invocation.rule.handler or invocation.rule.id,handlers.get(invocation.rule.id))
            key = id(handler)
            if key not in self.handlers:
                self.handlers[key] = handler, len(self.handlers) + 1
            identities.append((invocation.rule.id,self.handlers[key][1]))
        return tuple(identities)

    def clear(self):
        self.facts.store.clear()
        self.facts.views.clear()
        self.__init__()


def current_python_check(registry):
    return getattr(registry, "_python_check_session", None)


def begin_python_check(registry, *, _parse_cache=None):
    previous = current_python_check(registry)
    if previous is not None:
        previous.clear()
    if _parse_cache is None:
        prepared = getattr(registry, "prepared_resources", None)
        _parse_cache = getattr(prepared, "syntax_caches", {}).setdefault("python", {}) if prepared is not None else None
    session = PythonCheckSession(_parse_cache=_parse_cache)
    registry._python_check_session = session
    return session


def end_python_check(registry):
    session = current_python_check(registry)
    if session is not None:
        session.clear()
        del registry._python_check_session


@contextmanager
def python_check_scope(registry, *, _parse_cache=None):
    owned = current_python_check(registry) is None
    if owned:
        begin_python_check(registry, _parse_cache=_parse_cache)
    try:
        yield
    finally:
        if owned:
            end_python_check(registry)
