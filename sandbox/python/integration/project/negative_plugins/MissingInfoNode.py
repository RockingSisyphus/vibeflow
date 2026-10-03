from vibeflow.targets.python.sdk import Plugin, node

invalid = node(**{'contract': {'requires': [],
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
                                 'export': 'MissingInfoNode'}}],
 'source': {'kind': 'file',
            'ref': 'illegal_nodes/metadata_contract_cases.py',
            'export': 'MissingInfoNode'}})
plugin = Plugin(id='invalid.MissingInfoNode', resources=[invalid])
