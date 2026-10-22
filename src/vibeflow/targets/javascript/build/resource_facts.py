"""JavaScript source attribution for resource Rules; no permission decisions."""
from pathlib import Path

from vibeflow.targets.javascript.resources.identity import business_import_sites

from vibeflow.targets.javascript.build.toolchain import run_quality_facts_driver
from vibeflow.targets.shared.quality_support.resource_imports import implementation_import_scopes


def resource_import_facts(workspace, root, prepared, owners, *, syntax_cache, node_command):
    paths = {item["path"] for item in owners}
    paths.update(path for package in prepared.packages for path in package["source_paths"])
    paths = sorted(path for path in paths if Path(path).is_file() and Path(path).is_relative_to(workspace.root)
                   and Path(path).suffix in {".js", ".mjs", ".cjs", ".ts", ".mts", ".cts", ".tsx", ".jsx"})
    if not paths:
        return {"owners": owners, "imports": ()}
    requests = [{**item, "export": item["symbol"]} for item in owners if item["path"] in paths]
    key = ("resource_import_facts", str(root.path), tuple((path, Path(path).stat().st_mtime_ns, Path(path).stat().st_size) for path in paths),
           tuple((item["kind"], item["id"], item["path"], item["symbol"], item["role"]) for item in owners))
    measured = syntax_cache.get(key)
    if measured is None:
        measured = run_quality_facts_driver({"qualityRoot": str(workspace.root), "qualityFiles": paths,
        "qualityImplementations": requests}, package_root=root.path / root.project_config.get("javascript", {}).get("package_root", "."),
            node_command=node_command)
        syntax_cache[key] = measured
    projections = [{**item, "path": str((workspace.root / item["path"]).resolve())} for item in measured.implementations]
    scopes = implementation_import_scopes(({"owners": owners},), projections)
    edges = tuple({"path": str((workspace.root / file["path"]).resolve()), "target": str(Path(site["resolved_path"]).resolve()), "line": site["line"], "column": site["column"], "symbols": tuple(site.get("symbols", ()))}
        for file, site in business_import_sites(measured.files) if Path(site["resolved_path"]).is_relative_to(workspace.root) and "node_modules" not in Path(site["resolved_path"]).parts)
    return {"owners": tuple(scopes[0]["owners"]), "imports": edges}
