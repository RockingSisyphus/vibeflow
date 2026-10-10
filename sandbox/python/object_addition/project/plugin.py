from vibeflow.targets.python.sdk import Plugin
from nodes import Boundary, Add, Report
from math_resource import add

plugin = Plugin(id="addition.objects", resources=[Boundary, Add, Report, add])
