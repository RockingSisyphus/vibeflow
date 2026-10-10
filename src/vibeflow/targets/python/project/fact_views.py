"""Python declaration and source adapters for the shared fact-view store."""
from vibeflow.core.rules.models import plain, readonly
from vibeflow.targets.shared.facts import FactStore, fact_key, stable_facts
from vibeflow.targets.python.quality.source_context import PythonSourceContext, PythonSourceFile


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


class PythonFacts:
    def __init__(self):
        self.store = FactStore("python", opaque_types=(PythonSourceContext, PythonSourceFile))
        self.source_snapshots = {}
        self.contributions = {}
        self.catalog_snapshots = {}
        self.views = {}

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
                "calls":[(item.owner,item.node_id,item.type_key,plain(item.params),item.source_path,item.local_id,item.call_path,plain(item.rulesets)) for item in sources.calls],
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
        additions_key = fact_key(additions,opaque_types=self.store.opaque_types) if stable_facts(additions,opaque_types=self.store.opaque_types) else object()
        key = declarations_key, snapshot, id(sources), additions_key
        if key not in self.views:
            facts = {**declarations, "source_context":sources, **additions}
            self.views[key] = self.store.capture(facts, key=key, scope={"files":tuple(item.path for item in sources.files),
                "workflows":tuple(sorted({call.owner for call in sources.calls}))})
        return self.views[key]
