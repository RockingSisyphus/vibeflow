from vibeflow.targets.python.sdk import Plugin,node,node_type,rule,ruleset,data_schema,base_lib,capability,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource
resource_0 = base_lib(**{'id': 'workflow.add',
 'display_name': 'Add',
 'description': 'Arithmetic shared by this root.',
 'rulesets': ['vibeflow.base_lib'],
 'implementations': [{'language': 'python',
                      'targets': ['python'],
                      'source': {'kind': 'file',
                                 'ref': 'base_lib/math_lib.py',
                                 'export': 'add'},
                      'implementation_files': []}],
 'source': {'kind': 'file', 'ref': 'base_lib/math_lib.py', 'export': 'add'}})
