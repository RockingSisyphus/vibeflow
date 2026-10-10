from vibeflow.targets.python.sdk import rule
from vibeflow.targets.python.sdk import Plugin,node,rule,ruleset,data_schema,base_lib,capability,host_extension,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource
resource_0 = node(**{'type_key': 'example.model',
 'display_name': 'ModelBlock',
 'description': 'One model_block block in the example workflow.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'example.input',
                            'cardinality': 'exactly_one',
                            'display_name': 'Input'}],
              'provides': [{'key': 'feature',
                            'type': 'example.feature',
                            'display_name': 'Feature'}],
              'input_semantics': {'example.input': ['Input value for this '
                                                    'functional block.']},
              'output_semantics': {'feature': ['Scaled model output.']},
              'params_schema': {'gain': {'type': 'number'}},
              'params_defaults': {'gain': 2},
              'examples': [{'inputs': {'example.input': {'value': 3}},
                            'params': {'gain': 2}}]},
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'domain_nodes.py',
                                 'export': 'ModelBlock'},
                      'implementation_files': [{'kind': 'file',
                                                'ref': 'domain_helpers/__init__.py'},
                                               {'kind': 'file',
                                                'ref': 'domain_helpers/arithmetic.py'}]}],
 'rulesets': ['example.model_domain'],
 'presentation': {'fill': '#cceeff', 'shape': 'rect'},
 'tags': ['model_block'],
 'source': {'kind': 'file', 'ref': 'domain_nodes.py', 'export': 'ModelBlock'}})

resource_1 = node(**{'type_key': 'example.transform',
 'display_name': 'DataTransform',
 'description': 'One data_transform block in the example workflow.',
 'version': '0.15.0',
 'flow_kind': 'process',
 'contract': {'requires': [{'type': 'example.feature',
                            'cardinality': 'exactly_one',
                            'display_name': 'Feature'}],
              'provides': [{'key': 'result',
                            'type': 'example.output',
                            'display_name': 'Result'}],
              'input_semantics': {'example.feature': ['Model result to '
                                                      'transform.']},
              'output_semantics': {'result': ['Model result plus an offset.']},
              'params_schema': {'offset': {'type': 'number'}},
              'params_defaults': {'offset': 1},
              'examples': [{'inputs': {'example.feature': {'value': 6}},
                            'params': {'offset': 1}}]},
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'domain_nodes.py',
                                 'export': 'DataTransform'},
                      'implementation_files': [{'kind': 'file',
                                                'ref': 'domain_helpers/__init__.py'},
                                               {'kind': 'file',
                                                'ref': 'domain_helpers/arithmetic.py'}]}],
 'rulesets': ['example.data_domain'],
 'presentation': {'fill': '#dff7df', 'shape': 'rounded'},
 'tags': ['data_transform'],
 'source': {'kind': 'file',
            'ref': 'domain_nodes.py',
            'export': 'DataTransform'}})

resource_2 = node(**{'type_key': 'example.boundary',
 'display_name': 'Boundary',
 'description': 'A native start or end boundary.',
 'version': '0.15.0',
 'flow_kind': 'terminal',
 'contract': {},
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'domain_nodes.py',
                                 'export': 'Boundary'},
                      'implementation_files': [{'kind': 'file',
                                                'ref': 'domain_helpers/__init__.py'},
                                               {'kind': 'file',
                                                'ref': 'domain_helpers/arithmetic.py'}]}],
 'rulesets': ['vibeflow.io'],
 'tags': ['flowchart'],
 'source': {'kind': 'file', 'ref': 'domain_nodes.py', 'export': 'Boundary'}})

resource_3 = rule(**{'id': 'example.model_definition',
 'description': 'One direct model_forward method per model_block; helpers do '
                'not inherit legal model-definition ownership.',
 'scope': 'source',
 'params_schema': {'marker_method': {'type': 'string'},
                   'model_tag': {'type': 'string'}},
 'params_defaults': {'marker_method': 'model_forward',
                     'model_tag': 'model_block'},
 'outputs': {'evidence': 'example.model_definition.v1'},
 'implementations': [{'language': 'python',
                      'source': {'kind': 'file',
                                 'ref': 'rules/model_definition.py',
                                 'export': 'check'}}],
 'source': {'kind': 'file',
            'ref': 'rules/model_definition.py',
            'export': 'check'}})

resource_4 = ruleset(**{'id': 'example.model_domain',
 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition', 'rule_id': 'example.model_definition'}],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']},
 'relations': [{'source': '$self',
                'target': 'native/interface',
                'kind': 'overrides',
                'params': {'allowed_methods': ['model_forward']}}]})

resource_5 = ruleset(**{'id': 'example.data_domain',
 'calls': [{'id': 'native', 'ruleset_id': 'vibeflow.process'},
           {'id': 'definition', 'rule_id': 'example.model_definition'}],
 'entrypoints': {'import': ['native'],
                 'static': ['native', 'definition'],
                 'run': ['native', 'definition']}})

resource_6 = data_schema(**{'type_key': 'example.feature',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_7 = data_schema(**{'type_key': 'example.input',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_8 = data_schema(**{'type_key': 'example.output',
 'representation': 'json',
 'schema': {'type': 'number'}})

resource_9 = rule(id="example.model_files", implementations=[{"language":"python", "source":{"kind":"file", "ref":"rules/model_files.py", "export":"check"}}], source={"kind":"file", "ref":"rules/model_files.py", "export":"check"})
resource_10 = ruleset(id="example.model_layout", workflow_default=True,
    calls=[{"id":"files", "rule_id":"example.model_files"}], entrypoints={"static":["files"], "run":["files"]})

plugin = Plugin(id='fixture.resources', resources=[resource_0, resource_1, resource_2, resource_3, resource_4, resource_5, resource_6, resource_7, resource_8, resource_9, resource_10])
