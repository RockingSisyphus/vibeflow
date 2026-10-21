"""Load fixed JS/TS definitions through the existing Target worker."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import weakref
import atexit

from vibeflow.core.descriptors.contributions import PluginContributions, ResourceDeclaration, ResourceOrigin, ResourceOwner
from vibeflow.core.descriptors.decode import decode_resource
from vibeflow.targets.javascript.build.plugin_session import JavascriptPluginSession


@dataclass(frozen=True)
class JavascriptPluginDefinition:
    id: str
    resources: tuple
    config_schema: Any
    config_defaults: Any
    source: str
    load_states: Any
    session: Any
    declaration: Any = None
    _fixed_contributions: PluginContributions = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        resources = tuple(ResourceDeclaration(descriptor,
            ResourceOrigin(ResourceOwner("plugin", self.id), location.get("path", self.source), location.get("line"),
                           location.get("column"), location.get("symbol", "")))
            for descriptor, location in self.resources)
        object.__setattr__(self, "_fixed_contributions", PluginContributions(
            self.id, resources, source=self.source, declaration=self.declaration or {}))

    def contributions(self, config=None):
        return self._fixed_contributions._with_config(config)

    def close(self):
        self.session.__exit__(None, None, None)


_definitions = {}


def attach_catalog(catalog, definitions):
    """Target-owned callable handles live for exactly this Catalog's lifetime."""
    key = id(catalog)
    _definitions[key] = tuple(definitions)
    weakref.finalize(catalog, _release_catalog, key)


def _release_catalog(key):
    errors = []
    for definition in _definitions.pop(key, ()):
        try:
            definition.close()
        except Exception as error:
            errors.append(error)
    from vibeflow.targets.javascript.build.cleanup import finish_cleanup
    finish_cleanup(None, errors)


def contribution_session(catalog, group, resource_id):
    origin = catalog.origins.get((group, resource_id))
    if origin is None:
        return None
    return next((definition.session for definition in _definitions.get(id(catalog), ())
                 if definition.id == origin.owner.plugin_id), None)


@atexit.register
def _close_definitions():
    errors = []
    for key in tuple(_definitions):
        try:
            _release_catalog(key)
        except Exception as error:
            errors.append(error)
    from vibeflow.targets.javascript.build.cleanup import finish_cleanup
    finish_cleanup(None, errors)


def load_plugin(source, *, root, project_config, node_command="node", toolchain_root=None):
    javascript = project_config.get("javascript", {})
    package_root = (Path(toolchain_root or root) / javascript.get("package_root", ".")).resolve()
    if source.kind == "file":
        module = (Path(root) / source.ref).resolve()
    elif source.kind in {"module", "package"}:
        import subprocess
        script = """
import {fileURLToPath} from "node:url";
import {createRequire} from "node:module";
import {statSync} from "node:fs";
let entry;
try {
  entry = fileURLToPath(import.meta.resolve(process.argv[1]));
  if (!statSync(entry).isFile()) throw new Error("module entry is a directory");
} catch {
  entry = createRequire(import.meta.url).resolve(process.argv[1]);
}
process.stdout.write(entry);
"""
        result = subprocess.run([node_command, "--input-type=module", "-e", script, source.ref], cwd=package_root, capture_output=True, text=True, check=True)
        module = Path(result.stdout)
    else:
        raise ValueError("plugin source must be a file, module or package")
    session = JavascriptPluginSession(node_command=node_command).__enter__()
    try:
        result = session.declarations(module=module, package_root=package_root, export=source.export or "plugin")
    except Exception as exc:
        session.__exit__(type(exc), exc, exc.__traceback__)
        from vibeflow.targets.javascript.frontend.plugin_descriptors import JavascriptPluginError
        if getattr(exc,"code","") in {"DESCRIPTOR.INVALID", "RESOURCE.IMPLEMENTATION.CONFLICT"}:
            exc.location = dict(exc.details.get("location", {}))
            raise
        raise JavascriptPluginError("PLUGIN.DECLARATION.LOAD", f"could not load fixed plugin {module}: {exc}", details=getattr(exc,"details",{})) from exc
    resources = []
    for item in result["resources"]:
        location = item.get("origin", {})
        try:
            descriptor = decode_resource(item["descriptor"])
        except ValueError as error:
            session.__exit__(type(error), error, error.__traceback__)
            error.location = location
            raise
        resources.append((descriptor, location))
    resources = tuple(resources)
    states = {str(path):"unknown" for path in result.get("included_sources", ())}
    states.update({str(path):"loaded" for path in result.get("loaded_sources", ())})
    for descriptor,_ in resources:
        for implementation in getattr(descriptor,"implementations",()):
            for member in getattr(implementation,"implementation_files",()):
                if member.ref.endswith((".d.ts",".d.mts",".d.cts")):
                    states[member.ref]="not_loaded"
    try:
        return JavascriptPluginDefinition(result["id"], resources, result.get("config_schema", {}),
                                          result.get("config_defaults", {}), str(module), states, session, result.get("declaration", {}))
    except Exception as exc:
        session.__exit__(type(exc), exc, exc.__traceback__)
        raise


def discover_resources(directory, *, project_config, package_root, node_command="node"):
    """Read exported ordinary SDK resources without manufacturing a Plugin."""
    from vibeflow.core.descriptors.declarations import ResourceDefinition, ResourceDiscovery
    from vibeflow.core.descriptors.contributions import resource_kind
    package_root = (Path(package_root) / project_config.get("javascript", {}).get("package_root", ".")).resolve()
    found, states = [], {}
    candidates = [(path, kind) for group, kind in (("nodes", "node"), ("base_lib", "base_lib"))
                  for path in sorted((Path(directory) / group).rglob("*"))
                  if path.is_file() and path.suffix in {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts"}
                  and not path.name.endswith((".d.ts", ".d.mts", ".d.cts"))]
    if not candidates:
        return ResourceDiscovery()
    with JavascriptPluginSession(node_command=node_command) as session:
        for path, kind in candidates:
            result = session.resource_declarations(module=path.resolve(), package_root=package_root)
            states.update({path:"unknown" for path in result.get("included_sources", ())})
            states.update({path:"loaded" for path in result.get("loaded_sources", ())})
            for item in result["resources"]:
                try:
                    descriptor = decode_resource(item["descriptor"])
                except ValueError as error:
                    error.location=dict(item['origin'])
                    raise
                if resource_kind(descriptor) != kind:
                    raise ValueError(f"{path}: declarations under {path.parent.name}/ must be {kind} resources")
                origin = item["origin"]
                found.append(ResourceDefinition(descriptor, path=origin["path"], line=origin.get("line"),
                                                symbol=origin.get("symbol", "")))
    return ResourceDiscovery(tuple(found), states)
