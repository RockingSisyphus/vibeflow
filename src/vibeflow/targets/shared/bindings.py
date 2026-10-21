"""Command-local native implementations, separate from portable Catalog data."""
from types import MappingProxyType
import weakref

from vibeflow.core.descriptors.contributions import RESOURCE_GROUPS


_BINDINGS = {}


def attach_native_bindings(catalog, definitions):
    """Keep contributed callable identities for exactly this Catalog's lifetime."""
    bindings = {}
    for definition in definitions:
        if hasattr(definition, "bindings"):
            for key, value in definition.bindings().items():
                bindings[(definition.id, *key)] = value
    key = id(catalog)
    _BINDINGS[key] = MappingProxyType(bindings)
    weakref.finalize(catalog, _BINDINGS.pop, key, None)


def native_binding(catalog, kind, resource_id):
    """Resolve implementation provenance without a built-in resource-ID branch."""
    group = RESOURCE_GROUPS[kind]
    seen = set()
    while resource_id not in seen:
        seen.add(resource_id)
        origin = catalog.origins.get((group, resource_id))
        if origin is not None:
            binding = _BINDINGS.get(id(catalog), {}).get((origin.owner.plugin_id, kind, resource_id))
            if binding is not None:
                return binding
        descriptor = getattr(catalog, group).get(resource_id)
        resource_id = getattr(descriptor, "handler", "")
        if not resource_id:
            return None
    return None
