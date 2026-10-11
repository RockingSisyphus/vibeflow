"""javascript Ruleset definitions; Rule implementations live in rules/."""
from vibeflow.targets.javascript.rulesets.standard import standard_rulesets
from vibeflow.targets.javascript.rulesets.project import project_quality_ruleset


def builtin_rulesets():
    return (*standard_rulesets(), project_quality_ruleset())
