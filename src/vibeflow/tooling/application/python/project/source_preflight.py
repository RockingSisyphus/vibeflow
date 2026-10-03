"""Composition adapter for Python source closure facts and selected preflight."""
from pathlib import Path
from vibeflow.targets.python.project.source_closure import collect_python_source_facts, resolve_local_module_path
from vibeflow.targets.python.quality.source_analysis.preflight import preflight_python_source_facts


def preflight_python_import_tree(entry_path: Path, *, project_root=None, source_roots=()):
    path = entry_path.resolve()
    facts = collect_python_source_facts(path, project_root=project_root, source_roots=source_roots)
    preflight_python_source_facts(str(path), facts)


__all__ = ["collect_python_source_facts", "resolve_local_module_path", "preflight_python_import_tree"]
