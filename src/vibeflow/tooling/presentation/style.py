"""Renderer-neutral system colour palette."""
from dataclasses import dataclass
from typing import Mapping


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
    "plannedNode": StyleColors(fill="#fef08a", stroke="#ca8a04", text="#713f12"),
    "baseLibResource": StyleColors(fill="#ecfdf5", stroke="#059669", text="#064e3b"),
    "pluginResource": StyleColors(fill="#eff6ff", stroke="#2563eb", text="#1e3a8a"),
    "hostExtensionResource": StyleColors(fill="#f5f3ff", stroke="#7c3aed", text="#3b0764"),
    "plannedResource": StyleColors(fill="#fef08a", stroke="#ca8a04", text="#713f12"),
}
