from vibeflow.targets.python.sdk import Plugin, ruleset, data_schema, base_lib, capability, host_extension, SourceLocator
from domain_nodes import Boundary as resource_0

from domain_nodes import ModelBlock as resource_1

from domain_nodes import DataTransform as resource_2

from rules.model_definition import check as resource_3

resource_4=ruleset(**{'id': 'example.data_domain',
 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition', 'rule_id': 'example.model_definition'}],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']}})

resource_5=ruleset(**{'id': 'example.model_domain',
 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition', 'rule_id': 'example.model_definition'}],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']},
 'relations': [{'source': '$self',
                'target': 'native/interface',
                'kind': 'overrides',
                'params': {'allowed_methods': ['model_forward']}}]})

resource_6=data_schema(**{'type_key': 'example.feature',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_7=data_schema(**{'type_key': 'example.input',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_8=data_schema(**{'type_key': 'example.output',
 'representation': 'json',
 'schema': {'type': 'number'}})

plugin=Plugin(id='example.python.domain_rules',resources=[resource_0,resource_1,resource_2,resource_3,resource_4,resource_5,resource_6,resource_7,resource_8])
