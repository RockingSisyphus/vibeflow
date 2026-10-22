"""Apply planned opacity to complete SVG objects, once per visible subtree."""
import re
import xml.etree.ElementTree as ET


def normalize_planned_svg(text):
    if not re.search(r'\bclass=["\'][^"\']*\b(?:plannedNode|planned-panel)\b', text):
        return text
    root = ET.fromstring(text)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

    def opacity(element, value):
        style = re.sub(r'(?:^|;)\s*opacity\s*:[^;]*', '', element.get("style", ""))
        element.set("style", style.rstrip(";") + f";opacity:{value}!important")

    def visit(element, inherited=False, node_content=False):
        classes = set(element.get("class", "").split())
        planned = bool(classes & {"plannedNode", "planned-panel"})
        if planned:
            opacity(element, "1" if inherited else "0.6")
        elif node_content:
            # Mermaid's classDef applies opacity to geometry instead of the label.
            # Inline priority prevents its generated ID selectors dimming twice.
            opacity(element, "1")
        for child in element:
            visit(child, inherited or planned, node_content or "plannedNode" in classes)

    visit(root)
    return ET.tostring(root, encoding="unicode") + "\n"
