from __future__ import annotations

from collections.abc import Mapping, Sequence


def strongly_connected_components(adjacency: Mapping[str, Sequence[str]]) -> list[tuple[str, ...]]:
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    on_stack: set[str] = set()
    components: list[tuple[str, ...]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency.get(node, ()):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])
        if lowlinks[node] != indices[node]:
            return
        component: list[str] = []
        while True:
            item = stack.pop()
            on_stack.remove(item)
            component.append(item)
            if item == node:
                break
        components.append(tuple(component))

    for node in sorted(adjacency):
        if node not in indices:
            visit(node)
    return components
