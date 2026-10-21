"""NodeType shells and preparation-time application to business Nodes."""

from dataclasses import dataclass, field, fields
from typing import Mapping

from vibeflow.core.descriptors.models import DescriptorModelError, NodeDescriptor, _required_text
from vibeflow.core.descriptors.presentation import normalize_presentation
from vibeflow.core.descriptors.json_values import thaw_json
from vibeflow.core.rules.selection import selection_refs, selection_data


@dataclass(frozen=True)
class NodeTypeDescriptor:
    id: str
    display_name: str = ""
    description: str = ""
    rulesets: tuple = ()
    presentation: Mapping = field(default_factory=dict)

    def __post_init__(self):
        _required_text(self.id, field_name="node_type.id")
        object.__setattr__(self, "rulesets", selection_refs(self.rulesets, field_name="node_type.rulesets"))
        object.__setattr__(self, "presentation", normalize_presentation(self.presentation, field_name="node_type.presentation"))

    def to_dict(self):
        return {"kind": "node_type", "id": self.id, "display_name": self.display_name,
                "description": self.description, "rulesets": selection_data(self.rulesets),
                "presentation": thaw_json(self.presentation)}


@dataclass(frozen=True)
class ResolvedNodeDescriptor(NodeDescriptor):
    """Prepared business definition with explicit, non-executable type provenance."""
    declaration: NodeDescriptor | None = field(default=None, repr=False, compare=False)

    @property
    def ruleset_origin(self):
        return self.node_type if self.declaration.rulesets is None else self.id

    @property
    def presentation_sources(self):
        return {name: "node" if name in self.declaration.presentation else "node_type"
                for name in self.presentation}


def resolve_node_type(node, node_types):
    shell = node_types.get(node.node_type)
    if shell is None:
        raise DescriptorModelError(f"Node '{node.id}' requires missing NodeType '{node.node_type}'")
    values = {item.name: getattr(node, item.name) for item in fields(NodeDescriptor)}
    return ResolvedNodeDescriptor(**{**values,
        "rulesets": shell.rulesets if node.rulesets is None else node.rulesets,
        "presentation": {**shell.presentation, **node.presentation}}, declaration=node)
