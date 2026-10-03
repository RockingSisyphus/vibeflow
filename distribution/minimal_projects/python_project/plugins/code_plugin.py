from vibeflow.targets.python.sdk import Plugin, base_lib, SourceLocator
from nodes.workflow_nodes import EndNode, InputBoundaryNode, OutputBoundaryNode, ProcessPayloadNode, StartNode
plugin=Plugin(id='minimal.python',resources=[EndNode, InputBoundaryNode, OutputBoundaryNode, ProcessPayloadNode, StartNode])
