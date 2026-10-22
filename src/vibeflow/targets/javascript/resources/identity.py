"""Identity of the exact framework files provided to one JavaScript worker.

This is source provenance, not a permission policy. Raw analysis retains its
imports; business-resource projections omit only positively identified SDK files.
"""
from pathlib import Path
from types import MappingProxyType


class FrameworkResources:
    def __init__(self, directory):
        from . import RESOURCE_NAMES
        self._files = MappingProxyType({str((Path(directory) / name).resolve()):
            "javascript/" + name for name in RESOURCE_NAMES})

    def identify(self, path):
        return self._files.get(str(Path(path).resolve()), "") if path else ""

    def annotate_analysis(self, payload):
        """Attach identities before this worker's materialized files disappear."""
        if not isinstance(payload, dict):
            return payload  # Existing driver protocol validation owns malformed results.
        quality = payload.get("quality")
        rules = payload.get("rules")
        for result in (quality, rules.get("local_quality") if isinstance(rules, dict) else None):
            if not isinstance(result, dict):
                continue
            for file in result.get("files", ()):
                for site in file.get("import_sites", ()):
                    site["framework_resource"] = self.identify(site.get("resolved_path"))
        return payload

    def imported_framework_files(self, paths):
        return tuple(path for path in paths if self.identify(path))


def business_source_states(declarations):
    """Project the worker's raw load evidence into business source membership."""
    internal = frozenset(declarations["framework_sources"])
    states = {str(path): "unknown" for path in declarations.get("included_sources", ()) if path not in internal}
    states.update({str(path): "loaded" for path in declarations.get("loaded_sources", ()) if path not in internal})
    return states


def business_import_sites(files):
    """Keep project/external imports; raw facts still contain framework imports."""
    for file in files:
        for site in file["import_sites"]:
            if site.get("resolved_path") and not site.get("framework_resource"):
                yield file, site
