"""Prove exclusivity of deliveries from their complete scheduling paths.

Conditions belong to an emitting node and output key, not to a key globally.
Unknown expressions, cycles and oversized path sets never prove exclusivity.
"""
from collections import deque

from vibeflow.targets.shared.quality_support.workflow_rules.helpers import _parse_when


class BranchPaths:
    _MAX_PATHS = 128

    def __init__(self, graph, compiled):
        self.incoming = {node.name: [] for node in graph.nodes}
        outgoing = {node.name: [] for node in graph.nodes}
        self.transfers = tuple(compiled.resolved_transfer_edges)
        for edge in compiled.resolved_schedule_edges:
            self.incoming[edge.target].append(edge)
            outgoing[edge.source].append(edge.target)
        pending = {name: len(edges) for name, edges in self.incoming.items()}
        ready = deque(name for name, count in pending.items() if not count)
        self.paths = {}
        while ready:
            name = ready.popleft()
            self.paths[name] = self._paths(name)
            for target in outgoing[name]:
                pending[target] -= 1
                if not pending[target]:
                    ready.append(target)
        # Cycles and descendants of cycles stay unknown. Never combine facts
        # from different executions of a decision into an exclusivity proof.

    def _paths(self, name):
        incoming = self.incoming.get(name, ())
        if not incoming:
            return ((),)
        paths = []
        for edge in incoming:
            alternatives = self.deliveries(edge)
            if alternatives is None:
                return None
            for path in alternatives:
                if path not in paths:
                    paths.append(path)
                if len(paths) > self._MAX_PATHS:
                    return None
        return tuple(paths)

    def deliveries(self, edge):
        paths = self.paths.get(edge.source)
        if paths is None:
            return None
        condition = _parse_when(edge.when)
        if condition is None:
            return paths
        key, operator, value = condition
        atom = (edge.source, key, operator, value)
        return tuple((*path, atom) for path in paths)

    @staticmethod
    def _conflict(left, right):
        for source, key, operator, value in left:
            for other_source, other_key, other_operator, other_value in right:
                if (source, key) != (other_source, other_key):
                    continue
                if operator == other_operator == "==" and value != other_value:
                    return True
                if {operator, other_operator} == {"==", "!="} and value == other_value:
                    return True
        return False

    def exclusive(self, left_edge, right_edge):
        left, right = self.deliveries(left_edge), self.deliveries(right_edge)
        return bool(left and right) and all(self._conflict(a, b) for a in left for b in right)

    def sources_exclusive(self, target, sources):
        if len(sources) != len(set(sources)) or "pipeline.input" in sources:
            return False
        arrivals = {source: [edge for edge in self.transfers
                             if edge.source == source and edge.target == target] for source in sources}
        return all(arrivals[source] for source in sources) and all(
            self.exclusive(left, right)
            for index, source in enumerate(sources)
            for other in sources[index + 1:]
            for left in arrivals[source] for right in arrivals[other]
        )
