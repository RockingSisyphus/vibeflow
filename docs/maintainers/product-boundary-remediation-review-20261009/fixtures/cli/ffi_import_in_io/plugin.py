from vibeflow.targets.python.sdk import Plugin, ruleset
from node_resource import Start, Task
selected = ruleset(id="probe.selected", calls=[{'id': 'selected', 'rule_id': 'vibeflow.no_side_effects', 'params': {'effect_scope': 'python_io'}}])
plugin = Plugin(id="probe", resources=[Start, Task, selected], declaration_rulesets=[])
