"""Target-neutral dependency identities before native Host implementation binding."""
from vibeflow.targets.javascript.frontend.errors import ProjectBuildError

def active_host_ids(enabled, *, catalog, planned=frozenset()):
    """Resolve only declarations and dependency identities, without binding code."""
    ordered, visiting = [], []
    complete = set()
    def visit(identifier):
        if identifier in complete:
            return
        if identifier in planned:
            raise ProjectBuildError("VF_AOT_HOST_EXTENSION_PLANNED_DEPENDENCY",
                f"implemented host_extension depends on planned host_extension '{identifier}'")
        if identifier in visiting:
            cycle = " -> ".join((*visiting[visiting.index(identifier):], identifier))
            raise ProjectBuildError("VF_AOT_HOST_EXTENSION_CYCLE", f"host_extension dependency cycle: {cycle}")
        descriptor = catalog.get(identifier)
        if descriptor is None:
            raise ProjectBuildError("VF_AOT_HOST_EXTENSION_UNKNOWN", f"unknown host_extension '{identifier}'")
        visiting.append(identifier)
        for dependency in descriptor.dependencies:
            visit(dependency)
        visiting.pop()
        complete.add(identifier)
        ordered.append(identifier)
    for identifier in enabled:
        visit(identifier)
    return tuple(ordered)
