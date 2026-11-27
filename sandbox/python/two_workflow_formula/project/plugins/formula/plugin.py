"""声明三个数学工作流共享的数学数据类型。"""

from vibeflow.targets.python.sdk import Plugin, data_schema

plugin = Plugin(
    id="formula.data",
    resources=[
        data_schema(type_key=f"formula.{name}", schema={"type": "integer"})
        for name in (
            "x", "y", "sum", "difference", "double_difference", "original", "next", "product",
            "sum_squares", "absolute_gap", "square_gap",
        )
    ] + [data_schema(type_key="formula.result", schema={"type": "object"})],
)
