from vibeflow.targets.python.sdk import Plugin, ruleset, RuleCall
from .math_resource import calculate
from .plugin_support import compiler, runtime

hooks = ruleset(id="addition.hooks", calls=[RuleCall("imports", rule_id="vibeflow.import_side_effects"), RuleCall("effects", rule_id="vibeflow.no_side_effects", params={"effect_scope": "python_io"}), RuleCall("interface", rule_id="vibeflow.node_interface")], entrypoints={"import": ["imports"], "static": ["effects", "interface"], "run": ["effects", "interface"]})
plugin = Plugin(id="addition.plugin", resources=[calculate, hooks], compiler=compiler, runtime=runtime, implementation_files=["plugin_support.py"], rulesets=["addition.hooks"], declaration_rulesets=["vibeflow.plugin_declaration"])
