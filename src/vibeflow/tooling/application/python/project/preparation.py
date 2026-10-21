"""Python declaration, source-fact and governance binding preparation."""
from contextlib import contextmanager
from pathlib import Path


def discover_resources(directory, *, root, workspace, node_command, syntax_cache, loading_context=None):
    from vibeflow.targets.python.sdk.discovery import discover_resources as discover
    return discover(directory, source_roots=tuple(path for path in (root.path, workspace.root) if Path(directory).is_relative_to(path)),
        syntax_cache=syntax_cache, namespaces=loading_context)


def normalize_resource(declaration, implementation, *, directory, root, workspace):
    from vibeflow.targets.python.sdk.identity import normalize_resource as normalize
    return normalize(declaration, implementation, root=directory, source_roots=(root.path, workspace.root)).descriptor


def source_analysis(workspace, root, workflows, *, node_command, syntax_cache):
    from vibeflow.tooling.application.python.project.source_files import collect_root_source_facts
    from vibeflow.tooling.project.source_governance import root_resource_scopes
    from vibeflow.targets.python.project.structure_sources import python_import_scopes
    facts = collect_root_source_facts(root.path, parse_cache=syntax_cache)
    scopes = root_resource_scopes(workspace, root, workflows, facts.files)
    from vibeflow.tooling.project.source_governance import private_root_imports
    imports = _source_imports((root.path / file.path for file in facts.files), (root.path, workspace.root), syntax_cache)
    return facts, python_import_scopes(scopes, root.path, syntax_cache), private_root_imports(workspace, root, imports)


def shared_imports(workspace, root, *, node_command, syntax_cache):
    from vibeflow.tooling.application.python.project.source_files import _iter_python_files, DEFAULT_EXCLUDED_DIRS
    from vibeflow.tooling.project.source_governance import private_root_imports
    shared = (path for name in ("nodes", "base_lib", "plugins")
              for path in _iter_python_files(workspace.root / name, set(DEFAULT_EXCLUDED_DIRS)))
    return private_root_imports(workspace, root, _source_imports(shared, (workspace.root,), syntax_cache))


def _source_imports(paths, source_roots, syntax_cache):
    import ast
    from vibeflow.targets.python.quality.parse_cache import parse_python_source
    from vibeflow.targets.python.project.source_closure import _resolve_local_imports
    imports = []
    for path in paths:
        try:
            tree = parse_python_source(path, path.read_text(encoding="utf-8"), syntax_cache)
        except SyntaxError:
            continue
        for statement in ast.walk(tree):
            if isinstance(statement, (ast.Import, ast.ImportFrom)):
                for target in _resolve_local_imports(statement, current_path=path, source_roots=source_roots):
                    imports.append((path, target, statement.lineno))
    return imports


def review_workflow(workspace, path, *, preparation, governance):
    from vibeflow.tooling.application.python.project.core import build_workspace_environment
    from vibeflow.tooling.application.python.workspace_service import validate_workspace_config_path
    environment = build_workspace_environment(workspace, path, preparation=preparation, governance=governance)
    return validate_workspace_config_path(path, workspace=workspace, environment=environment).to_dict()


@contextmanager
def governance_handlers(catalogs, rules, *, target_root, node_command):
    from vibeflow.targets.python.sdk.loading import source_paths
    from vibeflow.targets.python.sdk.source_namespace import source_namespace
    namespaces, handlers = {}, {}
    for rule in rules:
        source = next(item.source for item in rule.implementations if item.language == "python")
        if source.kind != "file":
            raise ValueError(f"governance Rule '{rule.id}' must identify its implementation file")
        owner = catalogs.origins[("rules",rule.id)].owner
        directory = Path(owner.path)
        source_namespace(directory, namespaces=namespaces)
        namespace = namespaces[directory]
        with source_paths(catalogs.source_roots):
            callback = namespace.load(Path(source.ref))
            for member in source.export.split("."):
                callback = getattr(callback, member)
        handlers[rule.id] = callback
    yield handlers
