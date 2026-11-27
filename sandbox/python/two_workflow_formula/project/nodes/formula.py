"""公式使用的求和、求差、加倍、调用与合并节点。"""

from vibeflow.targets.python.sdk import node


def value(inputs, name):
    return inputs[f"formula.{name}"]["value"]


@node(id="formula.boundary", node_type="vibeflow.node", flow_kind="terminal", rulesets=[],
      display_name="流程边界", description="标记一次计算的开始或结束，不执行算术操作。", contract={})
class Boundary:
    def run_pure(self, inputs, params):
        return {}


@node(id="formula.sum", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="求两数之和", description="把 x 和 y 相加，得到整数 s。",
      contract={
          "requires": [
              {"type": "formula.x", "cardinality": "exactly_one", "display_name": "第一个整数 x"},
              {"type": "formula.y", "cardinality": "exactly_one", "display_name": "第二个整数 y"},
          ],
          "provides": [{"key": "sum", "type": "formula.sum", "display_name": "两数之和 s"}],
          "input_semantics": {"formula.x": ["被加数。"], "formula.y": ["加数。"]},
          "output_semantics": {"sum": ["s = x + y。"]},
      })
class AddInputs:
    def run_pure(self, inputs, params):
        return {"sum": value(inputs, "x") + value(inputs, "y")}


@node(id="formula.difference", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="求两数之差", description="用 x 减去 y，保留正负号。",
      contract={
          "requires": [
              {"type": "formula.x", "cardinality": "exactly_one", "display_name": "第一个整数 x"},
              {"type": "formula.y", "cardinality": "exactly_one", "display_name": "第二个整数 y"},
          ],
          "provides": [{"key": "difference", "type": "formula.difference", "display_name": "两数之差"}],
          "input_semantics": {"formula.x": ["被减数。"], "formula.y": ["减数。"]},
          "output_semantics": {"difference": ["结果是 x − y，可能为正、零或负。"]},
      })
class SubtractInputs:
    def run_pure(self, inputs, params):
        return {"difference": value(inputs, "x") - value(inputs, "y")}


@node(id="formula.double", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="把差值乘以 2", description="将差值翻倍，得到 2 × (x − y)。",
      contract={
          "requires": [
              {"type": "formula.difference", "cardinality": "exactly_one", "display_name": "两数之差"},
          ],
          "provides": [
              {"key": "double_difference", "type": "formula.double_difference", "display_name": "差值项"},
          ],
          "input_semantics": {"formula.difference": ["上一步得到的 x − y。"]},
          "output_semantics": {"double_difference": ["带符号的两倍差值。"]},
      })
class DoubleDifference:
    def run_pure(self, inputs, params):
        return {"double_difference": 2 * value(inputs, "difference")}


@node(id="formula.invoke_product", node_type="vibeflow.node", flow_kind="workflow-io",
      rulesets=["vibeflow.process"], display_name="交给另一流程计算乘积",
      description="只传入两数之和 s，等待另一流程返回 s × (s + 1)。",
      workflow_operations=[{"operation": "invoke_sync"}],
      contract={
          "requires": [{"type": "formula.sum", "cardinality": "exactly_one", "display_name": "两数之和 s"}],
          "provides": [{"key": "product", "type": "formula.product", "display_name": "乘积项"}],
          "input_semantics": {"formula.sum": ["另一流程只接收 s，无需知道 x 和 y。"]},
          "output_semantics": {"product": ["接收另一流程返回的 s × (s + 1)。"]},
          "params_schema": {"workflow": {"type": "object", "required": True}},
      })
class InvokeProduct:
    def run_pure(self, inputs, params, context):
        result = context.workflow.invoke_sync({
            "workflow": params["workflow"],
            "inputs": {"sum": value(inputs, "sum")},
        })
        return {"product": result["product"]}


@node(id="formula.combine", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="三项相加得到结果", description="等乘积项、差值项和平方与差距项都准备好，再相加。",
      contract={
          "requires": [
              {"type": "formula.product", "cardinality": "exactly_one", "display_name": "乘积项"},
              {"type": "formula.double_difference", "cardinality": "exactly_one", "display_name": "差值项"},
              {"type": "formula.square_gap", "cardinality": "exactly_one", "display_name": "平方与差距项"},
          ],
          "provides": [{"key": "result", "type": "formula.result", "display_name": "公式计算结果"}],
          "input_semantics": {
              "formula.product": ["另一流程算出的 (x + y) × (x + y + 1)。"],
              "formula.double_difference": ["主流程算出的 2 × (x − y)。"],
              "formula.square_gap": ["Nodeset 算出的 x² + y² + |x − y|。"],
          },
          "output_semantics": {"result": ["保留三项明细和它们的和。"]},
      })
class AddTerms:
    def run_pure(self, inputs, params):
        product = value(inputs, "product")
        doubled = value(inputs, "double_difference")
        square_gap = value(inputs, "square_gap")
        return {"result": {
            "乘积项": product, "差值项": doubled, "平方与差距项": square_gap,
            "结果": product + doubled + square_gap,
        }}
