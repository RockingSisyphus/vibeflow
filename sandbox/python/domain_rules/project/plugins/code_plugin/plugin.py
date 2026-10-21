from vibeflow.targets.python.sdk import Plugin,node,node_type,rule,ruleset,data_schema,base_lib,capability,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource
resource_0 = rule(**{'id': 'example.model_definition',
 'display_name': '',
 'description': 'One direct model_forward method per model_block; helpers do '
                'not inherit legal model-definition ownership.',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/model_definition.py',
                                 'export': 'check'}}],
 'inputs': {},
 'outputs': {'evidence': 'example.model_definition.v1'},
 'params_schema': {'marker_method': {'type': 'string'},
                   'model_tag': {'type': 'string'}},
 'params_defaults': {'marker_method': 'model_forward',
                     'model_tag': 'model_block'},
 'handler': '',
 'scope': 'source',
 'level': 'node',
 'source': {'kind': 'file',
            'ref': 'rules/model_definition.py',
            'export': 'check'}})

resource_1 = rule(**{'id': 'example.model_files',
 'display_name': '',
 'description': '',
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/model_files.py',
                                 'export': 'check'}}],
 'inputs': {},
 'outputs': {},
 'params_schema': {},
 'params_defaults': {},
 'handler': '',
 'scope': 'call',
 'level': 'graph',
 'source': {'kind': 'file', 'ref': 'rules/model_files.py', 'export': 'check'}})

resource_2 = ruleset(**{'id': 'example.data_domain',
 'calls': [{'id': 'native', 'params': {}, 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition',
            'params': {},
            'rule_id': 'example.model_definition'}],
 'relations': [],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']},
 'display_name': '',
 'description': '',
 'workflow_default': False,
 'graph_scope': None})

resource_3 = ruleset(**{'id': 'example.model_domain',
 'calls': [{'id': 'native', 'params': {}, 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition',
            'params': {},
            'rule_id': 'example.model_definition'}],
 'relations': [{'source': '$self',
                'target': 'native/interface',
                'kind': 'overrides',
                'bindings': {},
                'params': {'allowed_methods': ['model_forward']},
                'replace_rule': ''}],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']},
 'display_name': '',
 'description': '',
 'workflow_default': False,
 'graph_scope': None})

resource_4 = ruleset(**{'id': 'example.model_layout',
 'calls': [{'id': 'files', 'params': {}, 'rule_id': 'example.model_files'}],
 'relations': [],
 'entrypoints': {'static': ['files'], 'run': ['files']},
 'display_name': '',
 'description': '',
 'workflow_default': True,
 'graph_scope': None})

resource_5 = data_schema(**{'type_key': 'example.feature',
 'representation': 'json',
 'display_name': '',
 'description': '',
 'schema': {'type': 'number',
            '$schema': 'https://json-schema.org/draft/2020-12/schema'}})

resource_6 = data_schema(**{'type_key': 'example.input',
 'representation': 'json',
 'display_name': '',
 'description': '',
 'schema': {'type': 'number',
            '$schema': 'https://json-schema.org/draft/2020-12/schema'}})

resource_7 = data_schema(**{'type_key': 'example.output',
 'representation': 'json',
 'display_name': '',
 'description': '',
 'schema': {'type': 'number',
            '$schema': 'https://json-schema.org/draft/2020-12/schema'}})

plugin = Plugin(id='example.python.domain_rules', resources=[resource_0, resource_1, resource_2, resource_3, resource_4, resource_5, resource_6, resource_7])
