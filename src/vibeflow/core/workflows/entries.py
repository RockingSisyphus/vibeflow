"""Named entry contracts and projection of an already compiled graph."""
from dataclasses import dataclass, replace
from collections.abc import Mapping

from vibeflow.core.contracts import parse_pipeline_inputs, parse_pipeline_outputs


@dataclass(frozen=True)
class EntrySpec:
    start: str
    inputs: tuple | None = None
    outputs: tuple | None = None

    def to_dict(self):
        result = {"start": self.start}
        if self.inputs is not None:
            result["inputs"] = [item.to_dict() for item in self.inputs]
        if self.outputs is not None:
            result["outputs"] = [item.to_dict() for item in self.outputs]
        return result


def parse_entries(value, *, node_ids, default="", field="pipeline.entries"):
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")
    result = {}
    for name, raw in value.items():
        location = f"{field}.{name}"
        if not isinstance(name, str) or not name.strip() or not isinstance(raw, Mapping):
            raise ValueError(f"{location} must name an entry object")
        if set(raw) - {"start", "inputs", "outputs"}:
            raise ValueError(f"{location} allows only start, inputs and outputs")
        start = raw.get("start")
        if not isinstance(start, str) or start not in node_ids:
            raise ValueError(f"{location}.start must name an existing node")
        result[name] = EntrySpec(start,
            parse_pipeline_inputs(raw["inputs"], field=location + ".inputs") if "inputs" in raw else None,
            parse_pipeline_outputs(raw["outputs"], field=location + ".outputs") if "outputs" in raw else None)
    if not isinstance(default, str) or default and default not in result:
        raise ValueError("default_entry must name a declared entry")
    return result


def choose_entry(entries, default="", entry=None):
    if not entries:
        if entry is not None:
            raise ValueError(f"unknown workflow entry: {entry}")
        return None
    selected = entry if entry is not None else default or (next(iter(entries)) if len(entries) == 1 else None)
    if selected not in entries:
        raise ValueError("select a workflow entry: " + ", ".join(entries))
    return selected


def project_entry(graph, compiled, entry=None):
    """Select existing nodes/routes and contracts; never recompile business code."""
    selected = choose_entry(graph.entries, graph.default_entry, entry)
    if selected is None:
        return graph, compiled
    definition = graph.entries[selected]
    routes = compiled.resolved_schedule_edges
    if compiled.flow_kinds.get(definition.start) != "terminal" or any(e.target == definition.start for e in routes):
        raise ValueError(f"entry '{selected}' must start at a terminal without incoming schedule edges")
    active, pending = set(), [definition.start]
    outgoing = {}
    for edge in routes:
        outgoing.setdefault(edge.source, []).append(edge.target)
    while pending:
        current = pending.pop()
        if current not in active:
            active.add(current)
            pending.extend(outgoing.get(current, ()))
    return project_selected_graph(graph, compiled, selected, active)


def project_selected_graph(graph, compiled, selected, active):
    """Filter a checked graph using a previously prepared entry selection."""
    definition = graph.entries[selected]
    keep_edges = lambda values: tuple(e for e in values if e.source in active and e.target in active)
    projected = replace(graph, nodes=tuple(n for n in graph.nodes if n.id in active),
        edges=keep_edges(graph.edges),
        inputs=graph.inputs if definition.inputs is None else definition.inputs,
        outputs=graph.outputs if definition.outputs is None else definition.outputs,
        entries={}, default_entry="", selected_entry=selected)
    edge_fields = ("explicit_edges", "data_edges", "effective_edges", "mainline_edges",
                   "data_bypass_edges", "schedule_edges", "transfer_edges")
    updates = {key: keep_edges(getattr(compiled, key)) for key in edge_fields}
    updates.update(order=tuple(n for n in compiled.order if n in active),
        flow_kinds={k: v for k, v in compiled.flow_kinds.items() if k in active},
        effect_scopes={k: v for k, v in compiled.effect_scopes.items() if k in active},
        providers=compiled.entry_providers.get(selected, {k: v for k, v in compiled.providers.items() if v in active}),
        entry_providers={},
        consumers={k: tuple(n for n in v if n in active) for k, v in compiled.consumers.items()},
        contains_global_state=any(compiled.flow_kinds.get(n) == "global_state" for n in active))
    return projected, replace(compiled, **updates)
