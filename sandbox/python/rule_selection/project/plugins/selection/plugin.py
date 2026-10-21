from vibeflow.targets.python.sdk import Plugin, ruleset
from .rules import analyze, graph_check, local_check

r0 = ruleset(**{'id': 'selection.default', 'workflow_default': True, 'graph_scope': 'current_graph', 'calls': [{'id': 'analyze', 'rule_id': 'selection.analyze', 'params': {'label': 'selection.default'}}, {'id': 'check', 'rule_id': 'selection.graph_check'}], 'relations': [{'source': 'check', 'target': 'analyze', 'kind': 'requires', 'bindings': {'coverage': 'coverage'}}], 'entrypoints': {'static': ['check']}})
r1 = ruleset(**{'id': 'selection.child', 'graph_scope': 'current_graph', 'calls': [{'id': 'analyze', 'rule_id': 'selection.analyze', 'params': {'label': 'selection.child'}}, {'id': 'check', 'rule_id': 'selection.graph_check'}], 'relations': [{'source': 'check', 'target': 'analyze', 'kind': 'requires', 'bindings': {'coverage': 'coverage'}}], 'entrypoints': {'static': ['check']}})
r2 = ruleset(**{'id': 'selection.whole', 'graph_scope': 'effective_subtree', 'calls': [{'id': 'analyze', 'rule_id': 'selection.analyze', 'params': {'label': 'selection.whole'}}, {'id': 'check', 'rule_id': 'selection.graph_check'}], 'relations': [{'source': 'check', 'target': 'analyze', 'kind': 'requires', 'bindings': {'coverage': 'coverage'}}], 'entrypoints': {'static': ['check']}})
r3 = ruleset(**{'id': 'selection.local', 'calls': [{'id': 'check', 'rule_id': 'selection.local_check'}], 'entrypoints': {'static': ['check']}})
plugin = Plugin(id="selection.plugin", resources=[ analyze, graph_check, local_check, r0, r1, r2, r3])
