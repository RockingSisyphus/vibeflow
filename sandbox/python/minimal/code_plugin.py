from vibeflow.targets.python.sdk import Plugin, base_lib, SourceLocator
from nodes import AddNode, EndNode, SeedNode, StartNode
math_tools=base_lib(implementation_files=['base_lib/__init__.py'],id='base_lib.math_tools',display_name='Math Tools',description='Pure arithmetic helper',rulesets=['vibeflow.base_lib'],source=SourceLocator(kind='module',ref='base_lib.math_tools'))
plugin=Plugin(id='minimal.python',resources=[AddNode, EndNode, SeedNode, StartNode, math_tools])
