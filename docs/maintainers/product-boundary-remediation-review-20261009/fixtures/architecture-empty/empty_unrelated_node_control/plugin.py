from vibeflow.targets.python.sdk import Plugin, ruleset
from node_resource import Start, Task, Foreign
selected = ruleset(id="probe.selected", calls=[{'id': 'selected', 'rule_id': 'vibeflow.node_architecture'}])
plugin = Plugin(id="probe", resources=[Start, Task, Foreign, selected], declaration_rulesets=[])
