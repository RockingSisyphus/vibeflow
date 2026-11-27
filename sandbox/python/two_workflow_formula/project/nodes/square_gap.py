"""平方与差距 Nodeset 使用的算术节点。"""

from vibeflow.targets.python.sdk import node


@node(id="formula.sum_squares", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="求两数的平方和", description="把 x² 与 y² 相加。",
      contract={
          "requires": [
              {"type": "formula.x", "cardinality": "exactly_one", "display_name": "第一个整数 x"},
              {"type": "formula.y", "cardinality": "exactly_one", "display_name": "第二个整数 y"},
          ],
          "provides": [{"key": "sum_squares", "type": "formula.sum_squares", "display_name": "平方和"}],
          "input_semantics": {"formula.x": ["第一个要平方的整数。"], "formula.y": ["第二个要平方的整数。"]},
          "output_semantics": {"sum_squares": ["x² + y²，是计算结果的第一部分。"]},
      })
class SumSquares:
    def run_pure(self, inputs, params):
        x = inputs["formula.x"]["value"]
        y = inputs["formula.y"]["value"]
        return {"sum_squares": x * x + y * y}


@node(id="formula.absolute_gap", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="取差值的绝对值", description="把带符号的差换成两数间的距离。",
      contract={
          "requires": [{"type": "formula.difference", "cardinality": "exactly_one", "display_name": "两数之差"}],
          "provides": [{"key": "absolute_gap", "type": "formula.absolute_gap", "display_name": "两数间距"}],
          "input_semantics": {"formula.difference": ["x − y，可以是负数。"]},
          "output_semantics": {"absolute_gap": ["|x − y|，是计算结果的第二部分。"]},
      })
class AbsoluteGap:
    def run_pure(self, inputs, params):
        return {"absolute_gap": abs(inputs["formula.difference"]["value"])}


@node(id="formula.combine_square_gap", node_type="vibeflow.node", rulesets=["vibeflow.process"],
      display_name="合并平方和与差距", description="把平方和与两数间距相加。",
      contract={
          "requires": [
              {"type": "formula.sum_squares", "cardinality": "exactly_one", "display_name": "平方和"},
              {"type": "formula.absolute_gap", "cardinality": "exactly_one", "display_name": "两数间距"},
          ],
          "provides": [{"key": "square_gap", "type": "formula.square_gap", "display_name": "平方与差距项"}],
          "input_semantics": {
              "formula.sum_squares": ["并行分支得到的 x² + y²。"],
              "formula.absolute_gap": ["并行分支得到的 |x − y|。"],
          },
          "output_semantics": {"square_gap": ["完整结果 x² + y² + |x − y|。"]},
      })
class CombineSquareGap:
    def run_pure(self, inputs, params):
        return {"square_gap": inputs["formula.sum_squares"]["value"] + inputs["formula.absolute_gap"]["value"]}
