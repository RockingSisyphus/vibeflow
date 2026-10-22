"""Translate public presentation facts to the Mermaid vocabulary."""
from typing import Mapping
from vibeflow.tooling.presentation.style import SYSTEM_STYLE_COLORS
from vibeflow.tooling.presentation.shape_semantics import shape_for_flow_kind


def mermaid_shape(shape):
    return "diam" if shape == "diamond" else shape


def mermaid_shape_for_flow_kind(flow_kind):
    return mermaid_shape(shape_for_flow_kind(flow_kind))


def mermaid_style(presentation):
    names = {"fill":"fill", "stroke":"stroke", "text":"color"}
    return ",".join(f"{name}:{presentation.values[key]}" for key,name in names.items() if key in presentation.values)


SYSTEM_MODIFIER_STYLES: Mapping[str, str] = {
    "externalBoundary": "stroke-width:7px,vector-effect:non-scaling-stroke",
    "plannedNode": "stroke-width:3px,stroke-dasharray:6 3,opacity:0.6",
}

MERMAID_MAIN_CLASS_ORDER = (
    "defaultNode",
    "healthError",
    "healthWarning",
    "externalDependency",
    "externalBoundary",
    "documentNode",
    "nodesetNode",
    "loopNode",
    "plannedNode",
    "baseLibResource",
    "pluginResource",
    "plannedResource",
)

MERMAID_RESOURCE_CLASS_ORDER = (
    "baseLibResource",
    "pluginResource",
    "plannedResource",
)


def mermaid_class_def(class_name: str) -> str:
    modifier = SYSTEM_MODIFIER_STYLES.get(class_name)
    if modifier is not None:
        return f"classDef {class_name} {modifier};"
    style = SYSTEM_STYLE_COLORS[class_name]
    fields = [f"fill:{style.fill}", f"stroke:{style.stroke}"]
    if class_name == "plannedResource":
        fields.append("stroke-width:3px,stroke-dasharray: 6 3")
    fields.append(f"color:{style.text}")
    return f"classDef {class_name} {','.join(fields)};"

def mermaid_class_def_lines(class_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(mermaid_class_def(class_name) for class_name in class_names)
