"""Private, command-local source snapshots and review-result reuse.

A session belongs to one explicit check/run boundary. Its caches are discarded
at that boundary; a bare registry lookup never creates persistent eligibility.
"""
from dataclasses import dataclass, field, fields, is_dataclass
import json

from vibeflow.core.rules import RuleContext
from vibeflow.core.rules.models import plain, readonly


def fact_key(value):
    """Include portable data and retain the identity of opaque Target services."""
    from collections.abc import Mapping
    memo = {}
    def encode(item):
        if item is None or type(item) in {str,bool,int,float}:
            return item
        if id(item) in memo:
            return ["ref",memo[id(item)]]
        memo[id(item)] = len(memo)
        if isinstance(item,Mapping):
            return ["mapping",[(encode(key),encode(value)) for key,value in item.items()]]
        if isinstance(item,(tuple,list)):
            return ["sequence",[encode(value) for value in item]]
        if isinstance(item,(set,frozenset)):
            return ["set",[encode(value) for value in sorted(item,key=str)]]
        if is_dataclass(item) and not isinstance(item,type):
            return ["dataclass",type(item).__module__,type(item).__qualname__,id(type(item)),
                    [(value.name,encode(getattr(item,value.name))) for value in fields(item)]]
        return f"{type(item).__module__}.{type(item).__qualname__}@{id(item)}"
    return json.dumps(encode(value), sort_keys=True, allow_nan=False)


def stable_facts(value, active=None, memo=None):
    """Unknown extra objects may change without changing their Python identity."""
    from collections.abc import Mapping
    from vibeflow.targets.python.quality.source_context import PythonSourceContext, PythonSourceFile
    if value is None or type(value) in {str,bool,int,float}:
        return True
    if isinstance(value,(PythonSourceContext,PythonSourceFile)):
        return True
    active = set() if active is None else active
    memo = {} if memo is None else memo
    if id(value) in memo:
        return memo[id(value)]
    if id(value) in active:
        return False
    active.add(id(value))
    try:
        if isinstance(value,Mapping):
            stable = all(stable_facts(key,active,memo) and stable_facts(item,active,memo) for key,item in value.items())
        elif isinstance(value,(tuple,list,set,frozenset)):
            stable = all(stable_facts(item,active,memo) for item in value)
        elif is_dataclass(value) and not isinstance(value,type):
            stable = all(stable_facts(getattr(value,item.name),active,memo) for item in fields(value))
        else:
            stable = False
        memo[id(value)] = stable
        return stable
    finally:
        active.remove(id(value))


def catalog_key(registry):
    catalogs = tuple(getattr(registry, "rule_catalogs", ()) or ())
    resources = tuple((id(catalog), tuple((group, tuple(id(item) for item in (getattr(catalog, group, ()) or ())))
                      for group in ("nodes", "rules", "rulesets", "base_libs", "plugins", "host_extensions")))
                      for catalog in catalogs)
    loaded = getattr(getattr(registry, "loaded_plugins", None), "catalogs", None)
    settings = (getattr(loaded, "plugin_settings", {}), getattr(loaded, "plugin_records", ()))
    available = registry.available() if callable(getattr(registry,"available",None)) else ()
    descriptors = tuple((key, id(registry.descriptor(key))) for key in available)
    roots = tuple(map(str, getattr(registry, "source_roots", ())))
    return resources, descriptors, roots, fact_key(settings)


@dataclass
class PythonCheckView:
    token: int
    sources: object
    facts: object
    snapshot: str
    contexts: dict = field(default_factory=dict)
    source_caches: dict = field(default_factory=dict)
    project_facts: dict = field(default_factory=dict)
    _base: object = field(init=False,repr=False)

    def __post_init__(self):
        self._base = RuleContext(facts=self.facts,
            scope={"files":tuple(item.path for item in self.sources.files),
                   "workflows":tuple(sorted({call.owner for call in self.sources.calls}))},target="python")
        self.facts = self._base.facts

    def context(self, phase):
        if phase not in self.contexts:
            from dataclasses import replace
            self.contexts[phase] = replace(self._base,phase=phase)
        return self.contexts[phase]

    def source_cache(self, phase):
        return self.source_caches.setdefault(phase, {})


class PythonCheckSession:
    def __init__(self, *, _parse_cache=None):
        self.parse_cache = {} if _parse_cache is None else _parse_cache
        self.parsed_sources = {}
        self.source_snapshots = {}
        self.contributions = {}
        self.catalog_snapshots = {}
        self.views = {}
        self.rules = {}
        self.plans = {}
        self.library_sources = {}
        self.resource_sources = {}
        self.handlers = {}
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

    def declarations(self, registry):
        key = catalog_key(registry)
        if key not in self.contributions:
            from vibeflow.core.descriptors.contributions import contribution_facts
            from vibeflow.targets.python.project.source_membership import source_ownership
            loaded = getattr(getattr(registry, "loaded_plugins", None), "catalogs", None)
            self.catalog_snapshots[key] = tuple(tuple(getattr(catalog,group,()) or ())
                for catalog in (getattr(registry,"rule_catalogs",()) or ())
                for group in ("nodes","rules","rulesets","base_libs","plugins","host_extensions"))
            self.contributions[key] = readonly({
                **(contribution_facts(loaded) if loaded is not None else {}),
                **source_ownership(registry),
                "node_catalog":tuple(registry.descriptor(item) for item in registry.available())
                    if callable(getattr(registry,"available",None)) else ()})
        return key, self.contributions[key]

    def snapshot(self, sources):
        key = id(sources)
        previous = self.source_snapshots.get(key)
        if previous is None or previous[0] is not sources:
            import hashlib
            facts = {"files":[(item.path,item.module,item.root_id,item.text) for item in sources.files],
                "calls":[(item.owner,item.node_id,item.type_key,plain(item.params),item.source_path,item.local_id,item.call_path) for item in sources.calls],
                "imports":[(item.path,item.specifier,item.module,item.resolved_path,item.symbol,item.alias,item.line,item.column) for item in sources.imports],
                "nodes":[(item.descriptor.to_dict(),item.path,item.symbol,item.root_id,item.calls) for item in sources.nodes]}
            previous = (sources, hashlib.sha256(fact_key(facts).encode()).hexdigest())
            self.source_snapshots[key] = previous
        return previous[1]

    def view(self, registry, sources, *, extra_facts=None):
        declarations_key, declarations = self.declarations(registry)
        snapshot = self.snapshot(sources)
        # Source rules can read plugin settings and actual source load state.
        # Keep those views distinct instead of extending the Core cache contract.
        additions = {"source_load_states":getattr(registry, "source_load_states", {}), **dict(extra_facts or {})}
        additions_key = fact_key(additions) if stable_facts(additions) else object()
        key = declarations_key, snapshot, id(sources), additions_key
        if key not in self.views:
            facts = {**declarations, "source_context":sources, **additions}
            self.views[key] = PythonCheckView(len(self.views) + 1, sources, facts, snapshot)
        return self.views[key]

    def plan(self, selected, rules, rulesets, phase):
        from vibeflow.core.rules import compile_ruleset
        key = selected, phase, tuple((key,id(value)) for key,value in rules.items()), tuple((key,id(value)) for key,value in rulesets.items())
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
        self.__init__()


def current_python_check(registry):
    return getattr(registry, "_python_check_session", None)


def begin_python_check(registry, *, _parse_cache=None):
    previous = current_python_check(registry)
    if previous is not None:
        previous.clear()
    session = PythonCheckSession(_parse_cache=_parse_cache)
    registry._python_check_session = session
    return session


def end_python_check(registry):
    session = current_python_check(registry)
    if session is not None:
        session.clear()
        del registry._python_check_session
