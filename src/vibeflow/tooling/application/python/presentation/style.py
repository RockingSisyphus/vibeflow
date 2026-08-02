from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from vibeflow.core.style import (
    NODE_STYLE_FIELDS,
    RESERVED_SYSTEM_COLORS,
    is_hex_color as _core_is_hex_color,
    is_reserved_system_color as _core_is_reserved_system_color,
    normalize_hex_color as _core_normalize_hex_color,
)


@dataclass(frozen=True)
class StyleColors:
    fill: str
    stroke: str
    text: str
    extra: str = ""


SYSTEM_STYLE_COLORS: Mapping[str, StyleColors] = {
    "defaultNode": StyleColors(fill="#ECECFF", stroke="#9370DB", text="#333333"),
    "healthError": StyleColors(fill="#fee2e2", stroke="#dc2626", text="#7f1d1d"),
    "healthWarning": StyleColors(fill="#fef3c7", stroke="#d97706", text="#78350f"),
    "externalDependency": StyleColors(fill="#e0f2fe", stroke="#0284c7", text="#0c4a6e"),
    "documentNode": StyleColors(fill="#f0fdf4", stroke="#16a34a", text="#14532d"),
    "nodesetNode": StyleColors(fill="#ede9fe", stroke="#7c3aed", text="#3b0764"),
    "loopNode": StyleColors(fill="#f0fdfa", stroke="#0f766e", text="#134e4a"),
    "plannedNode": StyleColors(fill="#fef08a", stroke="#ca8a04", text="#713f12", extra="stroke-width:3px,stroke-dasharray: 6 3"),
    "baseLibResource": StyleColors(fill="#ecfdf5", stroke="#059669", text="#064e3b"),
    "pluginResource": StyleColors(fill="#eff6ff", stroke="#2563eb", text="#1e3a8a"),
    "hostExtensionResource": StyleColors(fill="#f5f3ff", stroke="#7c3aed", text="#3b0764"),
    "plannedResource": StyleColors(fill="#fef08a", stroke="#ca8a04", text="#713f12", extra="stroke-width:3px,stroke-dasharray: 6 3"),
}

SYSTEM_MODIFIER_STYLES: Mapping[str, str] = {
    "externalBoundary": "stroke-width:7px,vector-effect:non-scaling-stroke",
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
    "hostExtensionResource",
    "plannedResource",
)
MERMAID_RESOURCE_CLASS_ORDER = (
    "baseLibResource",
    "pluginResource",
    "hostExtensionResource",
    "plannedResource",
)


def is_hex_color(value: object) -> bool:
    return _core_is_hex_color(value)


def normalize_hex_color(value: str) -> str:
    return _core_normalize_hex_color(value)


def is_reserved_system_color(value: str) -> bool:
    return _core_is_reserved_system_color(value)


def mermaid_class_def(class_name: str) -> str:
    modifier = SYSTEM_MODIFIER_STYLES.get(class_name)
    if modifier is not None:
        return f"classDef {class_name} {modifier};"
    style = SYSTEM_STYLE_COLORS[class_name]
    fields = [f"fill:{style.fill}", f"stroke:{style.stroke}"]
    if style.extra:
        fields.append(style.extra)
    fields.append(f"color:{style.text}")
    return f"classDef {class_name} {','.join(fields)};"


def mermaid_class_def_lines(class_names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(mermaid_class_def(class_name) for class_name in class_names)
