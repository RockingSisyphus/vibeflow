from vibeflow.targets.python.sdk import Plugin, node

invalid = node(**{'type_key': 'bad.info_type',
 'display_name': [],
 'contract': {'requires': [],
              'provides': [{'key': 'bad.out',
                            'type': 'bad.out',
                            'display_name': 'bad.out'}],
              'input_semantics': {},
              'output_semantics': {'bad.out': ['bad output']},
              'examples': [],
              'params_schema': {},
              'params_defaults': {}},
 'rulesets': ['vibeflow.process'],
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'illegal_nodes/metadata_contract_cases.py',
                                 'export': 'InfoWrongTypeNode'}}],
 'source': {'kind': 'file',
            'ref': 'illegal_nodes/metadata_contract_cases.py',
            'export': 'InfoWrongTypeNode'}})
plugin = Plugin(id='invalid.InfoWrongTypeNode', resources=[invalid])
