"""Finite transport of the native shared Nodeset registry."""
from dataclasses import fields
from typing import Callable


def graph_wire(graph: object, project: Callable[[object], object]) -> dict:
    """Definitions occur once; child blocks refer to their registry by ID."""
    def body(block):
        return {item.name: project(getattr(block, item.name)) for item in fields(block)
                if item.name != "nodesets"}
    return {**body(graph), "nodesets": {
        key: {**{item.name: project(getattr(definition, item.name)) for item in fields(definition)
                  if item.name != "graph"},
              "graph": {**body(definition.graph), "nodeset_refs": list(definition.graph.nodesets)}}
        for key, definition in graph.nodesets.items()}}
