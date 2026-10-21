from vibeflow.targets.python.sdk import Plugin
from vibetrain.nodes.workflow_nodes import StartNode,InputBoundaryNode,ProcessPayloadNode,OutputBoundaryNode,EndNode
plugin=Plugin(id="probe.exports",resources=[StartNode,InputBoundaryNode,ProcessPayloadNode,OutputBoundaryNode,EndNode])
