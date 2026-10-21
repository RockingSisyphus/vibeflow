"""javascript Ruleset definitions; Rule implementations live in rules/."""
from vibeflow.targets.javascript.rulesets.standard import standard_rulesets
from vibeflow.targets.javascript.rulesets.source_quality import source_quality_ruleset


def builtin_rulesets():
    return (*standard_rulesets(), source_quality_ruleset())
