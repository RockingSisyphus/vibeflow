"""Read defaults from fixed resource declarations only."""


def workflow_defaults(rulesets):
    return tuple(sorted(key for key, descriptor in rulesets.items() if descriptor.workflow_default))


def node_defaults(descriptor):
    return descriptor.rulesets
