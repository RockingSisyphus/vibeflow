from __future__ import annotations

from collections.abc import Mapping, Sequence

from .models import (
    QualityFinding,
    QualityThresholds,
)


def dependency_findings(
    graph: Mapping[str, Sequence[str]],
    import_sites_by_edge: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
    thresholds: QualityThresholds,
) -> tuple[list[QualityFinding], list[str]]:
    findings: list[QualityFinding] = []
    longest = _longest_acyclic_chain(graph)
    if len(longest) > thresholds.max_dependency_chain:
        edge_import_sites = _path_edge_import_sites(
            longest,
            import_sites_by_edge,
        )
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CHAIN_TOO_DEEP",
                "error",
                "dependency_chain",
                " -> ".join(longest),
                f"dependency chain length is {len(longest)}",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="split_module",
                details={
                    "chain": longest,
                    "edge_import_sites": edge_import_sites,
                },
            )
        )
    elif len(longest) >= thresholds.warn_dependency_chain:
        edge_import_sites = _path_edge_import_sites(
            longest,
            import_sites_by_edge,
        )
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CHAIN_WARN",
                "warning",
                "dependency_chain",
                " -> ".join(longest),
                f"dependency chain length is {len(longest)}",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="split_module",
                details={
                    "chain": longest,
                    "edge_import_sites": edge_import_sites,
                },
            )
        )

    for cycle in _cycles(graph):
        edge_import_sites = _path_edge_import_sites(cycle, import_sites_by_edge)
        findings.append(
            QualityFinding(
                "QUALITY.DEPENDENCY.CYCLE",
                "error",
                "dependency_cycle",
                " -> ".join(cycle),
                "module import cycle detected",
                source_location=_first_import_site_location(edge_import_sites),
                suggested_fix_type="break_dependency",
                details={
                    "cycle": cycle,
                    "edge_import_sites": edge_import_sites,
                },
            )
        )
    findings.extend(_bidirectional_findings(graph, import_sites_by_edge))
    return findings, longest


def _bidirectional_findings(
    graph: Mapping[str, Sequence[str]],
    import_sites_by_edge: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    for source, targets in graph.items():
        for target in targets:
            if source not in graph.get(target, ()) or source >= target:
                continue
            forward = list(import_sites_by_edge.get((source, target), ()))
            reverse = list(import_sites_by_edge.get((target, source), ()))
            edge_sites = [
                {
                    "source": source,
                    "target": target,
                    "import_sites": forward,
                }
            ]
            findings.append(
                QualityFinding(
                    "QUALITY.DEPENDENCY.BIDIRECTIONAL",
                    "error",
                    "dependency_pair",
                    f"{source} <-> {target}",
                    "bidirectional module dependency detected",
                    source_location=_first_import_site_location(edge_sites),
                    suggested_fix_type="break_dependency",
                    details={
                        "source": source,
                        "target": target,
                        "forward_import_sites": forward,
                        "reverse_import_sites": reverse,
                    },
                )
            )
    return findings


def _path_edge_import_sites(
    path: Sequence[str],
    import_sites_by_edge: Mapping[
        tuple[str, str], Sequence[Mapping[str, object]]
    ],
) -> list[dict[str, object]]:
    return [
        {
            "source": source,
            "target": target,
            "import_sites": list(import_sites_by_edge.get((source, target), ())),
        }
        for source, target in zip(path, path[1:])
    ]


def _first_import_site_location(
    edge_import_sites: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    for edge in edge_import_sites:
        sites = edge.get("import_sites")
        if not isinstance(sites, Sequence):
            continue
        for site in sites:
            if not isinstance(site, Mapping):
                continue
            path = str(site.get("path", "")).strip()
            if not path:
                continue
            location: dict[str, object] = {"path": path}
            if site.get("line"):
                location["line"] = site["line"]
            if site.get("column"):
                location["column"] = site["column"]
            return location
    return {}


def _longest_acyclic_chain(
    graph: Mapping[str, Sequence[str]],
) -> list[str]:
    best: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        nonlocal best
        if node in path:
            return
        next_path = [*path, node]
        if len(next_path) > len(best):
            best = next_path
        for target in graph.get(node, ()):
            visit(target, next_path)

    for node in graph:
        visit(node, [])
    return best


def _cycles(graph: Mapping[str, Sequence[str]]) -> list[list[str]]:
    found: set[tuple[str, ...]] = set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            found.add(tuple(cycle))
            return
        for target in graph.get(node, ()):
            visit(target, [*path, node])

    for node in graph:
        visit(node, [])
    return [list(cycle) for cycle in sorted(found)]


__all__ = ["dependency_findings"]
