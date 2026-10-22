"""Composable root resource-use and project/root ownership Rules."""
from vibeflow.core.rules import RuleCall, RuleDescriptor, RuleRelation
from vibeflow.core.descriptors.resource_use import RESOURCE_SET_TYPE, RESOURCE_USE_TYPE


def declarations():
    rules = [RuleDescriptor(f"vibeflow.{level}.plugin_ownership", level=level) for level in ("project", "root")]
    rules.extend(RuleDescriptor("vibeflow.root.resource_" + name, level="root", outputs={"resources": RESOURCE_SET_TYPE})
                 for name in ("visibility", "independent", "plugins"))
    rules.append(RuleDescriptor("vibeflow.root.resource_duplicates", level="root"))
    rules.append(RuleDescriptor("vibeflow.root.resource_use", level="root",
        inputs={name: RESOURCE_SET_TYPE for name in ("visible", "independent", "plugins")}, outputs={"use": RESOURCE_USE_TYPE}))
    rules.append(RuleDescriptor("vibeflow.root.resource_references", level="root", inputs={"use": RESOURCE_USE_TYPE}))
    calls = tuple(RuleCall(rule.id.rsplit(".", 1)[1], rule_id=rule.id) for rule in rules if rule.level == "root")
    relations = tuple(RuleRelation("resource_use", "resource_" + name, "requires", {port: "resources"})
                      for name, port in (("visibility", "visible"), ("independent", "independent"), ("plugins", "plugins")))
    relations += (RuleRelation("resource_references", "resource_use", "requires", {"use": "use"}),)
    return tuple(rules), calls, relations


def handlers():
    from .selection import visibility, independent, plugins, duplicates, compose
    from .references import references
    from .ownership import ownership
    return {**{f"vibeflow.{level}.plugin_ownership": ownership for level in ("project", "root")},
            **{"vibeflow.root.resource_" + name: handler for name, handler in (
                ("visibility", visibility), ("independent", independent), ("plugins", plugins),
                ("duplicates", duplicates), ("use", compose), ("references", references))}}
