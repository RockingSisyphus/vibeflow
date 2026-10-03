from vibeflow.targets.python.sdk import Plugin, ruleset, data_schema, base_lib, capability, host_extension, SourceLocator
from rule_graph_nodes import Boundary as resource_0

from rule_graph_nodes import Calculate as resource_1

from rules.checker import check as resource_2

from rules.provider import check as resource_3

from rules.provider import replacement as resource_4

from rules.provider import resource_5_check as resource_5

resource_6=ruleset(**{'id': 'example.rule_graph',
 'calls': [{'id': 'provider', 'rule_id': 'example.number_provider'},
           {'id': 'checker', 'rule_id': 'example.number_checker'}],
 'relations': [{'source': 'checker',
                'target': 'provider',
                'kind': 'requires',
                'bindings': {'numbers': 'numbers'}}]})

resource_7=ruleset(**{'id': 'example.nested',
 'calls': [{'id': 'pair', 'ruleset_id': 'example.shared_pair'}]})

resource_8=ruleset(**{'id': 'example.shared_pair',
 'calls': [{'id': 'provider', 'rule_id': 'example.number_provider'},
           {'id': 'checker', 'rule_id': 'example.number_checker'}],
 'relations': [{'source': 'checker',
                'target': 'provider',
                'kind': 'requires',
                'bindings': {'numbers': 'numbers'}}]})

resource_9=data_schema(**{'type_key': 'example.input',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_10=data_schema(**{'type_key': 'example.output',
 'representation': 'json',
 'schema': {'type': 'number'}})

plugin=Plugin(id='example.python.rule_graph',resources=[resource_0,resource_1,resource_2,resource_3,resource_4,resource_5,resource_6,resource_7,resource_8,resource_9,resource_10])
