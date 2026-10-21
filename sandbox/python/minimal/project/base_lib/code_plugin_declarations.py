from vibeflow.targets.python.sdk import node,base_lib,SourceLocator,ResourceDefinition
from vibeflow.core.descriptors.decode import decode_resource

math_tools=base_lib(implementation_files=['__init__.py'],id='base_lib.math_tools',display_name='Math Tools',description='Pure arithmetic helper',rulesets=['vibeflow.base_lib'],source=SourceLocator(kind='module',ref='base_lib.math_tools'))
