"""只接收整数 s，计算相邻整数的乘积 s × (s + 1)。"""

from vibeflow.targets.python.sdk import node


@node(id="formula.add_one", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="把 s 加 1", description="算出下一个整数 s + 1，同时把原来的 s 传给乘法节点。",
      contract={
          "requires": [{"type": "formula.sum", "cardinality": "exactly_one", "display_name": "收到的整数 s"}],
          "provides": [
              {"key": "original", "type": "formula.original", "display_name": "原来的整数 s"},
              {"key": "next", "type": "formula.next", "display_name": "下一个整数 s + 1"},
          ],
          "input_semantics": {"formula.sum": ["待计算的整数 s。"]},
          "output_semantics": {"original": ["作为乘法的第一个因数。"], "next": ["作为乘法的第二个因数。"]},
      })
class AddOne:
    def run_pure(self, inputs, params):
        number = inputs["formula.sum"]["value"]
        return {"original": number, "next": number + 1}


@node(id="formula.multiply", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="相邻两数相乘", description="把原来的 s 和刚算出的 s + 1 相乘。",
      contract={
          "requires": [
              {"type": "formula.original", "cardinality": "exactly_one", "display_name": "原来的整数 s"},
              {"type": "formula.next", "cardinality": "exactly_one", "display_name": "下一个整数 s + 1"},
          ],
          "provides": [{"key": "product", "type": "formula.product", "display_name": "相邻整数乘积"}],
          "input_semantics": {"formula.original": ["第一个因数。"], "formula.next": ["第二个因数。"]},
          "output_semantics": {"product": ["相邻两个整数的乘积 s × (s + 1)。"]},
      })
class MultiplyNeighbors:
    def run_pure(self, inputs, params):
        return {"product": inputs["formula.original"]["value"] * inputs["formula.next"]["value"]}
