"""JavaScript Application adapter for fixed plugin bootstrap."""
from vibeflow.targets.javascript.sdk.loading import load_plugin


def attach_definitions(catalog, definitions):
    from vibeflow.targets.javascript.sdk.loading import attach_catalog
    attach_catalog(catalog, definitions)


def load_plugin_definition(source, *, owner, workspace, node_command, loading_context=None):
    return load_plugin(source, root=owner.path, project_config=owner.project_config, node_command=node_command,
                       toolchain_root=getattr(owner, "toolchain_root", None))

def load_builtin_definition():
    from vibeflow.targets.javascript.rules.plugin import builtin_plugin
    return builtin_plugin()


def plugin_source_paths(definition, contribution, *, owner, workspace, package, node_command, syntax_cache=None):
    """The bootstrap bundle already records imports; inspect delayed code once."""
    from pathlib import Path
    from vibeflow.targets.javascript.build.toolchain import run_quality_facts_driver
    from vibeflow.core.descriptors.source_bundle import implementation_sources
    for entry in contribution.resources:
        for implementation in getattr(entry.descriptor, "implementations", ()):
            if implementation.source.kind != "file":
                raise ValueError("JavaScript Plugin implementations must identify their package-owned source file")
    states = definition.load_states
    paths = set(states)
    delayed = any(locator.kind == "file" and states.get(locator.ref) not in {"loaded", "unknown"}
        for entry in contribution.resources for implementation in getattr(entry.descriptor, "implementations", ())
        for _, locator in implementation_sources(implementation))
    if delayed:
        files = [str(path) for path in package.rglob("*") if path.is_file()
                 and path.suffix in {".ts", ".js", ".mts", ".cts", ".mjs", ".cjs", ".tsx", ".jsx"}
                 and "node_modules" not in path.relative_to(package).parts]
        package_root = (getattr(owner, "toolchain_root", None) or owner.path) / owner.project_config.get("javascript", {}).get("package_root", ".")
        facts = run_quality_facts_driver({"qualityRoot":str(owner.path), "qualityFiles":files},
            package_root=package_root, node_command=node_command)
        paths.update(site["resolved_path"] for file in facts.files for site in file["import_sites"]
                     if site.get("resolved_path"))
    return paths
