"""Graph Rule definitions, separate from node source checks."""
from vibeflow.targets.javascript.rules.graph.topics import workflow_topic_resources, workflow_topic_handlers
from vibeflow.targets.javascript.rules.graph.workflow import workflow_plan_resources, workflow_plan_handlers


from inspect import unwrap

def bound_workflow_depth_defaults(handlers, depth, *, rules, origins):
    """Apply project depth configuration to the actual standard consumers."""
    from vibeflow.targets.shared.rule_support.workflow import nodesets
    from vibeflow.targets.shared.rule_support.plugin import configured_rule_defaults
    consumers = ((workflow_topic_handlers()["vibeflow.graph.nodesets"], workflow_topic_resources), (nodesets, workflow_plan_resources))
    result = {}
    for resource_id, handler in handlers.items():
        check = unwrap(handler) if handler is not None else None
        for native, factory in consumers:
            if check is native and resource_id in rules:
                configured = configured_rule_defaults(rules[resource_id],
                    {"nodeset_max_depth": depth}, origins.get(("rules", resource_id)), factory=factory)
                if configured:
                    result[resource_id] = configured
                break
    return result
