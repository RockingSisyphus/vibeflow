from __future__ import annotations

import ast
from pathlib import Path
from typing import Mapping

from .code_quality_types import ImportSite

def _collect_import_sites(module: str, rel_path: str, tree: ast.AST) -> tuple[ImportSite, ...]:
    sites: list[ImportSite] = []
    for node in getattr(tree, "body", ()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                sites.append(
                    ImportSite(
                        source_module=module,
                        imported=alias.name,
                        raw_import=f"import {alias.name}",
                        path=rel_path,
                        line=getattr(node, "lineno", 1),
                        column=getattr(node, "col_offset", 0) + 1,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_relative_import(module, node.module, node.level) if node.level else node.module
            if base:
                sites.append(
                    ImportSite(
                        source_module=module,
                        imported=base,
                        raw_import=_raw_import_from(node),
                        path=rel_path,
                        line=getattr(node, "lineno", 1),
                        column=getattr(node, "col_offset", 0) + 1,
                    )
                )
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    sites.append(
                        ImportSite(
                            source_module=module,
                            imported=f"{base}.{alias.name}",
                            raw_import=_raw_import_from(node, alias.name),
                            path=rel_path,
                            line=getattr(node, "lineno", 1),
                            column=getattr(node, "col_offset", 0) + 1,
                        )
                    )
    deduped = {(site.imported, site.raw_import, site.line, site.column): site for site in sites}
    return tuple(deduped[key] for key in sorted(deduped))

def _raw_import_from(node: ast.ImportFrom, alias_name: str | None = None) -> str:
    dots = "." * int(getattr(node, "level", 0) or 0)
    module = getattr(node, "module", None) or ""
    imported = alias_name or ", ".join(alias.name for alias in node.names)
    return f"from {dots}{module} import {imported}".strip()

def _build_dependency_graph(files: Sequence[FileQuality], modules: set[str]) -> dict[str, tuple[str, ...]]:
    graph: dict[str, tuple[str, ...]] = {}
    for file in files:
        resolved = set()
        for imported in file.imports:
            candidate = _resolve_internal_import(imported, modules)
            if candidate and candidate != file.module:
                resolved.add(candidate)
        graph[file.module] = tuple(sorted(resolved))
    return graph

def _import_sites_by_edge(
    files: Sequence[FileQuality],
    modules: set[str],
) -> dict[tuple[str, str], tuple[dict[str, object], ...]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for file in files:
        for site in file.import_sites:
            target = _resolve_internal_import(site.imported, modules)
            if not target or target == file.module:
                continue
            row = site.to_dict()
            row["target_module"] = target
            grouped.setdefault((file.module, target), []).append(row)
    return {edge: tuple(rows) for edge, rows in grouped.items()}

def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) or path.stem

def _resolve_relative_import(module: str, imported: str | None, level: int) -> str | None:
    parts = module.split(".")
    base = parts[: max(0, len(parts) - level)]
    if imported:
        base.extend(imported.split("."))
    return ".".join(part for part in base if part)

def _resolve_internal_import(imported: str, modules: set[str]) -> str | None:
    if imported in modules:
        return imported
    parts = imported.split(".")
    while len(parts) > 1:
        parts.pop()
        candidate = ".".join(parts)
        if candidate in modules:
            return candidate
    return None
