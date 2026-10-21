from vibeflow.targets.python.sdk import node,base_lib,SourceLocator,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource

resource_152 = base_lib(**{'id': 'good_math',
 'display_name': 'Good Math',
 'description': 'Validated arithmetic helper functions for sandbox resource '
                'checks.',
 'rulesets': ['vibeflow.base_lib'],
 'category': 'sandbox',
 'version': '0.1.0',
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'module',
                                 'ref': 'base_lib.good_math'}}],
 'source': {'kind': 'module', 'ref': 'base_lib.good_math'}})

resource_153 = base_lib(**{'id': 'good_chain_a',
 'display_name': 'Good Chain A',
 'description': 'A valid dependency-chain helper module for sandbox resource '
                'checks.',
 'rulesets': ['vibeflow.base_lib'],
 'category': 'sandbox',
 'version': '0.1.0',
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'module',
                                 'ref': 'base_lib.good_chain_a'},
                      'implementation_files': [{'kind': 'file',
                                                'ref': '__init__.py'},
                                               {'kind': 'file',
                                                'ref': 'good_chain_b.py'}]}],
 'dependencies': ['good_math'],
 'source': {'kind': 'module', 'ref': 'base_lib.good_chain_a'}})

resource_154 = base_lib(**{'id': 'sandbox_arithmetic',
 'display_name': 'Sandbox Arithmetic',
 'description': 'Arithmetic helper functions used by the resource nodeset '
                'fixture.',
 'rulesets': ['vibeflow.base_lib'],
 'category': 'sandbox',
 'version': '0.1.0',
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'module',
                                 'ref': 'base_lib.sandbox_arithmetic'}}],
 'source': {'kind': 'module', 'ref': 'base_lib.sandbox_arithmetic'}})
