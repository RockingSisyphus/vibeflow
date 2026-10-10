from vibeflow.targets.python.sdk import Plugin
from nodes import Boundary, Argv, Input, StreamInput, PathLeft, OpenLeft, PathRight, OpenRight, Yaml, Sum, PathWrite, OpenWrite, Print, Streams
from math_resource import total

plugin = Plugin(id="addition.cli", resources=[Boundary, Argv, Input, StreamInput, PathLeft, OpenLeft, PathRight, OpenRight, Yaml, Sum, PathWrite, OpenWrite, Print, Streams, total])
