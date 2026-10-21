from vibeflow.targets.python.sdk import node,base_lib,SourceLocator,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource

helpers = base_lib(**{'id': 'math.helpers', 'display_name': 'Multi-file arithmetic', 'description': 'Pure arithmetic with a declared support file.', 'rulesets': ['vibeflow.base_lib'], 'dependencies': [], 'external_packages': [], 'source': {'kind': 'file', 'ref': 'base_lib/arithmetic.py'}, 'implementation_files': ['scalar.py']})
