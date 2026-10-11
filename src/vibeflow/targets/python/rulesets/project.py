"""Project source-quality Ruleset definition."""
from vibeflow.core.rules import RuleCall, RuleRelation, RulesetDescriptor


def project_quality_ruleset():
    return RulesetDescriptor("vibeflow.quality.project",
        tuple(RuleCall(name, "vibeflow.quality." + name) for name in ("files", "dependencies", "structure", "duplicates")),
        (RuleRelation("structure", "dependencies", "requires", bindings={"graph": "graph", "import_sites": "import_sites"}),))
