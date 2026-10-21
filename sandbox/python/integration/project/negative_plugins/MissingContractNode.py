from vibeflow.targets.python.sdk import Plugin, node

invalid = node(**{'node_type':'vibeflow.node', 'id': 'bad.missing_contract',
 'display_name': 'Bad',
 'description': 'Bad node without contract.',
 'version': '0.1.0',
 'flow_kind': 'process',
 'author': None,
 'tags': ['bad'],
 'external': False,
 'rulesets': ['vibeflow.process'],
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'illegal_nodes/metadata_contract_cases.py',
                                 'export': 'MissingContractNode'}}],
 'source': {'kind': 'file',
            'ref': 'illegal_nodes/metadata_contract_cases.py',
            'export': 'MissingContractNode'}})
