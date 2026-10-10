from vibeflow.targets.python.sdk import Plugin
from math_resource import add
from nodes import Boundary, SumU, SumV, Compare, Left, Right, Finish, LeftEnd, RightEnd, Copy, LinearFinish

plugin = Plugin(id="piecewise.plugin", resources=[
    add, Boundary, SumU, SumV, Compare, Left, Right, Finish, LeftEnd, RightEnd, Copy, LinearFinish,
])
